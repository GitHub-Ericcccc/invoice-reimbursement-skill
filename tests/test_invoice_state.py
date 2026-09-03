from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "skill" / "invoice-reimbursement" / "scripts" / "invoice_state.py"


class InvoiceStateTests(unittest.TestCase):
    def run_cli(self, *args: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, "-B", "-X", "utf8", str(SCRIPT), *args],
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def test_scan_location_and_duplicate_record(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            invoice_dir = Path(raw) / "invoices"
            invoice_dir.mkdir()
            pdf = invoice_dir / "2026-01-02-汽油-12.34.pdf"
            pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
            workbook = invoice_dir / "报销表.xlsx"
            workbook.write_bytes(b"test-workbook")
            digest = hashlib.sha256(pdf.read_bytes()).hexdigest()

            scan = self.run_cli("scan", "--project-dir", str(invoice_dir))
            inventory = json.loads(scan.stdout)
            self.assertTrue(inventory["summary_workbook"]["exists"])
            self.assertEqual(len(inventory["pdfs"]), 1)

            batch = Path(raw) / "batch.json"
            batch.write_text(
                json.dumps(
                    [
                        {
                            "sha256": digest,
                            "invoice_number": None,
                            "issue_date": "2026-01-02",
                            "category": "汽油",
                            "amount": 12.34,
                            "normalized_filename": pdf.name,
                            "workbook_sheet": "报销明细",
                            "workbook_row": 2,
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            state = invoice_dir / ".codex" / "invoice-reimbursement-state.json"
            self.run_cli(
                "record",
                "--invoice-dir",
                str(invoice_dir),
                "--state",
                str(state),
                "--batch",
                str(batch),
                "--workbook",
                str(workbook),
            )
            duplicate = self.run_cli(
                "record",
                "--invoice-dir",
                str(invoice_dir),
                "--state",
                str(state),
                "--batch",
                str(batch),
                "--workbook",
                str(workbook),
                expected=1,
            )
            self.assertIn("Duplicate SHA-256", duplicate.stderr)

    def test_rejects_workbook_outside_invoice_directory(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            invoice_dir = root / "invoices"
            invoice_dir.mkdir()
            wrong_workbook = root / "报销表.xlsx"
            wrong_workbook.write_bytes(b"test-workbook")
            batch = root / "batch.json"
            batch.write_text("[]", encoding="utf-8")
            state = invoice_dir / ".codex" / "invoice-reimbursement-state.json"
            result = self.run_cli(
                "record",
                "--invoice-dir",
                str(invoice_dir),
                "--state",
                str(state),
                "--batch",
                str(batch),
                "--workbook",
                str(wrong_workbook),
                expected=1,
            )
            self.assertIn("Workbook must be exactly", result.stderr)


if __name__ == "__main__":
    unittest.main()
