#!/usr/bin/env python3
"""Run broad structured acquisition only when the screened pool needs replenishment.

The app is Indeed-first. When at least 30 screened candidates are already present,
spending scarce SerpApi quota on broad Google Jobs discovery reduces the quota
available for dedicated Indeed public-index discovery. Free official ATS/provider
supplements still run later in the workflow.
"""
from __future__ import annotations

import json
from pathlib import Path

import acquisition_precision

ROOT = Path(__file__).resolve().parents[1]
FEED = ROOT / "data" / "jobs.json"
MIN_HEALTHY_POOL = 30


def load_payload(path: Path = FEED) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def pool_size(payload: dict) -> int:
    try:
        stamped = max(0, int(payload.get("candidate_pool_size") or 0))
    except Exception:
        stamped = 0
    jobs = payload.get("jobs") or []
    actual = len(jobs) if isinstance(jobs, list) else 0
    return max(stamped, actual)


def should_skip_structured_search(payload: dict) -> bool:
    return pool_size(payload) >= MIN_HEALTHY_POOL


def main() -> None:
    payload = load_payload()
    if payload and should_skip_structured_search(payload):
        print(
            "Indeed-first acquisition: structured Google Jobs search skipped; "
            f"screened pool={pool_size(payload)} >= {MIN_HEALTHY_POOL}. "
            "SerpApi quota reserved for dedicated Indeed discovery."
        )
        return
    acquisition_precision.main()


if __name__ == "__main__":
    main()
