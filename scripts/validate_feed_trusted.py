#!/usr/bin/env python3
"""Feed validator extension for audited structured application destinations.

The legacy validator intentionally required a canonical jp.indeed.com/viewjob URL.
Production also permits a bounded set of job-board/ATS/provider URLs returned by
structured Google Jobs apply options or documented public employer ATS feeds.

Keep every legacy validation error except the canonical-Indeed URL error, and
replace that one only when the row independently revalidates through the same
application-destination allowlist with matching deterministic identity stamps.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import apply_sources
import validate_feed as legacy

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FEED = ROOT / "data" / "jobs.json"
URL_ERROR = re.compile(r"^jobs\[(\d+)\]\.url is not canonical Indeed viewjob for id=")
MIN_TRUSTED_APPLY_POLICY_VERSION = 2


def trusted_apply_row_valid(row: dict) -> bool:
    if not isinstance(row, dict):
        return False
    url = str(row.get("url") or "").strip()
    if not url:
        return False
    target = apply_sources.find_trusted_apply(
        {"apply_options": [{"title": "validated", "link": url}]}
    )
    if not target or target.kind == "indeed":
        return False
    try:
        policy_version = int(row.get("trusted_apply_policy_version") or 0)
    except (TypeError, ValueError):
        return False
    return bool(
        policy_version >= MIN_TRUSTED_APPLY_POLICY_VERSION
        and str(row.get("id") or "") == target.job_id
        and str(row.get("apply_source") or "") == target.source
        and str(row.get("apply_source_kind") or "") == target.kind
        and url == target.url
    )


def validate(payload: dict) -> list[str]:
    errors = legacy.validate(payload)
    jobs = payload.get("jobs") or []
    kept: list[str] = []
    for error in errors:
        match = URL_ERROR.match(error)
        if not match:
            kept.append(error)
            continue
        index = int(match.group(1))
        row = jobs[index] if isinstance(jobs, list) and 0 <= index < len(jobs) else None
        if not trusted_apply_row_valid(row):
            kept.append(error)
    return kept


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feed", type=Path, default=DEFAULT_FEED)
    args = parser.parse_args()
    try:
        payload = json.loads(args.feed.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"invalid JSON: {exc}")
        raise SystemExit(1)
    errors = validate(payload)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        raise SystemExit(1)
    print(f"trusted feed validation passed: {len(payload.get('jobs', []))} jobs")


if __name__ == "__main__":
    main()
