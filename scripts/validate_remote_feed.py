#!/usr/bin/env python3
"""Fail if a published candidate contains contradictory remote evidence."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FEED = ROOT / "data" / "jobs.json"
EXPLICIT_FULL_REMOTE = {
    "完全在宅",
    "フルリモート",
    "完全リモート",
    "100%リモート",
    "100％リモート",
    "fully remote",
    "100% remote",
}


def validate(payload: dict) -> list[str]:
    errors: list[str] = []
    jobs = payload.get("jobs")
    if not isinstance(jobs, list):
        return ["jobs must be a list"]

    malformed = payload.get("malformed_jobs")
    if malformed is not None and (
        not isinstance(malformed, int) or isinstance(malformed, bool) or malformed < 0
    ):
        errors.append("malformed_jobs must be a non-negative integer")

    for index, row in enumerate(jobs):
        if not isinstance(row, dict):
            continue
        prefix = f"jobs[{index}]"
        reasons = row.get("remote_reasons") or []
        if not isinstance(reasons, list):
            errors.append(f"{prefix}.remote_reasons must be a list")
            continue
        normalized = {str(value or "").strip().lower() for value in reasons}
        warnings = [value for value in normalized if value.startswith("注意:")]
        if warnings:
            errors.append(f"{prefix} contains contradictory remote signal: {sorted(warnings)[0]}")
        if row.get("tier") == "high" and not any(
            phrase.lower() in normalized for phrase in EXPLICIT_FULL_REMOTE
        ):
            errors.append(f"{prefix} high tier lacks explicit full-remote evidence")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feed", type=Path, default=DEFAULT_FEED)
    args = parser.parse_args()
    try:
        payload = json.loads(args.feed.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"invalid JSON: {exc}", file=sys.stderr)
        raise SystemExit(1)
    errors = validate(payload)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
    print(f"remote feed validation passed: {len(payload.get('jobs', []))} jobs")


if __name__ == "__main__":
    main()
