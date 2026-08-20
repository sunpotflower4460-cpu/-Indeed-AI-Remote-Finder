#!/usr/bin/env python3
"""Measured supply strategy layered on top of the strict production pipeline.

This module never relaxes publication rules or the nominal seven-request/day
budget. It improves where those searches are spent, respects any lower effective
request limit imposed by monthly pacing, and can temporarily switch to an Indeed
source-recovery mode when measured telemetry shows that otherwise relevant
Google Jobs rows are mostly unusable because they do not expose an Indeed
application path.

Normal mode:
- alternate long-tail task exploration with async-core anchors;
- at the nominal seven-search window, keep at least three async-core probes;
- retain an Indeed-biased probe for source-yield measurement.

Source-recovery mode:
- activate only when the previous low-stock run evaluated enough jobs and at
  least half were rejected solely because there was no Indeed apply path;
- use the empirically productive ``Indeed`` query term together with exact
  ``完全在宅`` / ``フルリモート`` phrases for every effective request;
- if a recovery run returns too little data, back off for several runs instead
  of oscillating between broad search and an empty recovery strategy;
- automatically return to normal exploration when the measured source
  bottleneck is no longer present.

Every returned row still passes the same v2 full-remote/autonomy/presence gates
and final LLM vetoes before publication.
"""
from __future__ import annotations

from collections import Counter
import json
import os

import acquisition
import acquisition_supply as base

YIELD_TELEMETRY_VERSION = 6
SOURCE_RECOVERY_VERSION = 2
SOURCE_RECOVERY_MIN_EVALUATED = 10
SOURCE_RECOVERY_NO_INDEED_RATIO = 0.50
SOURCE_RECOVERY_POOL_CEILING = 30
SOURCE_RECOVERY_COOLDOWN_RUNS = 3
INDEED_SOURCE_BIAS_TERM = "Indeed"

# These anchors intentionally avoid categories that commonly introduce recurring
# human coordination (for example translation/localization project work). They
# are discovery inputs only; every result still needs explicit full-remote text
# and all deterministic + LLM/presence gates before publication.
ASYNC_CORE_ANCHORS: list[tuple[str, str]] = [
    ("anchor_core_data_entry", "完全在宅 データ入力"),
    ("anchor_core_annotation", "完全在宅 アノテーション"),
    ("anchor_core_ai_rater", "フルリモート AI評価"),
    ("anchor_core_ocr", "完全在宅 OCR データチェック"),
    ("anchor_core_labeling", "フルリモート データラベリング"),
    ("anchor_core_document", "完全在宅 書類チェック データ入力"),
    ("anchor_core_catalog", "完全在宅 商品データ 登録"),
    ("anchor_core_metadata", "フルリモート タグ付け データ整理"),
]

# Production telemetry showed that appending the word "Indeed" can strongly
# bias Google Jobs toward rows with a canonical Indeed apply option, while the
# stricter site:jp.indeed.com operator returned zero rows in the Japanese run.
INDEED_BIAS_ANCHORS: list[tuple[str, str]] = [
    ("anchor_indeed_data", '"完全在宅" "データ入力" Indeed'),
    ("anchor_indeed_annotation", '"完全在宅" アノテーション Indeed'),
    ("anchor_indeed_rater", '"フルリモート" "AI評価" Indeed'),
    ("anchor_indeed_ocr", '"完全在宅" OCR Indeed'),
]

EXPERIMENTAL_ANCHORS: list[tuple[str, str]] = list(ASYNC_CORE_ANCHORS) + list(INDEED_BIAS_ANCHORS)

# When source recovery is active, all effective daily requests come from this
# list. It is deliberately longer than one nominal daily window so consecutive
# recovery runs still explore different async task families.
SOURCE_RECOVERY_QUERY_PROFILES: list[tuple[str, str]] = [
    ("source_data_entry_home", '"完全在宅" "データ入力" Indeed'),
    ("source_data_entry_remote", '"フルリモート" "データ入力" Indeed'),
    ("source_annotation_home", '"完全在宅" アノテーション Indeed'),
    ("source_annotation_remote", '"フルリモート" アノテーション Indeed'),
    ("source_ai_rating_home", '"完全在宅" "AI評価" Indeed'),
    ("source_ai_trainer_remote", '"フルリモート" "AIトレーナー" Indeed'),
    ("source_ocr_home", '"完全在宅" OCR Indeed'),
    ("source_labeling_remote", '"フルリモート" ラベリング Indeed'),
    ("source_transcription_home", '"完全在宅" "文字起こし" Indeed'),
    ("source_proofreading_home", '"完全在宅" 校正 Indeed'),
    ("source_product_entry_home", '"完全在宅" "商品登録" Indeed'),
    ("source_document_check_home", '"完全在宅" "書類チェック" Indeed'),
    ("source_data_check_home", '"完全在宅" "データチェック" Indeed'),
    ("source_metadata_remote", '"フルリモート" "タグ付け" Indeed'),
    ("source_web_research_home", '"完全在宅" "Webリサーチ" Indeed'),
    ("source_testing_home", '"完全在宅" "動作確認" Indeed'),
]

_PROFILE_YIELD: dict[str, dict[str, int]] = {}
_APPLY_SOURCE_COUNTS: Counter[str] = Counter()
_VIA_SOURCE_COUNTS: Counter[str] = Counter()
_ACTIVE_SOURCE_RECOVERY = False
_SOURCE_RECOVERY_TRIGGER_RATIO = 0.0
_SOURCE_RECOVERY_COOLDOWN_REMAINING = 0
_SOURCE_RECOVERY_TRIGGER_REASON = "none"


def measured_rotation_profiles(tasks: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Alternate one exploratory task with one high-likelihood async anchor."""
    combined: list[tuple[str, str]] = []
    core_index = 0
    bias_index = 0
    anchor_slot = 0
    use_bias = False

    for task_name, task_query in tasks:
        combined.append((task_name, task_query))
        if use_bias:
            name, query = INDEED_BIAS_ANCHORS[bias_index % len(INDEED_BIAS_ANCHORS)]
            bias_index += 1
        else:
            name, query = ASYNC_CORE_ANCHORS[core_index % len(ASYNC_CORE_ANCHORS)]
            core_index += 1
        combined.append((f"{name}_{anchor_slot:02d}", query))
        anchor_slot += 1
        use_bias = not use_bias
    return combined


PRODUCTION_QUERY_PROFILES = measured_rotation_profiles(base.TASK_QUERY_PROFILES)


def _nonnegative_int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _ratio_from_percent(value: object) -> float:
    try:
        return max(0.0, min(1.0, float(value or 0.0) / 100.0))
    except (TypeError, ValueError):
        return 0.0


def source_recovery_decision(payload: dict | None) -> tuple[bool, float, int, str]:
    """Choose recovery/fallback using only safe aggregate metadata."""
    if not isinstance(payload, dict):
        return False, 0.0, 0, "no-telemetry"

    pool = _nonnegative_int(payload.get("candidate_pool_size"))
    evaluated = _nonnegative_int(payload.get("candidate_quality_evaluated_jobs"))
    counts = payload.get("candidate_quality_rejection_counts") or {}
    no_indeed = _nonnegative_int(counts.get("no-indeed-apply")) if isinstance(counts, dict) else 0
    ratio = (no_indeed / evaluated) if evaluated else 0.0
    previous_active = payload.get("candidate_search_source_recovery_active") is True
    previous_version = _nonnegative_int(payload.get("candidate_search_source_recovery_version"))
    previous_cooldown = _nonnegative_int(
        payload.get("candidate_search_source_recovery_cooldown_runs_remaining")
    )

    # If the immediately previous recovery strategy produced almost no rows,
    # suppress repeated retries. The one exception is a strategy-version change:
    # v2 intentionally replaces the empirically empty site:jp.indeed.com v1, so
    # carry its known trigger ratio forward once and test the new method.
    if previous_active and evaluated < SOURCE_RECOVERY_MIN_EVALUATED:
        if previous_version < SOURCE_RECOVERY_VERSION:
            historical_ratio = _ratio_from_percent(
                payload.get("candidate_search_source_recovery_trigger_ratio_pct")
            )
            if pool < SOURCE_RECOVERY_POOL_CEILING and historical_ratio >= SOURCE_RECOVERY_NO_INDEED_RATIO:
                return True, historical_ratio, 0, "strategy-upgrade-retry"
        return False, ratio, SOURCE_RECOVERY_COOLDOWN_RUNS, "recovery-empty-backoff"

    if previous_cooldown > 0:
        return False, ratio, previous_cooldown - 1, "cooldown"

    active = bool(
        pool < SOURCE_RECOVERY_POOL_CEILING
        and evaluated >= SOURCE_RECOVERY_MIN_EVALUATED
        and ratio >= SOURCE_RECOVERY_NO_INDEED_RATIO
    )
    return active, ratio, 0, "no-indeed-bottleneck" if active else "normal"


def source_recovery_signal(payload: dict | None) -> tuple[bool, float]:
    """Backward-compatible compact view used by tests/callers."""
    active, ratio, _, _ = source_recovery_decision(payload)
    return active, ratio


def select_query_profiles(previous_payload: dict | None) -> list[tuple[str, str]]:
    global _ACTIVE_SOURCE_RECOVERY
    global _SOURCE_RECOVERY_TRIGGER_RATIO
    global _SOURCE_RECOVERY_COOLDOWN_REMAINING
    global _SOURCE_RECOVERY_TRIGGER_REASON

    active, ratio, cooldown, reason = source_recovery_decision(previous_payload)
    _ACTIVE_SOURCE_RECOVERY = active
    _SOURCE_RECOVERY_TRIGGER_RATIO = ratio
    _SOURCE_RECOVERY_COOLDOWN_REMAINING = cooldown
    _SOURCE_RECOVERY_TRIGGER_REASON = reason
    if active:
        return list(SOURCE_RECOVERY_QUERY_PROFILES)
    return list(PRODUCTION_QUERY_PROFILES)


def reset_yield_telemetry() -> None:
    _PROFILE_YIELD.clear()
    _APPLY_SOURCE_COUNTS.clear()
    _VIA_SOURCE_COUNTS.clear()


def _bucket(category: str) -> dict[str, int]:
    name = str(category or "unknown")[:80]
    return _PROFILE_YIELD.setdefault(
        name,
        {"seen": 0, "apply_options": 0, "indeed_apply": 0, "accepted": 0},
    )


def _source_label(value: object) -> str:
    label = acquisition.legacy.clean(str(value or "")).strip()
    if not label:
        return ""
    if "indeed" in label.lower():
        return "Indeed"
    return label[:60]


def observe_job(job: dict, category: str) -> None:
    """Collect safe aggregate source data; never copy an apply URL to telemetry."""
    if not isinstance(job, dict):
        return
    bucket = _bucket(category)
    bucket["seen"] += 1

    options = job.get("apply_options") or []
    valid = [item for item in options if isinstance(item, dict)] if isinstance(options, list) else []
    if valid:
        bucket["apply_options"] += 1
    for option in valid:
        label = _source_label(option.get("title"))
        if label:
            _APPLY_SOURCE_COUNTS[label] += 1

    via = _source_label(job.get("via"))
    if via:
        _VIA_SOURCE_COUNTS[via] += 1

    if acquisition.legacy.find_indeed_apply(job):
        bucket["indeed_apply"] += 1


def configure_yield_wrapper() -> None:
    if getattr(acquisition, "_yield_experiment_configured", False):
        return
    acquisition._yield_experiment_configured = True
    underlying = acquisition.build_row

    def measured_build_row(job, category, previous):
        observe_job(job, category)
        row = underlying(job, category, previous)
        if row:
            _bucket(category)["accepted"] += 1
        return row

    acquisition.build_row = measured_build_row


def yield_snapshot() -> dict:
    profiles = [
        {"profile": name, **counts}
        for name, counts in _PROFILE_YIELD.items()
        if counts.get("seen", 0) > 0
    ]
    profiles.sort(
        key=lambda item: (
            -int(item["accepted"]),
            -int(item["indeed_apply"]),
            -int(item["apply_options"]),
            -int(item["seen"]),
            str(item["profile"]),
        )
    )
    seen = sum(int(item["seen"]) for item in profiles)
    with_options = sum(int(item["apply_options"]) for item in profiles)
    with_indeed = sum(int(item["indeed_apply"]) for item in profiles)
    accepted = sum(int(item["accepted"]) for item in profiles)
    return {
        "candidate_yield_telemetry_version": YIELD_TELEMETRY_VERSION,
        "candidate_yield_jobs_seen": seen,
        "candidate_jobs_with_apply_options": with_options,
        "candidate_jobs_with_indeed_apply": with_indeed,
        "candidate_deterministic_gate_accepted": accepted,
        "candidate_apply_options_coverage_pct": round(with_options * 100 / seen, 1) if seen else 0.0,
        "candidate_indeed_apply_rate_pct": round(with_indeed * 100 / seen, 1) if seen else 0.0,
        "candidate_deterministic_accept_rate_pct": round(accepted * 100 / seen, 1) if seen else 0.0,
        "candidate_apply_source_counts": dict(_APPLY_SOURCE_COUNTS.most_common(10)),
        "candidate_via_source_counts": dict(_VIA_SOURCE_COUNTS.most_common(10)),
        "candidate_search_profile_yield": profiles[:12],
    }


def effective_request_limit(payload: dict) -> int:
    """Return the request window actually available after provider/month pacing."""
    effective = _nonnegative_int(payload.get("serpapi_effective_request_limit"))
    if effective <= 0:
        effective = _nonnegative_int(payload.get("query_total"))
    if effective <= 0:
        effective = base.DEEP_REQUESTS
    return min(base.DEEP_REQUESTS, effective)


def search_window_minima(active_recovery: bool, effective_limit: int) -> dict[str, int]:
    """Describe guarantees for the *effective* request window, not nominal seven."""
    width = max(0, min(base.DEEP_REQUESTS, int(effective_limit)))
    if active_recovery:
        return {
            "anchors": 0,
            "indeed_bias": width,
            "ordinary": 0,
            "source_targeted": width,
        }

    # Normal mode alternates task, anchor, task, anchor...; anchor classes then
    # alternate core/Indeed. At fewer than four requests a window cannot promise
    # both anchor classes, so report zero rather than an overstated guarantee.
    anchors = width // 2
    both_classes = 1 if width >= 4 else 0
    return {
        "anchors": anchors,
        "indeed_bias": both_classes,
        "ordinary": both_classes,
        "source_targeted": both_classes,
    }


def stamp_yield_metadata() -> None:
    payload = acquisition.load_payload()
    if not payload:
        return
    payload["candidate_search_strategy"] = (
        "indeed-keyword-source-recovery-v2"
        if _ACTIVE_SOURCE_RECOVERY
        else "async-core-interleaved-indeed-yield-v6"
    )
    payload["candidate_search_anchor_templates"] = len(EXPERIMENTAL_ANCHORS)
    payload["candidate_search_async_core_anchor_templates"] = len(ASYNC_CORE_ANCHORS)
    payload["candidate_search_indeed_bias_anchor_templates"] = len(INDEED_BIAS_ANCHORS)
    payload["candidate_search_source_recovery_version"] = SOURCE_RECOVERY_VERSION
    payload["candidate_search_source_recovery_active"] = _ACTIVE_SOURCE_RECOVERY
    payload["candidate_search_source_recovery_trigger_ratio_pct"] = round(
        _SOURCE_RECOVERY_TRIGGER_RATIO * 100, 1
    )
    payload["candidate_search_source_recovery_ratio_threshold_pct"] = round(
        SOURCE_RECOVERY_NO_INDEED_RATIO * 100, 1
    )
    payload["candidate_search_source_recovery_min_evaluated"] = SOURCE_RECOVERY_MIN_EVALUATED
    payload["candidate_search_source_recovery_pool_ceiling"] = SOURCE_RECOVERY_POOL_CEILING
    payload["candidate_search_source_recovery_cooldown_runs"] = SOURCE_RECOVERY_COOLDOWN_RUNS
    payload["candidate_search_source_recovery_cooldown_runs_remaining"] = (
        _SOURCE_RECOVERY_COOLDOWN_REMAINING
    )
    payload["candidate_search_source_recovery_trigger_reason"] = _SOURCE_RECOVERY_TRIGGER_REASON
    payload["candidate_search_source_bias_method"] = "keyword-plus-exact-remote"
    payload["candidate_search_source_bias_term"] = INDEED_SOURCE_BIAS_TERM

    effective = effective_request_limit(payload)
    minima = search_window_minima(_ACTIVE_SOURCE_RECOVERY, effective)
    payload["candidate_search_effective_daily_limit"] = effective
    payload["candidate_search_effective_window_paced"] = effective < base.DEEP_REQUESTS
    payload["candidate_search_anchor_min_per_daily_window"] = minima["anchors"]
    payload["candidate_search_indeed_bias_min_per_daily_window"] = minima["indeed_bias"]
    payload["candidate_search_ordinary_anchor_min_per_daily_window"] = minima["ordinary"]
    payload["candidate_search_source_targeted_min_per_daily_window"] = minima["source_targeted"]

    payload.update(yield_snapshot())
    acquisition.OUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def main() -> None:
    reset_yield_telemetry()
    base.acquisition_quality.reset_quality_telemetry()
    previous_payload = acquisition.load_payload()
    selected_profiles = select_query_profiles(previous_payload)
    base.ANCHOR_QUERY_PROFILES = list(EXPERIMENTAL_ANCHORS)
    base.PRODUCTION_QUERY_PROFILES = selected_profiles
    base.configure_supply_rotation()
    configure_yield_wrapper()

    api_key = os.environ.get("SERPAPI_KEY", "").strip()
    if not api_key:
        print("SERPAPI_KEY is not configured; preserving the last known-good feed.")
        return
    provider_cap = base.acquisition_remote.configure_provider_budget(api_key)
    if provider_cap == 0:
        print("SerpApi provider usage guard has no safe request headroom; preserving last known-good feed.")
        return

    acquisition.main()
    base.acquisition_remote.stamp_policy_metadata()
    base.acquisition_quality.stamp_quality_metadata()
    base.stamp_supply_metadata()
    stamp_yield_metadata()


if __name__ == "__main__":
    main()
