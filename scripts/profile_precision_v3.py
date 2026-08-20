#!/usr/bin/env python3
"""Family-diverse adaptive search ordering for scarce paced request windows.

V2 learns final downstream outcomes correctly, but normal-mode profile lists can
contain many repeated anchor slots that normalize to the same task family. When
monthly pacing leaves only two or three requests, two high-scoring variants of
the same family can otherwise consume the entire useful window.

V3 keeps the same scores, final-outcome feedback, historical decay, and 2:1
exploit/explore policy, while spreading nearby slots across task families when
an alternative exists. It changes only search ordering; all quality and budget
gates remain untouched.
"""
from __future__ import annotations

from typing import Iterable

import profile_precision as core
import profile_precision_v2 as v2

PROFILE_LEARNING_VERSION = 3
FAMILY_DIVERSITY_WINDOW = 2

core.PROFILE_LEARNING_VERSION = PROFILE_LEARNING_VERSION


FAMILY_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("ai_trainer", "ai_rating", "ai_rater", "rater"), "ai_rater"),
    (("annotation",), "annotation"),
    (("labeling", "data_label"), "labeling"),
    (("ocr",), "ocr"),
    (("data_entry",), "data_entry"),
    (("proofreading",), "proofreading"),
    (("transcription",), "transcription"),
    (("metadata",), "metadata"),
    (("document",), "document"),
    (("catalog", "product_entry"), "catalog"),
    (("web_research",), "web_research"),
    (("testing",), "testing"),
)


def family_key(value: object) -> str:
    key = core.profile_key(value)
    for tokens, family in FAMILY_RULES:
        if any(token in key for token in tokens):
            return family
    return key


def _pop_diverse(
    pool: list[tuple[str, str]], recent_families: list[str]
) -> tuple[str, str] | None:
    if not pool:
        return None
    blocked = set(recent_families[-FAMILY_DIVERSITY_WINDOW:])
    selected = 0
    for index, (name, _) in enumerate(pool):
        if family_key(name) not in blocked:
            selected = index
            break
    return pool.pop(selected)


def _append_diverse(
    cycle: list[tuple[str, str]],
    pool: list[tuple[str, str]],
    recent_families: list[str],
) -> None:
    item = _pop_diverse(pool, recent_families)
    if item is None:
        return
    cycle.append(item)
    recent_families.append(family_key(item[0]))
    if len(recent_families) > FAMILY_DIVERSITY_WINDOW:
        del recent_families[:-FAMILY_DIVERSITY_WINDOW]


def family_diverse_precision_cycle(
    profiles: list[tuple[str, str]], history: dict[str, dict[str, float]]
) -> tuple[list[tuple[str, str]], list[str]]:
    """Preserve 2:1 exploit/explore while avoiding nearby same-family slots."""
    indexed = list(enumerate(profiles))
    ranked = sorted(
        indexed,
        key=lambda item: (
            -core.precision_score(item[1][0], history),
            item[0],
        ),
    )
    ranked_profiles = [item[1] for item in ranked]
    if len(ranked_profiles) <= 2:
        return ranked_profiles, list(dict.fromkeys(core.profile_key(name) for name, _ in ranked_profiles))

    preferred_count = max(
        1,
        min(
            len(ranked_profiles),
            (
                len(ranked_profiles) * core.EXPLOIT_SLOTS
                + (core.EXPLOIT_SLOTS + core.EXPLORE_SLOTS - 1)
            )
            // (core.EXPLOIT_SLOTS + core.EXPLORE_SLOTS),
        ),
    )
    preferred = list(ranked_profiles[:preferred_count])
    exploration = list(ranked_profiles[preferred_count:])
    preferred_keys = list(
        dict.fromkeys(core.profile_key(name) for name, _ in preferred)
    )

    cycle: list[tuple[str, str]] = []
    recent_families: list[str] = []
    while preferred or exploration:
        for _ in range(core.EXPLOIT_SLOTS):
            _append_diverse(cycle, preferred, recent_families)
        _append_diverse(cycle, exploration, recent_families)
    return cycle, preferred_keys


# core.order_profiles resolves this helper dynamically, so patching only the
# cycle keeps its proven cursor compensation and phase advancement unchanged.
core._precision_cycle = family_diverse_precision_cycle


def profile_key(value: object) -> str:
    return core.profile_key(value)


def has_learning_signal(payload: dict | None) -> bool:
    return core.has_learning_signal(payload)


def order_profiles(
    profiles: Iterable[tuple[str, str]], payload: dict | None
) -> list[tuple[str, str]]:
    return core.order_profiles(profiles, payload)


def learning_metadata(current_payload: dict | None) -> dict:
    metadata = v2.learning_metadata(current_payload)
    metadata["candidate_search_profile_learning_version"] = PROFILE_LEARNING_VERSION
    metadata["candidate_search_precision_policy"] = (
        "two-exploit-one-explore-v3-family-diverse-final-outcome"
    )
    metadata["candidate_search_precision_family_diversity_window"] = FAMILY_DIVERSITY_WINDOW
    metadata["candidate_search_precision_family_key_method"] = "bounded-task-family-aliases-v1"
    priority_profiles = metadata.get("candidate_search_precision_priority_profiles") or []
    metadata["candidate_search_precision_priority_profiles"] = list(
        dict.fromkeys(str(value) for value in priority_profiles)
    )[:12]
    metadata["candidate_search_precision_priority_families"] = list(
        dict.fromkeys(family_key(value) for value in priority_profiles)
    )[:12]
    return metadata
