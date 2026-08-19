#!/usr/bin/env python3
"""Remove candidates where an available LLM audit confirms a material mismatch.

This gate is deliberately asymmetric. Missing LLM coverage never removes a
candidate, so provider/API outages cannot empty the deterministic feed. When a
review is available, however, explicit high-confidence evidence of physical,
synchronous, human-dependent, or low-automation work is strong enough to veto
publication.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FEED = ROOT / "data" / "jobs.json"


def reject_reason(row: dict) -> str | None:
    review = row.get("llm_review")
    if not isinstance(review, dict):
        return None
    verdict = str(review.get("verdict") or "")
    human = str(review.get("human_dependency") or "")
    sync = str(review.get("synchronous_human_interaction") or "")
    physical = review.get("physical_presence_required")
    try:
        confidence = int(review.get("confidence") or 0)
        automatable = int(review.get("automatable_fraction") or 0)
    except Exception:
        return None
    blockers = [str(x or "").strip() for x in review.get("blockers") or [] if str(x or "").strip()]

    if verdict == "reject":
        return "verdict-reject"
    if physical is True:
        return "physical-presence"
    if sync == "frequent":
        return "frequent-sync"
    if human == "high":
        return "high-human-dependency"
    if confidence >= 80 and sync == "occasional":
        return "confirmed-occasional-sync"
    if confidence >= 80 and human == "medium":
        return "confirmed-medium-human-dependency"
    if confidence >= 80 and automatable < 65:
        return "confirmed-low-automation"
    if confidence >= 85 and blockers and automatable < 90:
        return "confirmed-material-blocker"
    return None


def apply(payload: dict) -> dict:
    jobs = payload.get("jobs") or []
    if not isinstance(jobs, list):
        return payload
    kept: list[dict] = []
    dropped: list[dict] = []
    reasons: dict[str, int] = {}
    for row in jobs:
        if not isinstance(row, dict):
            kept.append(row)
            continue
        reason = reject_reason(row)
        if not reason:
            kept.append(row)
            continue
        dropped.append(row)
        reasons[reason] = reasons.get(reason, 0) + 1

    payload["jobs"] = kept
    payload["llm_quality_dropped"] = len(dropped)
    payload["llm_quality_drop_reasons"] = reasons
    payload["candidate_pool_size"] = len(kept)
    payload["live_jobs"] = sum(1 for row in kept if isinstance(row, dict) and not row.get("carryover"))
    payload["carryover_jobs"] = sum(1 for row in kept if isinstance(row, dict) and row.get("carryover"))
    payload["remote_search_only_jobs"] = sum(1 for row in kept if isinstance(row, dict) and row.get("remote_search_only"))
    target = int(payload.get("candidate_display_target") or 30)
    payload["pool_under_display_target"] = len(kept) < target
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feed", type=Path, default=DEFAULT_FEED)
    args = parser.parse_args()
    payload = json.loads(args.feed.read_text(encoding="utf-8"))
    result = apply(payload)
    args.feed.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"LLM quality gate kept {len(result.get('jobs', []))} jobs; "
        f"dropped {result.get('llm_quality_dropped', 0)}"
    )


if __name__ == "__main__":
    main()
