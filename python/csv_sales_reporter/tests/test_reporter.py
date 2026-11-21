import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import reporter  # noqa: E402


class TestCsvSalesReporter(unittest.TestCase):
    def test_aggregates_utf8_and_cp932_with_dedup_and_anomalies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            in_dir = Path(tmp) / "in"
            out_dir = Path(tmp) / "out"
            in_dir.mkdir()

            # UTF-8 with BOM
            (in_dir / "a.csv").write_text(
                "order_id,date,category,amount\n"
                'ORD-1,2026/11/20,EC売上,"12,000"\n'
                "ORD-1,2026/11/20,EC売上,12000\n"
                "ORD-BAD,2026-99-99,EC売上,1000\n",
                encoding="utf-8-sig",
            )
            # CP932 (Shift-JIS)
            (in_dir / "b.csv").write_bytes(
                (
                    "order_id,date,category,amount\n"
                    "ORD-2,2026-11-21,法人,￥30000\n"
                    "ORD-NEG,2026-11-21,法人,-100\n"
                ).encode("cp932")
            )

            res = reporter.aggregate_csv_files(in_dir.glob("*.csv"))
            self.assertEqual(res.files_processed, 2)
            self.assertEqual(len(res.valid_records), 2)
            self.assertEqual(res.duplicate_count, 1)
            self.assertEqual(len(res.anomalies), 2)
            self.assertEqual(res.grand_total, Decimal("42000"))
            self.assertEqual(res.category_totals["EC売上"], Decimal("12000"))
            self.assertEqual(res.category_totals["法人"], Decimal("30000"))

            reporter.write_outputs(res, out_dir)
            self.assertTrue((out_dir / "category_summary.csv").is_file())
            self.assertTrue((out_dir / "anomalies.csv").is_file())
            self.assertTrue((out_dir / "summary.json").is_file())
            self.assertTrue((out_dir / "report.md").is_file())


if __name__ == "__main__":
    unittest.main()
