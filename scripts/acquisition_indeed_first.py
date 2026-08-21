#!/usr/bin/env python3
"""Run broad Google Jobs acquisition only when the screened pool actually needs it.

Indeed is the primary discovery surface for this app. When the current screened
server pool is already healthy, spending one scarce SerpApi request on broad
Google Jobs reduces the quota available for dedicated Indeed public-index
searches. Free official ATS/provider refresh steps still run separately.
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
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
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
            "Indeed-first acquisition: broad structured search skipped; "
            f"screened pool={pool_size(payload)} >= {MIN_HEALTHY_POOL}. "
            "SerpApi quota reserved for dedicated Indeed discovery."
        )
        return
    acquisition_precision.main()


if __name__ == "__main__":
    main()
