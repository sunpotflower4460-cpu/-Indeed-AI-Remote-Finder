#!/usr/bin/env python3
"""Measured supply experiment layered on top of the strict production pipeline.

This module does not relax any publication rule. It keeps the existing seven
requests/day budget and v2 full-remote/autonomy/presence gates, while improving
where those seven requests are spent:

- short async-core anchors target work that is structurally easier to automate
  end-to-end (data entry, annotation, AI rating, OCR, labeling, document/data ops);
- four short anchor variants containing ``Indeed`` remain as a source-bias
  experiment;
- the rotation layout alternates task exploration and async anchors so every
  seven-search daily window contains at least three async-core probes, including
  at least one Indeed-biased probe and one ordinary core probe;
- per-profile counts record rows seen, apply options, Indeed apply paths, and
  rows surviving all deterministic publication gates;
- coarse apply/via source counts persist no URLs or secrets.

The final publication gates are unchanged. More search budget is pointed toward
work that can plausibly pass those gates instead of weakening the gates when
supply is sparse.
"""
from __future__ import annotations

from collections import Counter
import json
import os

import acquisition
import acquisition_supply as base

YIELD_TELEMETRY_VERSION = 3

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

INDEED_BIAS_ANCHORS: list[tuple[str, str]] = [
    ("anchor_indeed_data", "完全在宅 データ入力 Indeed"),
    ("anchor_indeed_annotation", "完全在宅 アノテーション Indeed"),
    ("anchor_indeed_rater", "フルリモート AI評価 Indeed"),
    ("anchor_indeed_ocr", "完全在宅 OCR チェック Indeed"),
]

EXPERIMENTAL_ANCHORS: list[tuple[str, str]] = list(ASYNC_CORE_ANCHORS) + list(INDEED_BIAS_ANCHORS)

_PROFILE_YIELD: dict[str, dict[str, int]] = {}
_APPLY_SOURCE_COUNTS: Counter[str] = Counter()
_VIA_SOURCE_COUNTS: Counter[str] = Counter()


def measured_rotation_profiles(tasks: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Alternate one exploratory task with one high-likelihood async anchor.

    Anchors themselves alternate ordinary-core / Indeed-biased. Because every
    second profile is an anchor, any circular seven-profile window contains at
    least three anchors. Alternating anchor classes guarantees each seven-search
    window contains both an ordinary core probe and an Indeed-biased source
    probe, while the task slots continue to explore the long-tail profile set.
    """
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


def stamp_yield_metadata() -> None:
    payload = acquisition.load_payload()
    if not payload:
        return
    payload["candidate_search_strategy"] = "async-core-interleaved-indeed-yield-v3"
    payload["candidate_search_anchor_templates"] = len(EXPERIMENTAL_ANCHORS)
    payload["candidate_search_async_core_anchor_templates"] = len(ASYNC_CORE_ANCHORS)
    payload["candidate_search_indeed_bias_anchor_templates"] = len(INDEED_BIAS_ANCHORS)
    payload["candidate_search_anchor_min_per_daily_window"] = 3
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
