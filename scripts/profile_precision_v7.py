#!/usr/bin/env python3
"""Zero-result-aware search-profile learning layered on precision v6.

V6 avoids profiles already known to be poor, but the profile-yield telemetry only
contained profiles that returned at least one job row. A successful search that
returned zero rows therefore looked "unseen" forever and could be selected again
without any empirical penalty.

V7 adds two bounded aggregate signals:
- search_attempts: successful/failed first-page profile attempts observed by the
  production wrapper;
- zero_result_attempts: successful first-page attempts that returned zero rows.

Zero-result feedback is deliberately a modest penalty. One empty search should
not permanently kill a high-intent profile, while repeated empty searches should
make other unexplored/healthy profiles more attractive. Provider failures are
tracked separately and are not treated as zero-result evidence.

Request counts, monthly/provider guards, query text, publication thresholds,
remote/presence/AI-use rules, LLM vetoes and validators remain unchanged.
"""
from __future__ import annotations

from typing import Iterable

import profile_precision as core
import profile_precision_v6 as v6

PROFILE_LEARNING_VERSION = 7
SEARCH_ATTEMPT_FIELD = "search_attempts"
ZERO_RESULT_FIELD = "zero_result_attempts"
ZERO_RESULT_PENALTY = 32.0
ZERO_RESULT_CONFIDENCE_ATTEMPTS = 4.0

for field in (SEARCH_ATTEMPT_FIELD, ZERO_RESULT_FIELD):
    if field not in core.STAT_FIELDS:
        core.STAT_FIELDS = tuple(core.STAT_FIELDS) + (field,)
core.PROFILE_LEARNING_VERSION = PROFILE_LEARNING_VERSION

_ORIGINAL_BUILD_LEARNING = core.build_learning
_ORIGINAL_PRECISION_SCORE = core.precision_score


def _fold_needed(payload: dict | None) -> bool:
    if not isinstance(payload, dict):
        return False
    generated = str(payload.get("generated_at") or "")
    through = str(payload.get("candidate_search_profile_learning_through") or "")
    if not generated or generated == through:
        return False
    rows = payload.get("candidate_search_profile_yield") or []
    return isinstance(rows, list) and bool(rows)


def build_learning(payload: dict | None) -> tuple[dict[str, dict[str, float]], str]:
    should_fold = _fold_needed(payload)
    history, through = _ORIGINAL_BUILD_LEARNING(payload)
    if not should_fold or not isinstance(payload, dict):
        return history, through

    for item in payload.get("candidate_search_profile_yield") or []:
        if not isinstance(item, dict):
            continue
        key = core.profile_key(item.get("profile"))
        if not key or key == "unknown":
            continue
        attempts = core._number(item.get(SEARCH_ATTEMPT_FIELD))
        zeros = core._number(item.get(ZERO_RESULT_FIELD))
        if attempts:
            core._add(history, key, SEARCH_ATTEMPT_FIELD, attempts)
        if zeros:
            core._add(history, key, ZERO_RESULT_FIELD, min(zeros, attempts or zeros))
    return history, through


def precision_score(profile: object, history: dict[str, dict[str, float]]) -> float:
    score = _ORIGINAL_PRECISION_SCORE(profile, history)
    key = core.profile_key(profile)
    stats = history.get(key) or {}
    attempts = core._number(stats.get(SEARCH_ATTEMPT_FIELD))
    zeros = core._number(stats.get(ZERO_RESULT_FIELD))
    if attempts <= 0 or zeros <= 0:
        return score

    zero_rate = min(1.0, zeros / attempts)
    confidence = min(1.0, attempts / ZERO_RESULT_CONFIDENCE_ATTEMPTS)
    weight = 0.40 + 0.60 * confidence
    return score - ZERO_RESULT_PENALTY * zero_rate * weight


core.build_learning = build_learning
core.precision_score = precision_score


def profile_key(value: object) -> str:
    return core.profile_key(value)


def family_key(value: object) -> str:
    return v6.family_key(value)


def has_learning_signal(payload: dict | None) -> bool:
    return core.has_learning_signal(payload)


def augment_profiles(
    profiles: Iterable[tuple[str, str]], payload: dict | None = None
) -> list[tuple[str, str]]:
    return v6.augment_profiles(profiles, payload)


def actual_order(
    precompensated: Iterable[tuple[str, str]], payload: dict | None
) -> list[tuple[str, str]]:
    return v6.v5._actual_order(list(precompensated), payload)


def order_profiles(
    profiles: Iterable[tuple[str, str]], payload: dict | None
) -> list[tuple[str, str]]:
    return v6.order_profiles(profiles, payload)


def learning_metadata(current_payload: dict | None) -> dict:
    metadata = v6.learning_metadata(current_payload)
    metadata["candidate_search_profile_learning_version"] = PROFILE_LEARNING_VERSION
    metadata["candidate_search_precision_policy"] = (
        "v7-zero-result-aware+scarce-quality-floor+family-handoff+guarded-champion"
    )
    metadata["candidate_search_precision_zero_result_penalty"] = ZERO_RESULT_PENALTY
    metadata["candidate_search_precision_zero_result_confidence_attempts"] = (
        ZERO_RESULT_CONFIDENCE_ATTEMPTS
    )
    metadata["candidate_search_precision_zero_result_behavior"] = (
        "penalize-successful-empty-profile-without-penalizing-provider-failure"
    )
    return metadata
