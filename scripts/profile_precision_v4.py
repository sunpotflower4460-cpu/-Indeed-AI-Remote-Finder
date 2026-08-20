#!/usr/bin/env python3
"""Guarded champion-slot ordering for scarce adaptive search windows.

V3 prevents adjacent searches from collapsing onto the same task family. V4 adds
one bounded exploitation refinement: when an exact query profile has previously
produced a final live candidate and still has a strong precision score, prefer
that exact profile for the first actual search slot.

The champion is intentionally not sticky. If that exact profile was searched in
the immediately previous run and did not produce a *new* final survivor, it is
suppressed for the next run. This avoids spending half of a two-request paced
window repeatedly rediscovering the same listing.

Only ordering changes. Query text, request counts, monthly/provider guards,
publication thresholds, presence rules, LLM vetoes, validators and the existing
family-diverse exploration policy remain untouched.
"""
from __future__ import annotations

from typing import Iterable

import profile_precision as core
import profile_precision_v3 as v3

PROFILE_LEARNING_VERSION = 4
CHAMPION_MIN_SCORE = 80.0
CHAMPION_MIN_FINAL_SURVIVORS = 0.5

core.PROFILE_LEARNING_VERSION = PROFILE_LEARNING_VERSION

_SELECTED_CHAMPION: str | None = None
_SELECTED_CHAMPION_SCORE: float | None = None
_CHAMPION_SUPPRESSION_REASON = "none"


def _row_is_new(row: dict) -> bool:
    if not isinstance(row, dict) or row.get("carryover"):
        return False
    try:
        seen_count = int(row.get("seen_count") or 0)
    except (TypeError, ValueError):
        seen_count = 0
    if seen_count == 1:
        return True
    if seen_count > 1:
        return False
    first_seen = str(row.get("first_seen") or "").strip()
    last_seen = str(row.get("last_seen") or "").strip()
    return bool(first_seen and last_seen and first_seen == last_seen)


def _recently_searched_profiles(payload: dict | None) -> set[str]:
    if not isinstance(payload, dict):
        return set()
    rows = payload.get("candidate_search_profile_yield") or []
    if not isinstance(rows, list):
        return set()
    return {
        core.profile_key(item.get("profile"))
        for item in rows
        if isinstance(item, dict)
    }


def _new_final_survivor_profiles(payload: dict | None) -> set[str]:
    if not isinstance(payload, dict):
        return set()
    rows = payload.get("jobs") or []
    if not isinstance(rows, list):
        return set()
    return {
        core.profile_key(row.get("category"))
        for row in rows
        if isinstance(row, dict) and _row_is_new(row)
    }


def _champion_candidate(
    profiles: list[tuple[str, str]], payload: dict | None
) -> tuple[str, float] | None:
    """Return one exact-profile champion, or None when freshness guard suppresses it."""
    global _CHAMPION_SUPPRESSION_REASON

    if not profiles or not isinstance(payload, dict):
        _CHAMPION_SUPPRESSION_REASON = "no-profile-or-telemetry"
        return None
    if payload.get("pool_under_display_target") is False:
        _CHAMPION_SUPPRESSION_REASON = "pool-target-met"
        return None

    available = {core.profile_key(name) for name, _ in profiles}
    recent = _recently_searched_profiles(payload)
    new_survivors = _new_final_survivor_profiles(payload)

    ranked: list[tuple[float, str]] = []
    for key in available:
        stats = core._STATE.get(key) or {}
        final_survivors = core._number(stats.get("final_survivors"))
        if final_survivors < CHAMPION_MIN_FINAL_SURVIVORS:
            continue
        score = core.precision_score(key, core._STATE)
        if score < CHAMPION_MIN_SCORE:
            continue
        ranked.append((score, key))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    if not ranked:
        _CHAMPION_SUPPRESSION_REASON = "no-eligible-champion"
        return None

    for score, key in ranked:
        # Immediate fatigue guard: if this exact query was just spent and did not
        # create a genuinely new final survivor, give the next run to other
        # profiles. Rediscovering an existing live row does not count as novel.
        if key in recent and key not in new_survivors:
            continue
        _CHAMPION_SUPPRESSION_REASON = "none"
        return key, score

    _CHAMPION_SUPPRESSION_REASON = "recent-search-no-new-survivor"
    return None


def _actual_order(precompensated: list[tuple[str, str]], payload: dict | None) -> list[tuple[str, str]]:
    if not precompensated:
        return []
    cursor = int(core._number((payload or {}).get("serpapi_rotation_cursor"))) % len(precompensated)
    if not cursor:
        return list(precompensated)
    return precompensated[cursor:] + precompensated[:cursor]


def _precompensate(actual: list[tuple[str, str]], payload: dict | None) -> list[tuple[str, str]]:
    if not actual:
        return []
    cursor = int(core._number((payload or {}).get("serpapi_rotation_cursor"))) % len(actual)
    if not cursor:
        return list(actual)
    return actual[-cursor:] + actual[:-cursor]


def _promote_champion(
    actual: list[tuple[str, str]], champion_key: str
) -> list[tuple[str, str]]:
    selected_index = None
    for index, (name, _) in enumerate(actual):
        if core.profile_key(name) == champion_key:
            selected_index = index
            break
    if selected_index is None or selected_index == 0:
        return actual

    champion = actual.pop(selected_index)
    actual.insert(0, champion)

    # Keep v3's scarce-window diversity invariant after moving the champion:
    # if slot 2 shares the champion family and an alternative exists, move the
    # first alternative family into slot 2. No profile is removed.
    if len(actual) > 1:
        champion_family = v3.family_key(champion[0])
        if v3.family_key(actual[1][0]) == champion_family:
            for index in range(2, len(actual)):
                if v3.family_key(actual[index][0]) != champion_family:
                    actual.insert(1, actual.pop(index))
                    break
    return actual


def profile_key(value: object) -> str:
    return core.profile_key(value)


def has_learning_signal(payload: dict | None) -> bool:
    return core.has_learning_signal(payload)


def order_profiles(
    profiles: Iterable[tuple[str, str]], payload: dict | None
) -> list[tuple[str, str]]:
    global _SELECTED_CHAMPION, _SELECTED_CHAMPION_SCORE, _CHAMPION_SUPPRESSION_REASON
    _SELECTED_CHAMPION = None
    _SELECTED_CHAMPION_SCORE = None
    _CHAMPION_SUPPRESSION_REASON = "none"

    rows = list(profiles)
    ordered = v3.order_profiles(rows, payload)
    champion = _champion_candidate(rows, payload)
    if champion is None:
        return ordered

    champion_key, champion_score = champion
    actual = _actual_order(ordered, payload)
    actual = _promote_champion(actual, champion_key)
    _SELECTED_CHAMPION = champion_key
    _SELECTED_CHAMPION_SCORE = round(champion_score, 2)
    return _precompensate(actual, payload)


def learning_metadata(current_payload: dict | None) -> dict:
    metadata = v3.learning_metadata(current_payload)
    metadata["candidate_search_profile_learning_version"] = PROFILE_LEARNING_VERSION
    metadata["candidate_search_precision_policy"] = (
        "v4-guarded-champion+family-diverse-final-outcome"
    )
    metadata["candidate_search_precision_champion_min_score"] = CHAMPION_MIN_SCORE
    metadata["candidate_search_precision_champion_min_final_survivors"] = (
        CHAMPION_MIN_FINAL_SURVIVORS
    )
    metadata["candidate_search_precision_champion_profile"] = _SELECTED_CHAMPION
    metadata["candidate_search_precision_champion_score"] = _SELECTED_CHAMPION_SCORE
    metadata["candidate_search_precision_champion_suppression_reason"] = (
        _CHAMPION_SUPPRESSION_REASON
    )
    metadata["candidate_search_precision_champion_fatigue_guard"] = (
        "suppress-after-immediate-search-without-new-final-survivor"
    )
    return metadata
