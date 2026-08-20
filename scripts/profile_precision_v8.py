#!/usr/bin/env python3
"""Critical-low-stock rescue ordering layered on search precision v7.

V7 learns from zero-result searches and the earlier layers learn final outcomes,
family handoff, champion fatigue, and known-bad scarce slots. Production still
showed a clear product failure: with only one publishable candidate, some of the
four available searches were spent on generic document/testing profiles that
historically fail the final full-remote/autonomy gates.

V8 changes only discovery ordering while stock is critically low:
- pool <= 5: every available first-page slot is focused on AI rating/training,
  annotation, or search-quality work;
- pool 6..29: at least 75% of the available first-page window is focused there;
- pool >= 30: emergency focus is disabled and v7 ordering is untouched;
- current, verified provider-specific queries are added only while stock is low;
- recently searched exact profiles are avoided when another focus profile exists;
- family diversity is preferred before repeating the same focus family.

No publication threshold, remote/presence rule, LLM veto, AI-use policy, request
count, provider guard, or monthly budget rule is weakened.
"""
from __future__ import annotations

import math
from typing import Iterable

import profile_precision as core
import profile_precision_v7 as v7

PROFILE_LEARNING_VERSION = 8
CRITICAL_POOL_MAX = 5
LOW_STOCK_POOL_MAX = 30
LOW_STOCK_FOCUS_SHARE = 0.75
FOCUS_FAMILIES = frozenset({"ai_rater", "annotation", "search_quality"})

# Provider-specific searches are based on currently live remote Japanese AI/data
# work pages, plus generic nationwide variants. They are discovery probes only.
RESCUE_PROFILES: list[tuple[str, str]] = [
    (
        "source_rescue_ai_trainer_outlier_japanese",
        '"Outlier" "Japanese AI Training" remote Japan',
    ),
    (
        "source_rescue_search_eval_welo_japanese",
        '"Welo Global" "Search Quality" Japanese remote Japan',
    ),
    (
        "source_rescue_ai_rating_welo_ads_japanese",
        '"Welo Global" "Ads Quality" Japanese remote Japan',
    ),
    (
        "source_rescue_ai_trainer_welo_data_japanese",
        '"Welo Global" "Japanese Data Trainer" remote Japan',
    ),
    (
        "source_rescue_ai_rater_telus_japanese",
        '"TELUS Digital" "Japanese" rater remote Japan',
    ),
    (
        "source_rescue_ai_rater_japanese_nationwide",
        '"Japanese AI rater" "fully remote" "in Japan"',
    ),
    (
        "source_rescue_ai_trainer_japanese_nationwide",
        '"Japanese AI trainer" "fully remote" "in Japan"',
    ),
    (
        "source_rescue_ai_rater_llm_japanese",
        '"Japanese" "LLM evaluator" "fully remote" Japan',
    ),
    (
        "source_rescue_annotation_japanese_nationwide",
        '"Japanese data annotator" "fully remote" Japan',
    ),
    (
        "source_rescue_search_eval_japanese_nationwide",
        '"Japanese search evaluator" remote Japan',
    ),
    (
        "source_rescue_ai_trainer_jp",
        '"完全在宅" "AIトレーナー" 日本',
    ),
    (
        "source_rescue_ai_rating_jp",
        '"完全在宅" "AI評価" 日本',
    ),
    (
        "source_rescue_annotation_jp",
        '"完全在宅" アノテーション 日本',
    ),
    (
        "source_rescue_ai_rater_generated_jp",
        '"フルリモート" "生成AI" 評価 日本',
    ),
]

core.PROFILE_LEARNING_VERSION = PROFILE_LEARNING_VERSION

_RESCUE_ACTIVE = False
_RESCUE_POOL_SIZE = 0
_RESCUE_WINDOW = 0
_RESCUE_FOCUS_TARGET = 0
_RESCUE_FOCUS_ACTUAL = 0
_RESCUE_PROFILES_ADDED = 0
_RESCUE_SELECTED_PROFILES: list[str] = []


def profile_key(value: object) -> str:
    return core.profile_key(value)


def family_key(value: object) -> str:
    return v7.family_key(value)


def has_learning_signal(payload: dict | None) -> bool:
    return core.has_learning_signal(payload)


def _int(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _pool_size(payload: dict | None) -> int:
    if not isinstance(payload, dict):
        return 0
    for key in ("candidate_pool_size", "pool_before_refresh"):
        if key in payload:
            return _int(payload.get(key))
    jobs = payload.get("jobs") or []
    return len(jobs) if isinstance(jobs, list) else 0


def _window_width(payload: dict | None, profile_count: int) -> int:
    if not isinstance(payload, dict):
        return 0
    for key in (
        "serpapi_effective_request_limit",
        "candidate_search_effective_daily_limit",
        "query_total",
    ):
        value = _int(payload.get(key))
        if value:
            return min(profile_count, value)
    return 0


def is_focus_profile(value: object) -> bool:
    return family_key(value) in FOCUS_FAMILIES


def augment_profiles(
    profiles: Iterable[tuple[str, str]], payload: dict | None = None
) -> list[tuple[str, str]]:
    """Use v7 augmentation and add rescue probes only while server stock is low."""
    global _RESCUE_PROFILES_ADDED
    rows = list(v7.augment_profiles(profiles, payload))
    _RESCUE_PROFILES_ADDED = 0
    if _pool_size(payload) >= LOW_STOCK_POOL_MAX:
        return rows

    seen = {core.profile_key(name) for name, _ in rows}
    for name, query in RESCUE_PROFILES:
        key = core.profile_key(name)
        if key in seen:
            continue
        rows.append((name, query))
        seen.add(key)
        _RESCUE_PROFILES_ADDED += 1
    return rows


def actual_order(
    precompensated: Iterable[tuple[str, str]], payload: dict | None
) -> list[tuple[str, str]]:
    return v7.actual_order(precompensated, payload)


def _precompensate(
    actual: list[tuple[str, str]], payload: dict | None
) -> list[tuple[str, str]]:
    return v7.v6.v5._precompensate(actual, payload)


def _recent_profiles(payload: dict | None) -> set[str]:
    return v7.v6.v4._recently_searched_profiles(payload)


def _seen_for(key: str) -> float:
    return core._number((core._STATE.get(key) or {}).get("seen"))


def _focus_rank(
    item: tuple[str, str],
    index: int,
    recent: set[str],
) -> tuple[int, int, float, float, int, str]:
    name, _ = item
    key = core.profile_key(name)
    seen = _seen_for(key)
    score = core.precision_score(key, core._STATE)
    rescue = 1 if key.startswith("source_rescue_") else 0
    not_recent = 1 if key not in recent else 0
    unseen = 1 if seen <= 0 else 0
    # Prefer a non-recent exact profile, then a fresh rescue/unseen probe, then
    # learned score. Stable original order is the final tie breaker.
    return (not_recent, rescue, unseen, score, -index, key)


def _select_focus_prefix(
    actual: list[tuple[str, str]],
    target: int,
    payload: dict | None,
) -> list[tuple[str, str]]:
    if target <= 0:
        return list(actual)

    indexed = [(index, item) for index, item in enumerate(actual) if is_focus_profile(item[0])]
    recent = _recent_profiles(payload)
    remaining = list(indexed)
    selected: list[tuple[int, tuple[str, str]]] = []
    used_families: set[str] = set()

    while remaining and len(selected) < target:
        diverse = [entry for entry in remaining if family_key(entry[1][0]) not in used_families]
        pool = diverse or remaining
        best = max(pool, key=lambda entry: _focus_rank(entry[1], entry[0], recent))
        selected.append(best)
        remaining.remove(best)
        used_families.add(family_key(best[1][0]))
        if len(used_families) >= len(FOCUS_FAMILIES):
            used_families.clear()

    selected_indexes = {index for index, _ in selected}
    prefix = [item for _, item in selected]
    tail = [item for index, item in enumerate(actual) if index not in selected_indexes]
    return prefix + tail


def _focus_target(pool_size: int, width: int) -> int:
    if width <= 0 or pool_size >= LOW_STOCK_POOL_MAX:
        return 0
    if pool_size <= CRITICAL_POOL_MAX:
        return width
    return min(width, max(1, math.ceil(width * LOW_STOCK_FOCUS_SHARE)))


def order_profiles(
    profiles: Iterable[tuple[str, str]], payload: dict | None
) -> list[tuple[str, str]]:
    """Apply v7 first, then emergency focus only while the server pool is low."""
    global _RESCUE_ACTIVE, _RESCUE_POOL_SIZE, _RESCUE_WINDOW
    global _RESCUE_FOCUS_TARGET, _RESCUE_FOCUS_ACTUAL, _RESCUE_SELECTED_PROFILES

    rows = list(profiles)
    ordered = v7.order_profiles(rows, payload)
    actual = actual_order(ordered, payload)
    pool_size = _pool_size(payload)
    width = _window_width(payload, len(actual))
    target = _focus_target(pool_size, width)

    _RESCUE_POOL_SIZE = pool_size
    _RESCUE_WINDOW = width
    _RESCUE_FOCUS_TARGET = target
    _RESCUE_ACTIVE = target > 0

    if target:
        actual = _select_focus_prefix(actual, target, payload)

    first_window = actual[:width] if width else []
    _RESCUE_SELECTED_PROFILES = [core.profile_key(name) for name, _ in first_window]
    _RESCUE_FOCUS_ACTUAL = sum(1 for name, _ in first_window if is_focus_profile(name))
    return _precompensate(actual, payload)


def learning_metadata(current_payload: dict | None) -> dict:
    metadata = v7.learning_metadata(current_payload)
    metadata["candidate_search_profile_learning_version"] = PROFILE_LEARNING_VERSION
    metadata["candidate_search_precision_policy"] = (
        "v8-critical-low-stock-focus+v7-zero-result+scarce-quality-floor+family-handoff"
    )
    metadata["candidate_search_precision_rescue_active"] = _RESCUE_ACTIVE
    metadata["candidate_search_precision_rescue_pool_size"] = _RESCUE_POOL_SIZE
    metadata["candidate_search_precision_rescue_critical_pool_max"] = CRITICAL_POOL_MAX
    metadata["candidate_search_precision_rescue_low_stock_pool_max"] = LOW_STOCK_POOL_MAX
    metadata["candidate_search_precision_rescue_window"] = _RESCUE_WINDOW
    metadata["candidate_search_precision_rescue_focus_target"] = _RESCUE_FOCUS_TARGET
    metadata["candidate_search_precision_rescue_focus_actual"] = _RESCUE_FOCUS_ACTUAL
    metadata["candidate_search_precision_rescue_focus_share_target_pct"] = (
        100.0 if _RESCUE_POOL_SIZE <= CRITICAL_POOL_MAX else LOW_STOCK_FOCUS_SHARE * 100
    )
    metadata["candidate_search_precision_rescue_profiles_added"] = _RESCUE_PROFILES_ADDED
    metadata["candidate_search_precision_rescue_selected_profiles"] = list(
        _RESCUE_SELECTED_PROFILES
    )[:7]
    metadata["candidate_search_precision_rescue_focus_families"] = sorted(FOCUS_FAMILIES)
    metadata["candidate_search_precision_rescue_behavior"] = (
        "critical-pool-all-focus;low-stock-three-quarters-focus;normal-at-30"
    )
    return metadata
