#!/usr/bin/env python3
"""Scarce-window quality floor layered on search precision v5.

V5 rotates a fatigued exact champion into a different query within a proven task
family. Production telemetry then exposed one remaining inefficiency: when
monthly pacing leaves only two or three searches, the exploration slot can still
land on a profile whose accumulated precision score is already strongly negative.

V6 keeps exploration, but does not spend a scarce slot on a known-bad profile if
an untried or materially stronger profile from a different family is available.
It only reorders existing/approved discovery profiles. Request counts, monthly
and provider budgets, publication thresholds, remote/presence rules, AI-use
policy rules, LLM vetoes and validators remain unchanged.
"""
from __future__ import annotations

from typing import Iterable

import profile_precision as core
import profile_precision_v4 as v4
import profile_precision_v5 as v5

PROFILE_LEARNING_VERSION = 6
SCARCE_WINDOW_MAX = 3
SCARCE_SLOT_MIN_SCORE = -5.0
SCARCE_REPLACEMENT_MIN_SCORE = 12.0

core.PROFILE_LEARNING_VERSION = PROFILE_LEARNING_VERSION

_SCARCE_GUARD_ACTIVE = False
_SCARCE_GUARD_WIDTH = 0
_SCARCE_REPLACEMENTS: list[dict[str, object]] = []


def profile_key(value: object) -> str:
    return core.profile_key(value)


def family_key(value: object) -> str:
    return v5.family_key(value)


def has_learning_signal(payload: dict | None) -> bool:
    return core.has_learning_signal(payload)


def augment_profiles(
    profiles: Iterable[tuple[str, str]], payload: dict | None = None
) -> list[tuple[str, str]]:
    return v5.augment_profiles(profiles, payload)


def _scarce_width(payload: dict | None) -> int:
    if not isinstance(payload, dict):
        return 0
    for key in (
        "serpapi_effective_request_limit",
        "candidate_search_effective_daily_limit",
        "query_total",
    ):
        try:
            value = max(0, int(payload.get(key) or 0))
        except (TypeError, ValueError):
            value = 0
        if value:
            return value
    return 0


def _seen_for(key: str) -> float:
    return core._number((core._STATE.get(key) or {}).get("seen"))


def _replacement_candidate(
    actual: list[tuple[str, str]],
    start_index: int,
    blocked_families: set[str],
    recent_profiles: set[str],
) -> int | None:
    ranked: list[tuple[int, float, float, str, int]] = []
    for index in range(start_index, len(actual)):
        name, _ = actual[index]
        key = core.profile_key(name)
        if key in recent_profiles:
            continue
        family = family_key(key)
        if family in blocked_families:
            continue
        score = core.precision_score(key, core._STATE)
        if score < SCARCE_REPLACEMENT_MIN_SCORE:
            continue
        seen = _seen_for(key)
        unseen = 1 if seen <= 0.0 else 0
        # Preserve exploration by preferring an unseen positive-prior profile;
        # if all eligible alternatives have history, use the strongest score.
        ranked.append((unseen, score, -seen, key, index))
    if not ranked:
        return None
    ranked.sort(key=lambda item: (-item[0], -item[1], -item[2], item[3]))
    return ranked[0][4]


def _guard_scarce_window(
    actual: list[tuple[str, str]], payload: dict | None
) -> list[tuple[str, str]]:
    global _SCARCE_GUARD_ACTIVE, _SCARCE_GUARD_WIDTH, _SCARCE_REPLACEMENTS
    _SCARCE_GUARD_ACTIVE = False
    _SCARCE_GUARD_WIDTH = 0
    _SCARCE_REPLACEMENTS = []

    if not actual or not isinstance(payload, dict):
        return actual
    if payload.get("pool_under_display_target") is False:
        return actual

    width = min(len(actual), _scarce_width(payload))
    if width <= 0 or width > SCARCE_WINDOW_MAX:
        return actual

    _SCARCE_GUARD_ACTIVE = True
    _SCARCE_GUARD_WIDTH = width
    recent_profiles = v4._recently_searched_profiles(payload)
    blocked_families: set[str] = set()

    for slot in range(width):
        current_name, _ = actual[slot]
        current_key = core.profile_key(current_name)
        current_family = family_key(current_key)
        current_score = core.precision_score(current_key, core._STATE)

        # Keep a healthy/unknown exploration slot. The guard only replaces a
        # profile that history already marks as materially weak.
        if current_score >= SCARCE_SLOT_MIN_SCORE:
            blocked_families.add(current_family)
            continue

        replacement_index = _replacement_candidate(
            actual,
            slot + 1,
            blocked_families,
            recent_profiles,
        )
        if replacement_index is None:
            blocked_families.add(current_family)
            continue

        replacement_name, _ = actual[replacement_index]
        replacement_key = core.profile_key(replacement_name)
        replacement_score = core.precision_score(replacement_key, core._STATE)
        actual[slot], actual[replacement_index] = actual[replacement_index], actual[slot]
        _SCARCE_REPLACEMENTS.append(
            {
                "slot": slot + 1,
                "from_profile": current_key,
                "from_score": round(current_score, 2),
                "to_profile": replacement_key,
                "to_score": round(replacement_score, 2),
                "to_family": family_key(replacement_key),
                "to_seen": round(_seen_for(replacement_key), 3),
            }
        )
        blocked_families.add(family_key(replacement_key))

    return actual


def order_profiles(
    profiles: Iterable[tuple[str, str]], payload: dict | None
) -> list[tuple[str, str]]:
    rows = list(profiles)
    ordered = v5.order_profiles(rows, payload)
    actual = v5._actual_order(ordered, payload)
    actual = _guard_scarce_window(actual, payload)
    return v5._precompensate(actual, payload)


def learning_metadata(current_payload: dict | None) -> dict:
    metadata = v5.learning_metadata(current_payload)
    metadata["candidate_search_profile_learning_version"] = PROFILE_LEARNING_VERSION
    metadata["candidate_search_precision_policy"] = (
        "v6-scarce-quality-floor+family-handoff+guarded-champion"
    )
    metadata["candidate_search_precision_scarce_guard_active"] = _SCARCE_GUARD_ACTIVE
    metadata["candidate_search_precision_scarce_guard_max_window"] = SCARCE_WINDOW_MAX
    metadata["candidate_search_precision_scarce_guard_window"] = _SCARCE_GUARD_WIDTH
    metadata["candidate_search_precision_scarce_slot_min_score"] = SCARCE_SLOT_MIN_SCORE
    metadata["candidate_search_precision_scarce_replacement_min_score"] = (
        SCARCE_REPLACEMENT_MIN_SCORE
    )
    metadata["candidate_search_precision_scarce_replacements"] = list(_SCARCE_REPLACEMENTS)[:3]
    metadata["candidate_search_precision_scarce_guard_behavior"] = (
        "replace-known-negative-slot-with-unseen-or-stronger-different-family"
    )
    return metadata
