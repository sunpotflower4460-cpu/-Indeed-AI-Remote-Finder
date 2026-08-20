#!/usr/bin/env python3
"""Keep deep stock above the PWA's 30-candidate visible minimum.

The user-facing target remains 100 strict, unapplied candidates, but acquisition
must happen *before* final LLM/presence/AI-use vetoes. Recent production kept 42
of 50 pre-final rows, so stopping acquisition at 100 can systematically miss the
100-row final-stock goal. This wrapper therefore targets 120 pre-final rows.

All supplemental sources remain zero-SerpApi and pass the same production
quality builder. Core official provider pages are checked first, then a bounded
live OneForma catalog discovery layer, a deeper Japan-specific official-page
layer, RWS TrainAI, and finally the existing Welo/LILT/Prolific targeted ATS
feeds. Final quality vetoes still run afterwards, so the deeper buffer absorbs
both user actions and downstream quality removals without accepting weaker jobs.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import acquisition
import supplement_official_ai_providers as direct
import supplement_oneforma_catalog as oneforma_catalog
import supplement_official_japan_depth as japan_depth
import supplement_rws_trainai as rws
import supplement_targeted_public_ats as targeted

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FEED = ROOT / "data" / "jobs.json"
VISIBLE_MINIMUM = 30
POST_FINAL_STOCK_TARGET = 100
PRE_FINAL_BUFFER_TARGET = 120
BUFFER_POLICY_VERSION = 6


def _load(path: Path | None) -> dict:
    if not path:
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _rearm_quality_builder() -> None:
    """Let each in-process source reinstall remote + strict quality wrappers.

    ``acquisition_precision.install()`` intentionally points ``build_row`` at its
    trusted-apply implementation. The first supplemental source then wraps that
    builder with the production remote/autonomy policy and strict quality policy.
    Because the buffered refill runs several source modules in one Python process,
    a later source used to call ``install()`` again, replace ``build_row``, and
    then see both one-time configured flags. The result was valid-looking rows
    without autonomy and quality stamps.

    Re-arming both flags before every source keeps the intended order deterministic:
    precision install -> remote/autonomy wrapper -> strict quality wrapper -> rows.
    Each source starts from the trusted base builder, so this does not stack
    recursive build-row wrappers.
    """
    acquisition._production_remote_policy_configured = False
    acquisition._production_quality_policy_configured = False


def top_up_with_buffer(
    payload: dict,
    previous_payload: dict | None = None,
    **source_overrides,
) -> dict:
    previous = previous_payload or {}

    # Tests can supply source payloads to stay fully offline. Production omits
    # them and checks only audited public pages and documented public ATS feeds.
    _rearm_quality_builder()
    direct_pages_supplied = "direct_pages" in source_overrides
    direct_pages = source_overrides.pop("direct_pages", None)
    if direct_pages_supplied:
        payload = direct.supplement(payload, previous, fetched_pages=direct_pages)
    else:
        payload = direct.supplement(payload, previous)

    _rearm_quality_builder()
    oneforma_index_supplied = "oneforma_index_pages" in source_overrides
    oneforma_detail_supplied = "oneforma_detail_pages" in source_overrides
    oneforma_index_pages = source_overrides.pop("oneforma_index_pages", None)
    oneforma_detail_pages = source_overrides.pop("oneforma_detail_pages", None)
    if oneforma_index_supplied or oneforma_detail_supplied:
        payload = oneforma_catalog.supplement(
            payload,
            previous,
            index_pages=oneforma_index_pages or {},
            detail_pages=oneforma_detail_pages or {},
        )
    else:
        payload = oneforma_catalog.supplement(payload, previous)

    _rearm_quality_builder()
    depth_pages_supplied = "japan_depth_pages" in source_overrides
    depth_pages = source_overrides.pop("japan_depth_pages", None)
    if depth_pages_supplied:
        payload = japan_depth.supplement(payload, previous, fetched_pages=depth_pages)
    else:
        payload = japan_depth.supplement(payload, previous)

    _rearm_quality_builder()
    rws_posts_supplied = "rws_posts" in source_overrides
    rws_posts = source_overrides.pop("rws_posts", None)
    if rws_posts_supplied:
        payload = rws.supplement(payload, previous, posts=rws_posts)
    else:
        payload = rws.supplement(payload, previous)

    _rearm_quality_builder()
    original_target = targeted.TARGET_POOL
    targeted.TARGET_POOL = PRE_FINAL_BUFFER_TARGET
    try:
        result = targeted.top_up(payload, previous, **source_overrides)
    finally:
        targeted.TARGET_POOL = original_target

    after = len([row for row in result.get("jobs") or [] if isinstance(row, dict)])
    result["candidate_pre_final_buffer_policy_version"] = BUFFER_POLICY_VERSION
    result["candidate_visible_minimum"] = VISIBLE_MINIMUM
    result["candidate_post_final_stock_target"] = POST_FINAL_STOCK_TARGET
    result["candidate_pre_final_buffer_target"] = PRE_FINAL_BUFFER_TARGET
    result["candidate_pre_final_buffer_ready"] = after >= PRE_FINAL_BUFFER_TARGET
    result["candidate_pre_final_buffer_uses_serpapi"] = False
    result["candidate_quality_builder_rearmed_per_source"] = True
    result["candidate_oneforma_catalog_in_buffer"] = True
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
        f"pre120={result.get('candidate_pre_final_buffer_ready')}"
    )


if __name__ == "__main__":
    main()
