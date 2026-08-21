#!/usr/bin/env python3
"""Validate current Indeed discovery truth and safety invariants."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FEED = ROOT / "data" / "jobs.json"
MIN_VERSION = 4


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
    if "viewjob-jk-plus-search-vjk" not in method:
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

    hits = int(payload.get("candidate_indeed_index_hits_run") or 0)
    exact_hits = int(payload.get("candidate_indeed_index_exact_url_hits_run") or 0)
    vjk_hits = int(payload.get("candidate_indeed_index_search_vjk_hits_run") or 0)
    if hits != exact_hits + vjk_hits:
        raise RuntimeError("Indeed runtime validation: hit-type counts inconsistent")

    seeds = payload.get("candidate_indeed_index_seeds") or []
    if not isinstance(seeds, list):
        raise RuntimeError("Indeed runtime validation: seeds must be a list")
    exact_seeds = int(payload.get("candidate_indeed_index_exact_url_seed_count") or 0)
    vjk_seeds = int(payload.get("candidate_indeed_index_search_vjk_seed_count") or 0)
    if len(seeds) != exact_seeds + vjk_seeds:
        raise RuntimeError("Indeed runtime validation: seed-type counts inconsistent")

    for index, seed in enumerate(seeds):
        if not isinstance(seed, dict):
            raise RuntimeError(f"Indeed runtime validation: seed {index} is not an object")
        kind = str(seed.get("indeed_index_link_kind") or "")
        if kind == "viewjob-jk":
            if seed.get("indeed_exact_url_verified") is not True:
                raise RuntimeError("Indeed runtime validation: direct seed lacks exact-url proof")
            if seed.get("indeed_promotion_eligible") is not True:
                raise RuntimeError("Indeed runtime validation: direct seed unexpectedly non-promotable")
        elif kind == "search-vjk":
            if seed.get("indeed_job_key_verified") is not True:
                raise RuntimeError("Indeed runtime validation: vjk seed lacks job-key proof")
            if seed.get("indeed_exact_url_verified") is not False:
                raise RuntimeError("Indeed runtime validation: vjk seed falsely claims exact URL proof")
            if seed.get("indeed_canonical_url_derived_from_vjk") is not True:
                raise RuntimeError("Indeed runtime validation: vjk derivation disclosure missing")
            if seed.get("indeed_promotion_eligible") is not False:
                raise RuntimeError("Indeed runtime validation: vjk seed must remain discovery-only")
        else:
            raise RuntimeError("Indeed runtime validation: unknown seed evidence kind")
        if seed.get("indeed_page_body_verified") is not False:
            raise RuntimeError("Indeed runtime validation: index seed cannot claim page-body verification")


def main() -> None:
    payload = load_payload()
    validate(payload)
    print(
        "Indeed runtime validation passed: "
        f"version={payload.get('candidate_indeed_index_version')} "
        f"attempted={payload.get('candidate_indeed_index_request_run')} "
        f"hits={payload.get('candidate_indeed_index_hits_run')} "
        f"exact={payload.get('candidate_indeed_index_exact_url_seed_count')} "
        f"vjk={payload.get('candidate_indeed_index_search_vjk_seed_count')} "
        f"promoted={payload.get('candidate_indeed_index_promoted_run')} "
        f"coverage={payload.get('candidate_indeed_index_profile_coverage_count')}/"
        f"{payload.get('candidate_indeed_index_profile_count')}"
    )


if __name__ == "__main__":
    main()
