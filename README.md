# Business Automation Kit (Python / Google Apps Script)

実務の定型作業を安全・確実に自動化するための実装サンプル集です。  
**「壊れにくいエラー処理」「自動テスト」「非エンジニア向け導入マニュアル」**をセットで提供する標準品質を示しています。

---

## 収録ツール一覧

| ツール | 言語 / 実行環境 | 主な用途 | テスト |
| --- | --- | --- | :---: |
| [csv_sales_reporter](python/csv_sales_reporter/) | Python 3.10+（標準ライブラリのみ） | 複数CSV（UTF-8 / Shift-JIS）の自動統合・重複除外・異常値検知・集計レポート出力 | 自動テスト済 |
| [sheet_workflow_automation](gas/sheet_workflow_automation/) | Google Apps Script (GAS) | スプレッドシートのステータス監視・重複送信防止付きメール/Webhook通知・実行ログ記録 | 構造検証済 |

---

## 設計ポリシー

1. **実務の落とし穴を先回りで潰す**
   - 日本の業務CSVで頻発する文字コード混在（UTF-8 BOM / CP932・Shift-JIS）、カンマ付き数値、空白・重複行を安全に処理します。
   - GASの通知処理では「二重送信防止（送信済みフラグ＋LockService排他制御）」を標準実装しています。
2. **依存関係を最小限に保つ**
   - Pythonツールは標準ライブラリのみで動作するため、環境構築トラブルが起きにくい構成です。
3. **誰でも運用できるドキュメント付き**
   - 導入手順書・エラー時の確認ポイントを日本語で同梱しています。

---

## 動作確認方法（Pythonツール）

```bash
python3 -m unittest discover -s python/csv_sales_reporter/tests -v
python3 python/csv_sales_reporter/reporter.py \
  --input-dir python/csv_sales_reporter/sample_data \
  --output-dir /tmp/report_out
```
