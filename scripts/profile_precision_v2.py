#!/usr/bin/env python3
"""Final-outcome-aware adaptive search-profile precision learning.

This module extends profile_precision.py without changing any discovery query,
publication threshold, remote/presence rule, LLM veto, or provider budget.

The v1 learner rewards deterministic acceptance and final live survivors. V2
also measures *post-gate loss*: deterministic candidates returned by a profile
that do not survive into the final non-carryover feed. That captures LLM vetoes,
presence vetoes, deduplication and other downstream losses without persisting
candidate titles, companies, descriptions, URLs or IDs.

Because a post-gate loss can have several causes, it is treated as a bounded
precision penalty rather than as proof that the underlying query is invalid.
The existing one-third exploration lane remains unchanged.
"""
from __future__ import annotations

from collections import Counter
from typing import Iterable

import profile_precision as base

PROFILE_LEARNING_VERSION = 2
POST_GATE_LOSS_FIELD = "post_gate_losses"
POST_GATE_LOSS_PENALTY = 300.0

# Extend the stored aggregate schema before v1 helpers allocate/read stats.
if POST_GATE_LOSS_FIELD not in base.STAT_FIELDS:
    base.STAT_FIELDS = tuple(base.STAT_FIELDS) + (POST_GATE_LOSS_FIELD,)
base.PROFILE_LEARNING_VERSION = PROFILE_LEARNING_VERSION

_ORIGINAL_BUILD_LEARNING = base.build_learning
_ORIGINAL_PRECISION_SCORE = base.precision_score
_ORIGINAL_LEARNING_METADATA = base.learning_metadata


def _fold_needed(payload: dict | None) -> bool:
    if not isinstance(payload, dict):
        return False
    generated = str(payload.get("generated_at") or "")
    already_through = str(payload.get("candidate_search_profile_learning_through") or "")
    if not generated or generated == already_through:
        return False
    yield_rows = payload.get("candidate_search_profile_yield") or []
    quality_rows = payload.get("candidate_quality_rejection_by_profile") or []
    return bool(
        (isinstance(yield_rows, list) and yield_rows)
        or (isinstance(quality_rows, list) and quality_rows)
    )


def _accepted_by_profile(payload: dict) -> Counter[str]:
    accepted: Counter[str] = Counter()
    rows = payload.get("candidate_search_profile_yield") or []
    if isinstance(rows, list):
        for item in rows:
            if not isinstance(item, dict):
                continue
            key = base.profile_key(item.get("profile"))
            if key and key != "unknown":
                accepted[key] = max(
                    accepted[key],
                    int(base._number(item.get("accepted"))),
                )

    # Quality telemetry is an independent source of the same pre-LLM outcome.
    # Use max rather than sum so the two telemetry views cannot double count.
    rows = payload.get("candidate_quality_rejection_by_profile") or []
    if isinstance(rows, list):
        for item in rows:
            if not isinstance(item, dict):
                continue
            key = base.profile_key(item.get("profile"))
            if key and key != "unknown":
                accepted[key] = max(
                    accepted[key],
                    int(base._number(item.get("accepted"))),
                )
    return accepted


def _final_live_survivors_by_profile(payload: dict) -> Counter[str]:
    survivors: Counter[str] = Counter()
    rows = payload.get("jobs") or []
    if not isinstance(rows, list):
        return survivors
    for row in rows:
        if not isinstance(row, dict) or row.get("carryover"):
            continue
        key = base.profile_key(row.get("category"))
        if key and key != "unknown":
            survivors[key] += 1
    return survivors


def build_learning(payload: dict | None) -> tuple[dict[str, dict[str, float]], str]:
    """Fold v1 signals plus bounded downstream-loss feedback exactly once."""
    should_fold = _fold_needed(payload)
    history, through = _ORIGINAL_BUILD_LEARNING(payload)
    if not should_fold or not isinstance(payload, dict):
        return history, through

    accepted = _accepted_by_profile(payload)
    survivors = _final_live_survivors_by_profile(payload)
    for key, count in accepted.items():
        loss = max(0, int(count) - int(survivors.get(key, 0)))
        if loss:
            base._add(history, key, POST_GATE_LOSS_FIELD, float(loss))
    return history, through


def precision_score(profile: object, history: dict[str, dict[str, float]]) -> float:
    """Apply a strong but sample-weighted penalty for downstream candidate loss."""
    score = _ORIGINAL_PRECISION_SCORE(profile, history)
    key = base.profile_key(profile)
    stats = history.get(key) or {}
    seen = base._number(stats.get("seen"))
    if seen <= 0:
        return score
    losses = base._number(stats.get(POST_GATE_LOSS_FIELD))
    if losses <= 0:
        return score
    loss_rate = min(1.0, losses / seen)
    confidence = min(1.0, seen / 20.0)
    empirical_weight = 0.35 + 0.65 * confidence
    return score - POST_GATE_LOSS_PENALTY * loss_rate * empirical_weight


def learning_metadata(current_payload: dict | None) -> dict:
    metadata = _ORIGINAL_LEARNING_METADATA(current_payload)
    metadata["candidate_search_profile_learning_version"] = PROFILE_LEARNING_VERSION
    metadata["candidate_search_precision_policy"] = "two-exploit-one-explore-v2-final-outcome"
    metadata["candidate_search_precision_empirical_signals"] = (
        "indeed-yield+deterministic-accept+final-survivor+post-gate-loss+coarse-rejections"
    )
    metadata["candidate_search_precision_post_gate_loss_penalty"] = POST_GATE_LOSS_PENALTY
    metadata["candidate_search_precision_post_gate_loss_definition"] = (
        "pre-llm-accepted-minus-final-live-survivors"
    )
    return metadata


# Patch the v1 module's internal lookups so its stable ordering/phase machinery
# automatically uses the v2 history and score functions.
base.build_learning = build_learning
base.precision_score = precision_score


def profile_key(value: object) -> str:
    return base.profile_key(value)


def has_learning_signal(payload: dict | None) -> bool:
    return base.has_learning_signal(payload)


def order_profiles(
    profiles: Iterable[tuple[str, str]], payload: dict | None
) -> list[tuple[str, str]]:
    return base.order_profiles(profiles, payload)
