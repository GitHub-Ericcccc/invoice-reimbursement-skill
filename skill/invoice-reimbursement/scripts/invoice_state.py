#!/usr/bin/env python3
"""Inventory invoice PDFs and atomically record verified reimbursement batches."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path


NORMALIZED_NAME = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})-(?P<content>.+)-(?P<amount>\d+\.\d{2})(?:-(?P<suffix>\d+))?\.pdf$",
    re.IGNORECASE,
)
SUMMARY_WORKBOOK = "报销表.xlsx"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_state(path: Path) -> dict:
    if not path.exists():
        return {"schema_version": 1, "entries": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not isinstance(data.get("entries"), list):
        raise ValueError(f"Unsupported or invalid state file: {path}")
    return data


def default_state(project_dir: Path) -> Path:
    return project_dir / ".codex" / "invoice-reimbursement-state.json"


def scan(args: argparse.Namespace) -> None:
    project_dir = Path(args.project_dir).resolve(strict=True)
    state_path = Path(args.state).resolve() if args.state else default_state(project_dir)
    state = load_state(state_path)
    known_hashes = {entry.get("sha256") for entry in state["entries"] if entry.get("sha256")}
    known_numbers = {
        str(entry.get("invoice_number"))
        for entry in state["entries"]
        if entry.get("invoice_number") not in (None, "")
    }

    pdfs = []
    for path in sorted(project_dir.glob("*.pdf"), key=lambda item: item.name.casefold()):
        digest = sha256_file(path)
        match = NORMALIZED_NAME.match(path.name)
        pdfs.append(
            {
                "name": path.name,
                "path": str(path),
                "size": path.stat().st_size,
                "sha256": digest,
                "known_by_sha256": digest in known_hashes,
                "normalized_filename": match.groupdict() if match else None,
            }
        )

    workbooks = []
    for pattern in ("*.xlsx", "*.xlsm"):
        for path in project_dir.glob(pattern):
            stat = path.stat()
            workbooks.append(
                {
                    "name": path.name,
                    "path": str(path),
                    "size": stat.st_size,
                    "modified_utc": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                }
            )
    workbooks.sort(key=lambda item: item["modified_utc"], reverse=True)

    print(
        json.dumps(
            {
                "schema_version": 1,
                "project_dir": str(project_dir),
                "state_path": str(state_path),
                "state_exists": state_path.exists(),
                "known_invoice_numbers": sorted(known_numbers),
                "pdfs": pdfs,
                "summary_workbook": {
                    "name": SUMMARY_WORKBOOK,
                    "path": str(project_dir / SUMMARY_WORKBOOK),
                    "exists": (project_dir / SUMMARY_WORKBOOK).is_file(),
                },
                "workbooks": workbooks,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def validate_entry(entry: dict) -> None:
    required = {
        "sha256",
        "invoice_number",
        "issue_date",
        "category",
        "amount",
        "normalized_filename",
        "workbook_sheet",
        "workbook_row",
    }
    missing = sorted(required.difference(entry))
    if missing:
        raise ValueError(f"Batch entry missing fields: {', '.join(missing)}")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", str(entry["sha256"])):
        raise ValueError("Invalid SHA-256 in batch entry")
    if float(entry["amount"]) < 0:
        raise ValueError("Amount must not be negative")
    datetime.strptime(str(entry["issue_date"]), "%Y-%m-%d")


def atomic_json_write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def record(args: argparse.Namespace) -> None:
    invoice_dir = Path(args.invoice_dir).resolve(strict=True)
    state_path = Path(args.state).resolve()
    batch_path = Path(args.batch).resolve(strict=True)
    workbook_path = Path(args.workbook).resolve(strict=True)
    if workbook_path.parent != invoice_dir or workbook_path.name != SUMMARY_WORKBOOK:
        raise ValueError(
            f"Workbook must be exactly {invoice_dir / SUMMARY_WORKBOOK}"
        )
    expected_state_dir = invoice_dir / ".codex"
    if state_path.parent != expected_state_dir:
        raise ValueError(f"State must be stored under {expected_state_dir}")
    state = load_state(state_path)
    batch = json.loads(batch_path.read_text(encoding="utf-8"))
    if not isinstance(batch, list) or not batch:
        raise ValueError("Batch must be a non-empty JSON array")

    existing_hashes = {entry.get("sha256") for entry in state["entries"]}
    existing_numbers = {
        str(entry.get("invoice_number"))
        for entry in state["entries"]
        if entry.get("invoice_number") not in (None, "")
    }
    batch_hashes: set[str] = set()
    batch_numbers: set[str] = set()
    committed_at = datetime.now(timezone.utc).isoformat()
    additions = []

    for raw_entry in batch:
        if not isinstance(raw_entry, dict):
            raise ValueError("Each batch entry must be a JSON object")
        validate_entry(raw_entry)
        digest = str(raw_entry["sha256"]).lower()
        number = str(raw_entry["invoice_number"]) if raw_entry["invoice_number"] not in (None, "") else ""
        if digest in existing_hashes or digest in batch_hashes:
            raise ValueError(f"Duplicate SHA-256: {digest}")
        if number and (number in existing_numbers or number in batch_numbers):
            raise ValueError(f"Duplicate invoice number: {number}")
        batch_hashes.add(digest)
        if number:
            batch_numbers.add(number)
        entry = dict(raw_entry)
        entry["sha256"] = digest
        entry["workbook"] = str(workbook_path)
        entry["committed_at_utc"] = committed_at
        additions.append(entry)

    state["entries"].extend(additions)
    state["updated_at_utc"] = committed_at
    atomic_json_write(state_path, state)
    print(json.dumps({"state": str(state_path), "recorded": len(additions)}, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan", help="Inventory PDFs, workbooks, and prior state")
    scan_parser.add_argument("--project-dir", required=True)
    scan_parser.add_argument("--state")
    scan_parser.set_defaults(func=scan)

    record_parser = subparsers.add_parser("record", help="Atomically record a verified batch")
    record_parser.add_argument("--invoice-dir", required=True)
    record_parser.add_argument("--state", required=True)
    record_parser.add_argument("--batch", required=True)
    record_parser.add_argument("--workbook", required=True)
    record_parser.set_defaults(func=record)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
