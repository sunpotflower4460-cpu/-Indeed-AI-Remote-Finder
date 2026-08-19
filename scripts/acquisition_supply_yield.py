#!/usr/bin/env python3
"""Measured supply experiment layered on top of the strict production pipeline.

This module does not relax any publication rule. It keeps the existing seven
requests/day budget and v2 full-remote/autonomy/presence gates, while adding:

- four short anchor variants containing ``Indeed`` as a source-bias experiment;
- a rotation layout that guarantees every seven-search daily window contains at
  least one Indeed-biased anchor and at least one ordinary anchor;
- per-profile counts for rows seen, rows with apply options, Indeed apply paths,
  and rows that survive all deterministic publication gates;
- coarse apply/via source counts with no URLs or secrets persisted.

The ordinary anchors remain in rotation, so future runs can compare measured
yield instead of assuming the source-bias wording is beneficial.
"""
from __future__ import annotations

from collections import Counter
import json
import os

import acquisition
import acquisition_supply as base

YIELD_TELEMETRY_VERSION = 2

INDEED_BIAS_ANCHORS: list[tuple[str, str]] = [
    ("anchor_indeed_data", "完全在宅 データ入力 Indeed"),
    ("anchor_indeed_ai", "フルリモート AI評価 Indeed"),
    ("anchor_indeed_language", "完全在宅 翻訳 校正 Indeed"),
    ("anchor_indeed_content", "完全在宅 商品登録 Indeed"),
]
EXPERIMENTAL_ANCHORS: list[tuple[str, str]] = list(base.ANCHOR_QUERY_PROFILES) + list(INDEED_BIAS_ANCHORS)

_PROFILE_YIELD: dict[str, dict[str, int]] = {}
_APPLY_SOURCE_COUNTS: Counter[str] = Counter()
_VIA_SOURCE_COUNTS: Counter[str] = Counter()


def measured_rotation_profiles(tasks: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Alternate ordinary and Indeed-biased anchors across the task rotation.

    Base supply inserts one anchor after each pair of task profiles. A seven
    profile window therefore contains at least two consecutive anchor slots.
    Alternating the anchor stream ordinary/bias guarantees at least one source
    probe per daily seven-search window without spending an additional request.
    """
    combined: list[tuple[str, str]] = []
    ordinary_index = 0
    bias_index = 0
    anchor_slot = 0
    use_bias = False

    for offset in range(0, len(tasks), 2):
        combined.extend(tasks[offset: offset + 2])
        if use_bias:
            name, query = INDEED_BIAS_ANCHORS[bias_index % len(INDEED_BIAS_ANCHORS)]
            bias_index += 1
        else:
            name, query = base.ANCHOR_QUERY_PROFILES[
                ordinary_index % len(base.ANCHOR_QUERY_PROFILES)
            ]
            ordinary_index += 1
        combined.append((f"{name}_{anchor_slot:02d}", query))
        anchor_slot += 1
        use_bias = not use_bias
    return combined


PRODUCTION_QUERY_PROFILES = measured_rotation_profiles(base.TASK_QUERY_PROFILES)


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
    return {
        "candidate_yield_telemetry_version": YIELD_TELEMETRY_VERSION,
        "candidate_yield_jobs_seen": seen,
        "candidate_jobs_with_apply_options": with_options,
        "candidate_jobs_with_indeed_apply": with_indeed,
        "candidate_apply_options_coverage_pct": round(with_options * 100 / seen, 1) if seen else 0.0,
        "candidate_indeed_apply_rate_pct": round(with_indeed * 100 / seen, 1) if seen else 0.0,
        "candidate_apply_source_counts": dict(_APPLY_SOURCE_COUNTS.most_common(10)),
        "candidate_via_source_counts": dict(_VIA_SOURCE_COUNTS.most_common(10)),
        "candidate_search_profile_yield": profiles[:12],
    }


def stamp_yield_metadata() -> None:
    payload = acquisition.load_payload()
    if not payload:
        return
    payload["candidate_search_strategy"] = "alternating-anchor-indeed-yield-experiment-v2"
    payload["candidate_search_anchor_templates"] = len(EXPERIMENTAL_ANCHORS)
    payload["candidate_search_indeed_bias_anchor_templates"] = len(INDEED_BIAS_ANCHORS)
    payload["candidate_search_indeed_bias_min_per_daily_window"] = 1
    payload["candidate_search_ordinary_anchor_min_per_daily_window"] = 1
    payload.update(yield_snapshot())
    acquisition.OUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def main() -> None:
    reset_yield_telemetry()
    base.ANCHOR_QUERY_PROFILES = list(EXPERIMENTAL_ANCHORS)
    base.PRODUCTION_QUERY_PROFILES = list(PRODUCTION_QUERY_PROFILES)
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
