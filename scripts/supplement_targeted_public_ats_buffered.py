#!/usr/bin/env python3
"""Keep a safety margin above the PWA's 30-candidate minimum.

The underlying targeted ATS supplement deliberately does not relax any quality
rule. This wrapper changes only *when* that supplement is allowed to stop:
instead of stopping as soon as the pre-final pool reaches 30, continue topping
up while it is below 45. Recent production showed that deterministic candidates
can still be removed by the LLM/presence gate, so a pre-final buffer makes the
user-facing 30-row queue more resilient without accepting weaker jobs.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import supplement_targeted_public_ats as targeted

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FEED = ROOT / "data" / "jobs.json"
VISIBLE_MINIMUM = 30
PRE_FINAL_BUFFER_TARGET = 45
BUFFER_POLICY_VERSION = 1


def _load(path: Path | None) -> dict:
    if not path:
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def top_up_with_buffer(
    payload: dict,
    previous_payload: dict | None = None,
    **source_overrides,
) -> dict:
    original_target = targeted.TARGET_POOL
    targeted.TARGET_POOL = PRE_FINAL_BUFFER_TARGET
    try:
        result = targeted.top_up(payload, previous_payload or {}, **source_overrides)
    finally:
        targeted.TARGET_POOL = original_target

    after = len([row for row in result.get("jobs") or [] if isinstance(row, dict)])
    result["candidate_pre_final_buffer_policy_version"] = BUFFER_POLICY_VERSION
    result["candidate_visible_minimum"] = VISIBLE_MINIMUM
    result["candidate_pre_final_buffer_target"] = PRE_FINAL_BUFFER_TARGET
    result["candidate_pre_final_buffer_ready"] = after >= PRE_FINAL_BUFFER_TARGET
    # Keep the original field semantically honest: it means the 30-row product
    # minimum, not the stricter internal buffer threshold.
    result["candidate_targeted_public_ats_goal_30_ready"] = after >= VISIBLE_MINIMUM
    if result.get("candidate_targeted_public_ats_skipped") == "pool-at-or-above-30":
        result["candidate_targeted_public_ats_skipped"] = "pool-at-or-above-buffer-target"
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feed", type=Path, default=DEFAULT_FEED)
    parser.add_argument("--previous", type=Path)
    args = parser.parse_args()
    payload = _load(args.feed)
    if not payload:
        raise SystemExit(f"feed missing or invalid: {args.feed}")
    result = top_up_with_buffer(payload, _load(args.previous))
    args.feed.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        "buffered targeted ATS top-up: "
        f"before={result.get('candidate_targeted_public_ats_pool_before')} "
        f"after={result.get('candidate_targeted_public_ats_pool_after')} "
        f"min30={result.get('candidate_targeted_public_ats_goal_30_ready')} "
        f"buffer45={result.get('candidate_pre_final_buffer_ready')}"
    )


if __name__ == "__main__":
    main()
