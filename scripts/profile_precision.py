#!/usr/bin/env python3
"""Adaptive, privacy-safe search-profile precision learning.

This module changes only *which existing discovery profiles are searched first*.
It never changes publication thresholds, remote/presence rules, LLM vetoes, or
API budget limits.

The learner uses only bounded aggregate telemetry already safe to publish:
- rows seen per profile;
- Indeed apply-path yield;
- deterministic quality-gate acceptance;
- coarse rejection reasons; and
- final non-carryover survivors by profile.

Historical counts decay so old behavior cannot dominate forever. Search order
keeps a one-third exploration lane so low-scoring or unseen profiles are never
permanently starved. The legacy rotation cursor is aligned to the learned cycle,
while an independent precision phase advances after each run.
"""
from __future__ import annotations

import re
from typing import Iterable

PROFILE_LEARNING_VERSION = 1
PROFILE_HISTORY_LIMIT = 96
HISTORY_DECAY = 0.82
EXPLOIT_SLOTS = 2
EXPLORE_SLOTS = 1

HARD_REJECTION_REASONS = {
    "synchronous-human-attention",
    "partial-or-conditional-remote",
    "ongoing-human-coordination",
    "continuous-human-presence",
    "missing-explicit-full-remote",
    "remote-search-only",
    "review-human-risk-above-ceiling",
}
SOFT_REJECTION_REASONS = {
    "score-below-candidate-floor",
    "review-automation-below-floor",
    "review-insufficient-automation-signals",
}

# These two exact profiles are the only source-recovery profiles that produced
# deterministic candidates in the first successful v2 production recovery run.
# The bonus is intentionally modest; live telemetry can override it quickly.
PROVEN_PROFILE_BONUS = {
    "source_ai_trainer_remote": 45.0,
    "source_annotation_remote": 35.0,
}

TOKEN_PRIORS: tuple[tuple[str, float], ...] = (
    ("ai_trainer", 35.0),
    ("ai_rater", 30.0),
    ("ai_rating", 30.0),
    ("model_response", 28.0),
    ("prompt_eval", 25.0),
    ("annotation", 28.0),
    ("search_eval", 20.0),
    ("rater", 16.0),
    ("labeling", 15.0),
    ("ocr", 10.0),
    ("data_check", 8.0),
    ("metadata", 6.0),
    ("data_entry", -5.0),
    ("proofreading", -6.0),
    ("transcription", -6.0),
    ("testing", -7.0),
    ("document_check", -4.0),
)

STAT_FIELDS = (
    "seen",
    "indeed_apply",
    "accepted",
    "final_survivors",
    "hard_rejections",
    "no_indeed",
    "soft_rejections",
    "observed_runs",
)

_STATE: dict[str, dict[str, float]] = {}
_ACTIVE = False
_PHASE_START = 0
_PROFILE_COUNT = 0
_PRIORITY_KEYS: list[str] = []
_LEARNING_THROUGH = ""


def _number(value: object) -> float:
    if isinstance(value, bool):
        return 0.0
    try:
        return max(0.0, float(value or 0.0))
    except (TypeError, ValueError):
        return 0.0


def _int(value: object) -> int:
    return int(_number(value))


def profile_key(value: object) -> str:
    """Normalize rotating anchor suffixes without broadening profile identity."""
    name = str(value or "unknown")[:80]
    if name.startswith("anchor_"):
        name = re.sub(r"_\d{2,3}$", "", name)
    return name


def _empty_stats() -> dict[str, float]:
    return {field: 0.0 for field in STAT_FIELDS}


def _stored_history(payload: dict | None) -> dict[str, dict[str, float]]:
    history: dict[str, dict[str, float]] = {}
    if not isinstance(payload, dict):
        return history
    rows = payload.get("candidate_search_profile_learning") or []
    if not isinstance(rows, list):
        return history
    for item in rows:
        if not isinstance(item, dict):
            continue
        key = profile_key(item.get("profile"))
        if not key or key == "unknown":
            continue
        stats = _empty_stats()
        for field in STAT_FIELDS:
            stats[field] = _number(item.get(field))
        history[key] = stats
    return history


def _decay(history: dict[str, dict[str, float]]) -> None:
    for stats in history.values():
        for field in STAT_FIELDS:
            stats[field] = round(_number(stats.get(field)) * HISTORY_DECAY, 4)


def _add(history: dict[str, dict[str, float]], key: str, field: str, amount: float) -> None:
    stats = history.setdefault(key, _empty_stats())
    stats[field] = _number(stats.get(field)) + max(0.0, amount)


def _fold_previous_run(
    history: dict[str, dict[str, float]], payload: dict | None
) -> tuple[dict[str, dict[str, float]], str]:
    if not isinstance(payload, dict):
        return history, ""

    generated = str(payload.get("generated_at") or "")
    already_through = str(payload.get("candidate_search_profile_learning_through") or "")
    if generated and already_through == generated:
        return history, generated

    yield_rows = payload.get("candidate_search_profile_yield") or []
    quality_rows = payload.get("candidate_quality_rejection_by_profile") or []
    has_run_signal = isinstance(yield_rows, list) and bool(yield_rows)
    has_run_signal = has_run_signal or (isinstance(quality_rows, list) and bool(quality_rows))
    if not has_run_signal:
        return history, already_through

    _decay(history)
    observed: set[str] = set()
    seen_by_key: dict[str, float] = {}

    if isinstance(yield_rows, list):
        for item in yield_rows:
            if not isinstance(item, dict):
                continue
            key = profile_key(item.get("profile"))
            observed.add(key)
            seen = _number(item.get("seen"))
            seen_by_key[key] = max(seen_by_key.get(key, 0.0), seen)
            _add(history, key, "indeed_apply", _number(item.get("indeed_apply")))
            _add(history, key, "accepted", _number(item.get("accepted")))

    if isinstance(quality_rows, list):
        for item in quality_rows:
            if not isinstance(item, dict):
                continue
            key = profile_key(item.get("profile"))
            observed.add(key)
            seen_by_key[key] = max(seen_by_key.get(key, 0.0), _number(item.get("evaluated")))
            reasons = item.get("reasons") or {}
            if not isinstance(reasons, dict):
                continue
            _add(history, key, "no_indeed", _number(reasons.get("no-indeed-apply")))
            _add(
                history,
                key,
                "hard_rejections",
                sum(_number(reasons.get(reason)) for reason in HARD_REJECTION_REASONS),
            )
            _add(
                history,
                key,
                "soft_rejections",
                sum(_number(reasons.get(reason)) for reason in SOFT_REJECTION_REASONS),
            )

    for key, seen in seen_by_key.items():
        _add(history, key, "seen", seen)

    # A final survivor is stronger evidence than a pre-LLM acceptance. Do not
    # repeatedly reward carryover rows that were not rediscovered in this run.
    for row in payload.get("jobs") or []:
        if not isinstance(row, dict) or row.get("carryover"):
            continue
        key = profile_key(row.get("category"))
        if key and key != "unknown":
            _add(history, key, "final_survivors", 1.0)

    for key in observed:
        if key and key != "unknown":
            _add(history, key, "observed_runs", 1.0)

    return history, generated or already_through


def build_learning(payload: dict | None) -> tuple[dict[str, dict[str, float]], str]:
    history = _stored_history(payload)
    return _fold_previous_run(history, payload)


def _base_prior(key: str) -> float:
    score = PROVEN_PROFILE_BONUS.get(key, 0.0)
    if key.startswith("source_"):
        score += 5.0
    if key.startswith("anchor_indeed_"):
        score += 4.0
    for token, weight in TOKEN_PRIORS:
        if token in key:
            score += weight
    return score


def precision_score(profile: object, history: dict[str, dict[str, float]]) -> float:
    key = profile_key(profile)
    prior = _base_prior(key)
    stats = history.get(key) or {}
    seen = _number(stats.get("seen"))
    if seen <= 0:
        return prior

    accepted_rate = min(1.0, _number(stats.get("accepted")) / seen)
    final_rate = min(1.0, _number(stats.get("final_survivors")) / seen)
    indeed_rate = min(1.0, _number(stats.get("indeed_apply")) / seen)
    hard_rate = min(1.0, _number(stats.get("hard_rejections")) / seen)
    no_indeed_rate = min(1.0, _number(stats.get("no_indeed")) / seen)
    soft_rate = min(1.0, _number(stats.get("soft_rejections")) / seen)

    empirical = (
        500.0 * final_rate
        + 180.0 * accepted_rate
        + 45.0 * indeed_rate
        - 120.0 * hard_rate
        - 35.0 * no_indeed_rate
        - 30.0 * soft_rate
    )
    confidence = min(1.0, seen / 20.0)
    # Even a small sample may inform ordering, but cannot instantly dominate a
    # strong task prior. At 20+ observed rows empirical evidence gets full weight.
    empirical_weight = 0.35 + 0.65 * confidence
    return prior + empirical * empirical_weight


def _precision_cycle(
    profiles: list[tuple[str, str]], history: dict[str, dict[str, float]]
) -> tuple[list[tuple[str, str]], list[str]]:
    indexed = list(enumerate(profiles))
    ranked = sorted(
        indexed,
        key=lambda item: (
            -precision_score(item[1][0], history),
            item[0],
        ),
    )
    ranked_profiles = [item[1] for item in ranked]
    if len(ranked_profiles) <= 2:
        return ranked_profiles, [profile_key(name) for name, _ in ranked_profiles]

    preferred_count = max(
        1,
        min(
            len(ranked_profiles),
            (len(ranked_profiles) * EXPLOIT_SLOTS + (EXPLOIT_SLOTS + EXPLORE_SLOTS - 1))
            // (EXPLOIT_SLOTS + EXPLORE_SLOTS),
        ),
    )
    preferred = ranked_profiles[:preferred_count]
    exploration = ranked_profiles[preferred_count:]
    preferred_keys = [profile_key(name) for name, _ in preferred]

    cycle: list[tuple[str, str]] = []
    p = 0
    e = 0
    while p < len(preferred) or e < len(exploration):
        for _ in range(EXPLOIT_SLOTS):
            if p < len(preferred):
                cycle.append(preferred[p])
                p += 1
        if e < len(exploration):
            cycle.append(exploration[e])
            e += 1
    return cycle, preferred_keys


def has_learning_signal(payload: dict | None) -> bool:
    if not isinstance(payload, dict):
        return False
    for key in (
        "candidate_search_profile_learning",
        "candidate_search_profile_yield",
        "candidate_quality_rejection_by_profile",
    ):
        value = payload.get(key)
        if isinstance(value, list) and value:
            return True
    return False


def order_profiles(
    profiles: Iterable[tuple[str, str]], payload: dict | None
) -> list[tuple[str, str]]:
    """Return adaptive exploit/explore order while honoring legacy cursor math."""
    global _STATE, _ACTIVE, _PHASE_START, _PROFILE_COUNT, _PRIORITY_KEYS, _LEARNING_THROUGH

    rows = list(profiles)
    _PROFILE_COUNT = len(rows)
    _PRIORITY_KEYS = []
    _PHASE_START = 0
    _ACTIVE = bool(rows) and has_learning_signal(payload)
    _STATE, _LEARNING_THROUGH = build_learning(payload)
    if not _ACTIVE or len(rows) < 2:
        return rows

    cycle, preferred_keys = _precision_cycle(rows, _STATE)
    _PRIORITY_KEYS = preferred_keys
    phase = _int((payload or {}).get("candidate_search_precision_phase")) % len(cycle)
    _PHASE_START = phase
    phase_cycle = cycle[phase:] + cycle[:phase]

    # acquisition.main later rotates QUERY_PROFILES by serpapi_rotation_cursor.
    # Shift the stored list in the opposite direction so the *actual* first
    # search is phase_cycle[0], independent of the legacy cursor value.
    legacy_cursor = _int((payload or {}).get("serpapi_rotation_cursor")) % len(cycle)
    if legacy_cursor:
        return phase_cycle[-legacy_cursor:] + phase_cycle[:-legacy_cursor]
    return phase_cycle


def _history_rows() -> list[dict]:
    ranked = sorted(
        _STATE.items(),
        key=lambda item: (
            -precision_score(item[0], _STATE),
            -_number(item[1].get("seen")),
            item[0],
        ),
    )[:PROFILE_HISTORY_LIMIT]
    rows: list[dict] = []
    for key, stats in ranked:
        row = {"profile": key}
        for field in STAT_FIELDS:
            value = round(_number(stats.get(field)), 3)
            if value:
                row[field] = value
        row["precision_score"] = round(precision_score(key, _STATE), 2)
        rows.append(row)
    return rows


def learning_metadata(current_payload: dict | None) -> dict:
    query_total = _int((current_payload or {}).get("query_total"))
    next_phase = 0
    if _PROFILE_COUNT:
        next_phase = (_PHASE_START + min(query_total, _PROFILE_COUNT)) % _PROFILE_COUNT
    preferred_preview = _PRIORITY_KEYS[:12]
    return {
        "candidate_search_profile_learning_version": PROFILE_LEARNING_VERSION,
        "candidate_search_profile_learning_active": _ACTIVE,
        "candidate_search_profile_learning_through": _LEARNING_THROUGH or None,
        "candidate_search_profile_learning": _history_rows(),
        "candidate_search_precision_policy": "two-exploit-one-explore-v1",
        "candidate_search_precision_empirical_signals": (
            "indeed-yield+deterministic-accept+final-survivor+coarse-rejections"
        ),
        "candidate_search_precision_exploration_share_pct": round(
            EXPLORE_SLOTS * 100 / (EXPLOIT_SLOTS + EXPLORE_SLOTS), 1
        ),
        "candidate_search_precision_profile_count": _PROFILE_COUNT,
        "candidate_search_precision_priority_profiles": preferred_preview,
        "candidate_search_precision_phase": next_phase,
    }
