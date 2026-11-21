#!/usr/bin/env python3
"""Aggregate multiple business CSV files (UTF-8 / Shift-JIS) into clean reports.

Features:
- Auto-detects UTF-8 (with/without BOM) and CP932 (Shift-JIS) encodings.
- Deduplicates rows by order_id while preserving audit counts.
- Validates numeric amounts and dates, separating anomalies instead of crashing.
- Generates summary CSV, anomaly CSV, JSON metrics, and a Japanese Markdown report.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable


ENCODINGS_TO_TRY = ("utf-8-sig", "cp932", "utf-8")
REQUIRED_COLUMNS = {"order_id", "date", "category", "amount"}


@dataclass(frozen=True)
class CleanRecord:
    order_id: str
    date: str
    category: str
    amount: Decimal
    source_file: str


@dataclass(frozen=True)
class AnomalyRecord:
    source_file: str
    row_number: int
    reason: str
    raw_row: dict[str, str]


@dataclass(frozen=True)
class ReportResult:
    files_processed: int
    total_rows_read: int
    valid_records: list[CleanRecord]
    duplicate_count: int
    anomalies: list[AnomalyRecord]
    category_totals: dict[str, Decimal]
    daily_totals: dict[str, Decimal]
    grand_total: Decimal


def read_csv_rows(path: Path) -> tuple[list[dict[str, str]], str]:
    """Read CSV rows trying common Japanese business encodings."""
    last_error: Exception | None = None
    for enc in ENCODINGS_TO_TRY:
        try:
            with path.open("r", encoding=enc, newline="") as fh:
                reader = csv.DictReader(fh)
                if reader.fieldnames is None:
                    return [], enc
                rows = [dict(row) for row in reader]
                return rows, enc
        except UnicodeDecodeError as exc:
            last_error = exc
            continue
    raise ValueError(f"Failed to decode {path.name}: {last_error}")


def parse_amount(raw_value: str) -> Decimal:
    cleaned = raw_value.strip().replace(",", "").replace("¥", "").replace("￥", "").replace("円", "")
    if not cleaned:
        raise InvalidOperation("empty amount")
    value = Decimal(cleaned)
    if not value.is_finite():
        raise InvalidOperation("non-finite amount")
    return value


def normalize_date(raw_value: str) -> str:
    text = raw_value.strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError(f"unsupported date format: {text!r}")


def aggregate_csv_files(paths: Iterable[Path]) -> ReportResult:
    file_list = sorted(paths)
    seen_order_ids: set[str] = set()
    valid_records: list[CleanRecord] = []
    anomalies: list[AnomalyRecord] = []
    category_totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    daily_totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    grand_total = Decimal("0")
    total_rows_read = 0
    duplicate_count = 0

    for path in file_list:
        rows, _ = read_csv_rows(path)
        for idx, row in enumerate(rows, start=2):
            total_rows_read += 1
            missing = [col for col in REQUIRED_COLUMNS if col not in row]
            if missing:
                anomalies.append(
                    AnomalyRecord(path.name, idx, f"missing columns: {','.join(sorted(missing))}", row)
                )
                continue

            order_id = (row.get("order_id") or "").strip()
            category = (row.get("category") or "").strip() or "未分類"
            if not order_id:
                anomalies.append(AnomalyRecord(path.name, idx, "empty order_id", row))
                continue

            if order_id in seen_order_ids:
                duplicate_count += 1
                continue

            try:
                norm_date = normalize_date(row.get("date") or "")
            except ValueError as exc:
                anomalies.append(AnomalyRecord(path.name, idx, str(exc), row))
                continue

            try:
                amount = parse_amount(row.get("amount") or "")
            except InvalidOperation:
                anomalies.append(
                    AnomalyRecord(path.name, idx, f"invalid amount: {row.get('amount')!r}", row)
                )
                continue

            if amount < 0:
                anomalies.append(AnomalyRecord(path.name, idx, "negative amount", row))
                continue

            seen_order_ids.add(order_id)
            rec = CleanRecord(
                order_id=order_id,
                date=norm_date,
                category=category,
                amount=amount,
                source_file=path.name,
            )
            valid_records.append(rec)
            category_totals[category] += amount
            daily_totals[norm_date] += amount
            grand_total += amount

    return ReportResult(
        files_processed=len(file_list),
        total_rows_read=total_rows_read,
        valid_records=valid_records,
        duplicate_count=duplicate_count,
        anomalies=anomalies,
        category_totals=dict(sorted(category_totals.items())),
        daily_totals=dict(sorted(daily_totals.items())),
        grand_total=grand_total,
    )


def write_outputs(result: ReportResult, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Category summary CSV (UTF-8 BOM for seamless Excel opening)
    with (output_dir / "category_summary.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["category", "total_amount"])
        for cat, total in result.category_totals.items():
            writer.writerow([cat, str(total)])

    # 2. Anomalies CSV
    with (output_dir / "anomalies.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["source_file", "row_number", "reason", "raw_row_json"])
        for anom in result.anomalies:
            writer.writerow(
                [anom.source_file, anom.row_number, anom.reason, json.dumps(anom.raw_row, ensure_ascii=False)]
            )

    # 3. Machine-readable JSON summary
    summary_payload = {
        "files_processed": result.files_processed,
        "total_rows_read": result.total_rows_read,
        "valid_records": len(result.valid_records),
        "duplicate_rows_skipped": result.duplicate_count,
        "anomalies_detected": len(result.anomalies),
        "grand_total": str(result.grand_total),
        "category_totals": {k: str(v) for k, v in result.category_totals.items()},
        "daily_totals": {k: str(v) for k, v in result.daily_totals.items()},
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # 4. Human-readable Japanese Markdown report
    lines = [
        "# 自動集計レポート",
        "",
        "## 処理サマリー",
        f"- 処理ファイル数: **{result.files_processed}**",
        f"- 読込総行数: **{result.total_rows_read}**",
        f"- 有効レコード数: **{len(result.valid_records)}**",
        f"- 重複スキップ件数: **{result.duplicate_count}**",
        f"- 異常検知件数: **{len(result.anomalies)}**",
        f"- 合計金額: **{result.grand_total:,.0f} 円**",
        "",
        "## カテゴリ別集計",
        "| カテゴリ | 合計金額（円） |",
        "| --- | ---: |",
    ]
    for cat, total in result.category_totals.items():
        lines.append(f"| {cat} | {total:,.0f} |")

    lines.extend(["", "## 日別集計", "| 日付 | 合計金額（円） |", "| --- | ---: |"])
    for day, total in result.daily_totals.items():
        lines.append(f"| {day} | {total:,.0f} |")

    if result.anomalies:
        lines.extend(["", "## 検知された異常データ", "| ファイル | 行 | 理由 |", "| --- | ---: | --- |"])
        for anom in result.anomalies:
            lines.append(f"| {anom.source_file} | {anom.row_number} | {anom.reason} |")

    (output_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Aggregate business CSV files into clean reports.")
    parser.add_argument("--input-dir", type=Path, required=True, help="Directory containing CSV files")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory to write reports")
    args = parser.parse_args(argv)

    if not args.input_dir.is_dir():
        print(f"Error: input directory not found: {args.input_dir}", file=sys.stderr)
        return 1

    csv_files = sorted(args.input_dir.glob("*.csv"))
    if not csv_files:
        print(f"Error: no CSV files found in {args.input_dir}", file=sys.stderr)
        return 1

    result = aggregate_csv_files(csv_files)
    write_outputs(result, args.output_dir)
    print(
        f"Done: {len(result.valid_records)} valid, {result.duplicate_count} duplicates, "
        f"{len(result.anomalies)} anomalies -> {args.output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
