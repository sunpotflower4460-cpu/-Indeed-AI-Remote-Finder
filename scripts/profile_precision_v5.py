#!/usr/bin/env python3
"""Quality-first family handoff for scarce adaptive search windows.

V4 learned which exact search profiles produced final survivors and suppressed an
exact champion after an immediate re-search failed to produce a new survivor.
That avoids wasting a scarce two-request window on the same query, but it can
swing too far toward unrelated task families even when the *kind* of work was
strongly validated.

V5 keeps the exact-profile fatigue guard and adds a bounded family handoff:
- add a small set of high-intent Japanese/English AI-evaluation queries;
- when a proven exact champion is fatigued, rotate to a different query in the
  same proven task family rather than repeating the exact query;
- require positive profile quality and historical final-survivor evidence;
- keep the next actual slot in a different family when possible;
- never change request counts, provider/monthly budgets, publication thresholds,
  presence rules, AI-use policy rules, LLM vetoes, or validators.
"""
from __future__ import annotations

from typing import Iterable

import profile_precision as core
import profile_precision_v3 as v3
import profile_precision_v4 as v4

PROFILE_LEARNING_VERSION = 5
FAMILY_HANDOFF_MIN_FINAL_SURVIVORS = 0.5
FAMILY_HANDOFF_MIN_PROFILE_SCORE = 12.0

# These queries are intentionally short. They target task families that are
# intrinsically digital, asynchronous, and close to the one production family
# that has already survived every deterministic + LLM gate. They remain only
# discovery inputs: every returned row still has to pass the unchanged strict
# publication pipeline.
SOURCE_HIGH_INTENT_PROFILES: list[tuple[str, str]] = [
    ("source_ai_trainer_japanese_en_remote", '"fully remote" "Japanese AI trainer" Indeed'),
    ("source_ai_rater_japanese_en_remote", '"fully remote" "Japanese AI rater" Indeed'),
    ("source_model_response_eval_remote", '"fully remote" "Japanese" "model evaluation" Indeed'),
    ("source_prompt_eval_japanese_remote", '"fully remote" "Japanese" "prompt evaluator" Indeed'),
    ("source_annotation_japanese_en_remote", '"fully remote" "Japanese data annotator" Indeed'),
    ("source_search_eval_japanese_remote", '"fully remote" "Japanese search evaluator" Indeed'),
    ("source_ai_rater_translation_remote", '"fully remote" "Japanese translator" "AI trainer" Indeed'),
    ("source_ai_trainer_language_remote", '"fully remote" "Japanese language" "AI evaluator" Indeed'),
]

NORMAL_HIGH_INTENT_PROFILES: list[tuple[str, str]] = [
    ("anchor_indeed_ai_trainer_english", '"fully remote" "Japanese AI trainer" Indeed'),
    ("anchor_indeed_ai_rater_english", '"fully remote" "Japanese AI rater" Indeed'),
    ("anchor_indeed_model_response_eval", '"fully remote" "Japanese" "model evaluation" Indeed'),
    ("anchor_indeed_annotation_english", '"fully remote" "Japanese data annotator" Indeed'),
]

# Extend V3's family vocabulary so new high-intent aliases do not occupy both
# scarce slots simply because their profile names differ.
ENHANCED_FAMILY_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("ai_trainer", "ai_rating", "ai_rater", "rater", "model_response", "prompt_eval", "llm_eval", "ai_evaluator", "language_ai"), "ai_rater"),
    (("annotation", "annotator"), "annotation"),
    (("labeling", "data_label"), "labeling"),
    (("search_eval", "search_quality", "search_evaluator"), "search_quality"),
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

core.PROFILE_LEARNING_VERSION = PROFILE_LEARNING_VERSION
v3.FAMILY_RULES = ENHANCED_FAMILY_RULES

_SELECTED_HANDOFF: str | None = None
_SELECTED_HANDOFF_FAMILY: str | None = None
_SELECTED_HANDOFF_SCORE: float | None = None
_HANDOFF_REASON = "none"
_AUGMENTED_PROFILE_COUNT = 0
_HIGH_INTENT_PROFILE_COUNT = 0


def family_key(value: object) -> str:
    return v3.family_key(value)


def profile_key(value: object) -> str:
    return core.profile_key(value)


def has_learning_signal(payload: dict | None) -> bool:
    return core.has_learning_signal(payload)


def _looks_like_source_recovery(profiles: list[tuple[str, str]]) -> bool:
    if not profiles:
        return False
    source = sum(1 for name, _ in profiles if core.profile_key(name).startswith("source_"))
    return source >= max(1, len(profiles) * 3 // 4)


def augment_profiles(
    profiles: Iterable[tuple[str, str]], payload: dict | None = None
) -> list[tuple[str, str]]:
    """Add bounded high-intent probes without deleting any existing profile."""
    del payload  # reserved for future telemetry-based profile-set changes
    global _AUGMENTED_PROFILE_COUNT, _HIGH_INTENT_PROFILE_COUNT

    rows = list(profiles)
    extras = SOURCE_HIGH_INTENT_PROFILES if _looks_like_source_recovery(rows) else NORMAL_HIGH_INTENT_PROFILES
    seen = {core.profile_key(name) for name, _ in rows}
    added = 0
    for name, query in extras:
        key = core.profile_key(name)
        if key in seen:
            continue
        rows.append((name, query))
        seen.add(key)
        added += 1
    _AUGMENTED_PROFILE_COUNT = len(rows)
    _HIGH_INTENT_PROFILE_COUNT = added
    return rows


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


def _family_history() -> dict[str, dict[str, float]]:
    grouped: dict[str, dict[str, float]] = {}
    for key, stats in core._STATE.items():
        family = family_key(key)
        bucket = grouped.setdefault(
            family,
            {"seen": 0.0, "accepted": 0.0, "final_survivors": 0.0},
        )
        bucket["seen"] += core._number(stats.get("seen"))
        bucket["accepted"] += core._number(stats.get("accepted"))
        bucket["final_survivors"] += core._number(stats.get("final_survivors"))
    return grouped


def _choose_family_handoff(
    profiles: list[tuple[str, str]], payload: dict | None
) -> tuple[str, str, float] | None:
    global _HANDOFF_REASON

    if not profiles or not isinstance(payload, dict):
        _HANDOFF_REASON = "no-profile-or-telemetry"
        return None
    if payload.get("pool_under_display_target") is False:
        _HANDOFF_REASON = "pool-target-met"
        return None

    recent = v4._recently_searched_profiles(payload)
    family_history = _family_history()
    candidates: list[tuple[float, float, float, str, str]] = []

    for name, _ in profiles:
        key = core.profile_key(name)
        if key in recent:
            continue
        family = family_key(key)
        history = family_history.get(family) or {}
        finals = core._number(history.get("final_survivors"))
        if finals < FAMILY_HANDOFF_MIN_FINAL_SURVIVORS:
            continue
        score = core.precision_score(key, core._STATE)
        if score < FAMILY_HANDOFF_MIN_PROFILE_SCORE:
            continue
        # Prefer families with proven final survivors, then exact profile score.
        # Lower seen counts win a final tie to encourage a different query wording
        # inside the already-proven family rather than another stale variant.
        seen = core._number((core._STATE.get(key) or {}).get("seen"))
        candidates.append((finals, score, -seen, key, family))

    if not candidates:
        _HANDOFF_REASON = "no-proven-family-sibling"
        return None

    candidates.sort(key=lambda item: (-item[0], -item[1], -item[2], item[3]))
    finals, score, _, key, family = candidates[0]
    del finals
    _HANDOFF_REASON = "proven-family-query-rotation"
    return key, family, score


def _promote_and_diversify(
    actual: list[tuple[str, str]], selected_key: str
) -> list[tuple[str, str]]:
    selected_index = None
    for index, (name, _) in enumerate(actual):
        if core.profile_key(name) == selected_key:
            selected_index = index
            break
    if selected_index is None:
        return actual
    if selected_index:
        actual.insert(0, actual.pop(selected_index))

    if len(actual) > 1:
        first_family = family_key(actual[0][0])
        if family_key(actual[1][0]) == first_family:
            for index in range(2, len(actual)):
                if family_key(actual[index][0]) != first_family:
                    actual.insert(1, actual.pop(index))
                    break
    return actual


def order_profiles(
    profiles: Iterable[tuple[str, str]], payload: dict | None
) -> list[tuple[str, str]]:
    """Keep V4 exact champion, otherwise rotate within a proven family."""
    global _SELECTED_HANDOFF, _SELECTED_HANDOFF_FAMILY, _SELECTED_HANDOFF_SCORE, _HANDOFF_REASON
    _SELECTED_HANDOFF = None
    _SELECTED_HANDOFF_FAMILY = None
    _SELECTED_HANDOFF_SCORE = None
    _HANDOFF_REASON = "none"

    rows = list(profiles)
    ordered = v4.order_profiles(rows, payload)

    # If V4 already selected an eligible exact champion, that stronger exact
    # evidence wins. Family handoff is for fatigue/no-exact-champion cases only.
    if v4._SELECTED_CHAMPION is not None:
        _HANDOFF_REASON = "exact-champion-selected"
        return ordered

    handoff = _choose_family_handoff(rows, payload)
    if handoff is None:
        return ordered

    selected_key, family, score = handoff
    actual = _actual_order(ordered, payload)
    actual = _promote_and_diversify(actual, selected_key)
    _SELECTED_HANDOFF = selected_key
    _SELECTED_HANDOFF_FAMILY = family
    _SELECTED_HANDOFF_SCORE = round(score, 2)
    return _precompensate(actual, payload)


def learning_metadata(current_payload: dict | None) -> dict:
    metadata = v4.learning_metadata(current_payload)
    metadata["candidate_search_profile_learning_version"] = PROFILE_LEARNING_VERSION
    metadata["candidate_search_precision_policy"] = (
        "v5-family-handoff+guarded-champion+family-diverse-final-outcome"
    )
    metadata["candidate_search_precision_family_key_method"] = (
        "bounded-task-family-aliases-v2-ai-eval-expansion"
    )
    metadata["candidate_search_precision_high_intent_profiles_added"] = _HIGH_INTENT_PROFILE_COUNT
    metadata["candidate_search_precision_augmented_profile_count"] = _AUGMENTED_PROFILE_COUNT
    metadata["candidate_search_precision_family_handoff_min_final_survivors"] = (
        FAMILY_HANDOFF_MIN_FINAL_SURVIVORS
    )
    metadata["candidate_search_precision_family_handoff_min_profile_score"] = (
        FAMILY_HANDOFF_MIN_PROFILE_SCORE
    )
    metadata["candidate_search_precision_family_handoff_profile"] = _SELECTED_HANDOFF
    metadata["candidate_search_precision_family_handoff_family"] = _SELECTED_HANDOFF_FAMILY
    metadata["candidate_search_precision_family_handoff_score"] = _SELECTED_HANDOFF_SCORE
    metadata["candidate_search_precision_family_handoff_reason"] = _HANDOFF_REASON
    metadata["candidate_search_precision_family_handoff_behavior"] = (
        "rotate-query-within-proven-family-before-unrelated-search"
    )
    return metadata
