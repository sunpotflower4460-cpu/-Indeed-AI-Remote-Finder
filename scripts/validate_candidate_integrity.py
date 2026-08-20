#!/usr/bin/env python3
"""Validate active Japan/identity/semantic integrity invariants."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import apply_candidate_integrity_gate as integrity  # noqa: E402

ROOT = SCRIPT_DIR.parent
DEFAULT_FEED = ROOT / "data" / "jobs.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feed", type=Path, default=DEFAULT_FEED)
    args = parser.parse_args()
    try:
        payload = json.loads(args.feed.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"invalid JSON: {exc}", file=sys.stderr)
        raise SystemExit(1)
    if not isinstance(payload, dict):
        print("feed must be an object", file=sys.stderr)
        raise SystemExit(1)

    errors = integrity.validate_active_payload(payload)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
    active = int(payload.get("candidate_integrity_gate_version") or 0)
    print(
        "candidate integrity validation passed: "
        f"active={active} jobs={len(payload.get('jobs') or [])}"
    )


if __name__ == "__main__":
    main()
