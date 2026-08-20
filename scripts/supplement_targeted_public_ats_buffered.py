#!/usr/bin/env python3
"""Keep deep stock above the PWA's 30-candidate visible minimum.

The user-facing target remains 100 strict, unapplied candidates, but acquisition
must happen *before* final LLM/presence/AI-use vetoes. Recent production kept 42
of 50 pre-final rows, so stopping acquisition at 100 can systematically miss the
100-row final-stock goal. This wrapper therefore targets 120 pre-final rows.

All supplemental sources remain zero-SerpApi and pass the same production
quality builder. Core official provider pages are checked first, then a deeper
Japan-specific official-page layer, RWS TrainAI, and finally the existing
Welo/LILT/Prolific targeted ATS feeds. Final quality vetoes still run afterwards,
so the deeper buffer absorbs both user actions and downstream quality removals
without accepting weaker jobs.

Important: each source module is also usable standalone and therefore calls
``acquisition_precision.install()`` itself. Re-installing that adapter after the
quality/autonomy wrappers have already been configured would replace the wrapped
builder with the lower-level trusted-source builder. This orchestrator installs
and configures the production builder once, then temporarily makes repeated
adapter installs no-ops while the source chain runs. That preserves identical
quality/autonomy stamping for the first, second, and every later source.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import acquisition_precision
import acquisition_quality
import supplement_official_ai_providers as direct
import supplement_official_japan_depth as japan_depth
import supplement_rws_trainai as rws
import supplement_targeted_public_ats as targeted

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FEED = ROOT / "data" / "jobs.json"
VISIBLE_MINIMUM = 30
POST_FINAL_STOCK_TARGET = 100
PRE_FINAL_BUFFER_TARGET = 120
BUFFER_POLICY_VERSION = 5


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
    previous = previous_payload or {}

    # Build the complete trusted-source -> remote/autonomy -> quality wrapper
    # exactly once. Source modules call install/configure for standalone safety,
    # but those repeated installs must not clobber the already-wrapped builder.
    acquisition_precision.install()
    acquisition_quality.configure_quality_policy()
    original_install = acquisition_precision.install
    acquisition_precision.install = lambda: None

    try:
        # Tests can supply direct_pages/japan_depth_pages/rws_posts to stay fully
        # offline. Production omits them and checks only the audited public pages
        # and documented public ATS endpoints.
        direct_pages_supplied = "direct_pages" in source_overrides
        direct_pages = source_overrides.pop("direct_pages", None)
        if direct_pages_supplied:
            payload = direct.supplement(payload, previous, fetched_pages=direct_pages)
        else:
            payload = direct.supplement(payload, previous)

        depth_pages_supplied = "japan_depth_pages" in source_overrides
        depth_pages = source_overrides.pop("japan_depth_pages", None)
        if depth_pages_supplied:
            payload = japan_depth.supplement(payload, previous, fetched_pages=depth_pages)
        else:
            payload = japan_depth.supplement(payload, previous)

        rws_posts_supplied = "rws_posts" in source_overrides
        rws_posts = source_overrides.pop("rws_posts", None)
        if rws_posts_supplied:
            payload = rws.supplement(payload, previous, posts=rws_posts)
        else:
            payload = rws.supplement(payload, previous)

        original_target = targeted.TARGET_POOL
        targeted.TARGET_POOL = PRE_FINAL_BUFFER_TARGET
        try:
            result = targeted.top_up(payload, previous, **source_overrides)
        finally:
            targeted.TARGET_POOL = original_target
    finally:
        acquisition_precision.install = original_install

    after = len([row for row in result.get("jobs") or [] if isinstance(row, dict)])
    result["candidate_pre_final_buffer_policy_version"] = BUFFER_POLICY_VERSION
    result["candidate_visible_minimum"] = VISIBLE_MINIMUM
    result["candidate_post_final_stock_target"] = POST_FINAL_STOCK_TARGET
    result["candidate_pre_final_buffer_target"] = PRE_FINAL_BUFFER_TARGET
    result["candidate_pre_final_buffer_ready"] = after >= PRE_FINAL_BUFFER_TARGET
    result["candidate_pre_final_buffer_uses_serpapi"] = False
    result["candidate_sequential_quality_wrapper_preserved"] = True
    # The 30-row field remains the product's hard visible-floor signal, not the
    # deeper stock target.
    result["candidate_targeted_public_ats_goal_30_ready"] = after >= VISIBLE_MINIMUM
    if result.get("candidate_targeted_public_ats_skipped") in {
        "pool-at-or-above-30",
        "pool-at-or-above-buffer-target",
    }:
        result["candidate_targeted_public_ats_skipped"] = "pool-at-or-above-pre-final-target"
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
        "buffered official-source top-up: "
        f"before={result.get('candidate_targeted_public_ats_pool_before')} "
        f"after={result.get('candidate_targeted_public_ats_pool_after')} "
        f"min30={result.get('candidate_targeted_public_ats_goal_30_ready')} "
        f"pre120={result.get('candidate_pre_final_buffer_ready')} "
        f"quality-wrapper={result.get('candidate_sequential_quality_wrapper_preserved')}"
    )


if __name__ == "__main__":
    main()
