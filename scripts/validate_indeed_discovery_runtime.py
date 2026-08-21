#!/usr/bin/env python3
"""Validate that production Indeed discovery actually executed current code.

Zero matching jobs can be legitimate. Silent fallback to old discovery code or a
crash before telemetry is written is not. v3 also requires explicit disclosure
that the backend did not fetch Indeed page bodies plus measurable profile
coverage telemetry.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FEED = ROOT / "data" / "jobs.json"
MIN_VERSION = 3


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
    if payload.get("candidate_indeed_page_body_directly_accessed") is not False:
        raise RuntimeError("Indeed runtime validation: page-body access disclosure missing")

    configured = payload.get("provider_configured") is True
    surplus = int(payload.get("candidate_indeed_index_budget_surplus_before_run") or 0)
    attempted = int(payload.get("candidate_indeed_index_request_run") or 0)
    profiles = payload.get("candidate_indeed_index_query_profiles") or []
    profile_count = int(payload.get("candidate_indeed_index_profile_count") or 0)
    coverage_count = int(payload.get("candidate_indeed_index_profile_coverage_count") or 0)
    attempt_history = payload.get("candidate_indeed_index_profile_last_attempt") or {}

    if profile_count < 1:
        raise RuntimeError("Indeed runtime validation: profile count missing")
    if not isinstance(attempt_history, dict):
        raise RuntimeError("Indeed runtime validation: profile coverage history missing")
    if coverage_count != len(attempt_history):
        raise RuntimeError("Indeed runtime validation: profile coverage count inconsistent")
    if coverage_count > profile_count:
        raise RuntimeError("Indeed runtime validation: profile coverage exceeds profile count")

    if configured and surplus > 0 and attempted <= 0:
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
        f"promoted={payload.get('candidate_indeed_index_promoted_run')} "
        f"coverage={payload.get('candidate_indeed_index_profile_coverage_count')}/"
        f"{payload.get('candidate_indeed_index_profile_count')}"
    )


if __name__ == "__main__":
    main()
