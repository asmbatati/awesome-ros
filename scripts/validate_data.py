#!/usr/bin/env python3
"""
Validate data/papers.csv and data/frameworks.csv against their JSON schemas.

Checks: required columns present, consistent field counts, enum values,
duplicate DOIs. Exits non-zero on any failure. Stdlib only.

Usage: python scripts/validate_data.py
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
csv.field_size_limit(10_000_000)


def check_file(csv_path, schema_path):
    ok = True
    with open(schema_path) as f:
        schema = json.load(f)
    required = schema.get("required", [])
    props = schema.get("properties", {})

    with open(csv_path, encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    header, body = rows[0], rows[1:]
    print(f"{csv_path.name}: {len(body)} rows, {len(header)} columns")

    missing = [r for r in required if r not in header]
    if missing:
        print(f"  FAIL: missing required columns: {missing}")
        ok = False

    bad_counts = [(i, len(r)) for i, r in enumerate(body, start=2) if len(r) != len(header)]
    if bad_counts:
        print(f"  FAIL: {len(bad_counts)} rows with wrong field count, first: {bad_counts[:5]}")
        ok = False

    enum_cols = {k: set(v["enum"]) for k, v in props.items() if "enum" in v}
    idx = {h: i for i, h in enumerate(header)}
    n_enum_errors = 0
    for i, row in enumerate(body, start=2):
        for col, allowed in enum_cols.items():
            if col not in idx or idx[col] >= len(row):
                continue
            val = row[idx[col]].strip()
            if val and val not in allowed:
                if n_enum_errors < 20:
                    print(f"  FAIL row {i}: {col} = {val!r} not in schema enum")
                n_enum_errors += 1
    if n_enum_errors:
        print(f"  FAIL: {n_enum_errors} enum violations total")
        ok = False

    if ok:
        print("  OK")
    return ok


def check_duplicate_dois():
    with open(ROOT / "data" / "papers.csv", encoding="utf-8", newline="") as f:
        dois = [
            (r.get("DOI") or "").strip().lower()
            for r in csv.DictReader(f)
            if (r.get("DOI") or "").strip()
        ]
    seen, dupes = set(), []
    for d in dois:
        if d in seen:
            dupes.append(d)
        seen.add(d)
    if dupes:
        print(f"FAIL: {len(dupes)} duplicate DOI(s): {dupes[:10]}")
        return False
    print(f"DOIs: {len(dois)} present, no duplicates")
    return True


def main():
    ok = check_file(ROOT / "data" / "papers.csv", ROOT / "schema" / "papers.schema.json")
    ok = check_file(ROOT / "data" / "frameworks.csv", ROOT / "schema" / "frameworks.schema.json") and ok
    ok = check_duplicate_dois() and ok
    if not ok:
        sys.exit(1)
    print("\nAll validation checks passed.")


if __name__ == "__main__":
    main()
