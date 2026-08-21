#!/usr/bin/env python3
"""Validate that the production Indeed discovery step actually executed.

This is intentionally a runtime contract rather than a market-supply contract.
Zero matching jobs can be legitimate; silently running old code or crashing before
telemetry is written is not. The validator therefore never requires a positive
Indeed job count. It only requires the v2 discovery telemetry to be present and,
when the step reports budget surplus, at least one search attempt to have been
recorded.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FEED = ROOT / "data" / "jobs.json"
MIN_VERSION = 2


def load_payload(path: Path = FEED) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError("Indeed runtime validation: feed unreadable") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Indeed runtime validation: feed is not an object")
    return payload


def validate(payload: dict) -> None:
    version = int(payload.get("candidate_indeed_index_version") or 0)
    if version < MIN_VERSION:
        raise RuntimeError(
            f"Indeed runtime validation: discovery v{MIN_VERSION}+ telemetry missing (got {version})"
        )

    method = str(payload.get("candidate_indeed_index_method") or "")
    if "exact-indeed-viewjob" not in method:
        raise RuntimeError("Indeed runtime validation: unexpected discovery method")

    direct = int(payload.get("candidate_indeed_index_direct_indeed_requests") or 0)
    if direct != 0:
        raise RuntimeError("Indeed runtime validation: direct Indeed backend access must remain zero")

    surplus = int(payload.get("candidate_indeed_index_budget_surplus_before_run") or 0)
    attempted = int(payload.get("candidate_indeed_index_request_run") or 0)
    profiles = payload.get("candidate_indeed_index_query_profiles") or []

    # If the production step had quota surplus, it must record at least one
    # attempted public-index query. This catches crashes/import failures that
    # otherwise leave a stale v1 feed looking like a legitimate zero-result run.
    if surplus > 0 and attempted <= 0:
        raise RuntimeError(
            "Indeed runtime validation: quota surplus existed but no search attempt was recorded"
        )
    if attempted > 0 and (not isinstance(profiles, list) or not profiles):
        raise RuntimeError("Indeed runtime validation: attempted search has no profile telemetry")


def main() -> None:
    payload = load_payload()
    validate(payload)
    print(
        "Indeed runtime validation passed: "
        f"version={payload.get('candidate_indeed_index_version')} "
        f"attempted={payload.get('candidate_indeed_index_request_run')} "
        f"hits={payload.get('candidate_indeed_index_hits_run')} "
        f"promoted={payload.get('candidate_indeed_index_promoted_run')}"
    )


if __name__ == "__main__":
    main()
