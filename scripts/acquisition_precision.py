#!/usr/bin/env python3
"""Production entrypoint with adaptive search-profile ordering.

The underlying acquisition, strict quality gates, source-recovery decision,
provider budget guard, and base telemetry remain in acquisition_supply_yield.py.
This wrapper reorders approved search profiles using bounded historical outcomes,
diversifies scarce windows, uses a guarded champion slot, rotates within proven
job families when an exact query is fatigued, adds high-intent AI-evaluation
probes, replaces known-negative profiles in two/three-request windows when a
better unexplored family exists, records successful zero-result searches so they
can be learned from, and broadens only the *application destination* from Indeed
to a small audited set of established Japanese job boards.

Publication quality is not relaxed: every candidate still has to pass the same
full-remote, autonomy, presence, deterministic, LLM and AI-use-policy gates.
"""
from __future__ import annotations

from collections import Counter
import json

import acquisition
import acquisition_quality
import acquisition_supply_yield as supply
import apply_ai_tool_policy_gate as ai_policy
import apply_sources
import profile_precision_v7 as profile_precision


_ORIGINAL_SELECT = supply.select_query_profiles
_ORIGINAL_STAMP = supply.stamp_yield_metadata
_ORIGINAL_PREFILTER = acquisition_quality.prefilter_rejection_reason
_ORIGINAL_ACQUISITION_BUILD_ROW = acquisition.build_row
_ORIGINAL_INDEED_APPLY = acquisition.legacy.find_indeed_apply
_PLANNED_ACTUAL_PROFILES: list[tuple[str, str]] = []
ATTEMPT_TELEMETRY_VERSION = 1
TRUSTED_APPLY_POLICY_VERSION = 1
SAFE_INTERNAL_MONTHLY_CAP = 245


def _nonnegative_int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def adaptive_select_query_profiles(previous_payload: dict | None) -> list[tuple[str, str]]:
    global _PLANNED_ACTUAL_PROFILES
    profiles = _ORIGINAL_SELECT(previous_payload)
    profiles = profile_precision.augment_profiles(profiles, previous_payload)
    ordered = profile_precision.order_profiles(profiles, previous_payload)
    _PLANNED_ACTUAL_PROFILES = profile_precision.actual_order(ordered, previous_payload)
    return ordered


def _call_with_trusted_apply(callback, job: dict):
    """Temporarily widen the legacy lookup only inside one synchronous gate call."""
    original = acquisition.legacy.find_indeed_apply
    acquisition.legacy.find_indeed_apply = apply_sources.target_tuple
    try:
        return callback()
    finally:
        acquisition.legacy.find_indeed_apply = original


def trusted_source_build_row(job: dict, category: str, previous: dict[str, dict]):
    """Reuse the proven row builder while substituting a validated apply target."""
    target = apply_sources.find_trusted_apply(job)
    if not target:
        return None

    row = _call_with_trusted_apply(
        lambda: _ORIGINAL_ACQUISITION_BUILD_ROW(job, category, previous),
        job,
    )
    if not row:
        return None

    row["url"] = target.url
    row["id"] = target.job_id
    row["apply_source"] = target.source
    row["apply_source_kind"] = target.kind
    row["trusted_apply_policy_version"] = TRUSTED_APPLY_POLICY_VERSION
    row["source"] = f"Google Jobs via SerpApi; {target.source} apply option verified"
    return row


def policy_aware_prefilter(job: dict) -> str | None:
    target = apply_sources.find_trusted_apply(job)
    if not target:
        return "no-trusted-apply"

    # The existing quality prefilter begins with an Indeed-only check. Substitute
    # our audited structured apply target only for this synchronous call, then
    # immediately restore the original helper so Indeed telemetry stays truthful.
    reason = _call_with_trusted_apply(lambda: _ORIGINAL_PREFILTER(job), job)
    if reason == "no-indeed-apply":
        reason = "no-trusted-apply"
    if reason:
        return reason
    status, _ = ai_policy.policy_signal(job)
    if status == "prohibited":
        return "explicit-ai-tool-ban"
    return None


def _failed_first_page_profiles(payload: dict) -> set[str]:
    failed: set[str] = set()
    errors = payload.get("errors") or []
    if not isinstance(errors, list):
        return failed
    for value in errors:
        text = str(value or "").strip()
        if not text:
            continue
        category = text.split(":", 1)[0].strip()
        if category:
            failed.add(category)
    return failed


def stamp_attempt_telemetry(
    payload: dict,
    planned_actual: list[tuple[str, str]],
) -> None:
    """Add first-page attempts even when a successful query returned zero jobs."""
    requests_run = _nonnegative_int(payload.get("serpapi_requests_run"))
    paginated = _nonnegative_int(payload.get("serpapi_paginated_requests_run"))
    first_page_attempts = max(0, requests_run - paginated)
    attempted = list(planned_actual[:first_page_attempts])
    failed = _failed_first_page_profiles(payload)

    existing = payload.get("candidate_search_profile_yield") or []
    rows = [dict(item) for item in existing if isinstance(item, dict)] if isinstance(existing, list) else []
    by_name = {str(item.get("profile") or ""): item for item in rows if item.get("profile")}

    zero_profiles: list[str] = []
    failed_profiles: list[str] = []
    attempted_names: list[str] = []
    for name, _ in attempted:
        category = str(name or "")[:80]
        if not category:
            continue
        attempted_names.append(category)
        row = by_name.get(category)
        if row is None:
            row = {
                "profile": category,
                "seen": 0,
                "apply_options": 0,
                "indeed_apply": 0,
                "accepted": 0,
            }
            rows.append(row)
            by_name[category] = row
        row["search_attempts"] = _nonnegative_int(row.get("search_attempts")) + 1

        if category in failed:
            row["query_failures"] = _nonnegative_int(row.get("query_failures")) + 1
            failed_profiles.append(category)
            continue

        row["successful_search_attempts"] = _nonnegative_int(
            row.get("successful_search_attempts")
        ) + 1
        if _nonnegative_int(row.get("seen")) == 0:
            row["zero_result_attempts"] = _nonnegative_int(
                row.get("zero_result_attempts")
            ) + 1
            zero_profiles.append(category)

    payload["candidate_search_profile_yield"] = rows[:24]
    payload["candidate_search_attempt_telemetry_version"] = ATTEMPT_TELEMETRY_VERSION
    payload["candidate_search_attempted_profiles"] = attempted_names[:7]
    payload["candidate_search_first_page_attempts"] = len(attempted_names)
    payload["candidate_search_zero_result_profiles"] = zero_profiles[:7]
    payload["candidate_search_zero_result_profile_count"] = len(zero_profiles)
    payload["candidate_search_failed_profiles"] = failed_profiles[:7]
    payload["candidate_search_failed_profile_count"] = len(failed_profiles)


def stamp_apply_source_metadata(payload: dict) -> None:
    counts: Counter[str] = Counter()
    indeed = 0
    trusted_other = 0
    for row in payload.get("jobs") or []:
        if not isinstance(row, dict):
            continue
        source = str(row.get("apply_source") or "").strip()
        kind = str(row.get("apply_source_kind") or "").strip()
        if source:
            counts[source] += 1
        if kind == "indeed":
            indeed += 1
        elif kind == "trusted-job-board":
            trusted_other += 1

    payload["candidate_trusted_apply_policy_version"] = TRUSTED_APPLY_POLICY_VERSION
    payload["candidate_apply_destination_policy"] = "indeed-first+audited-major-job-boards"
    payload["candidate_apply_destination_quality_unchanged"] = True
    payload["candidate_trusted_apply_board_domains"] = [
        suffix for suffix, _ in apply_sources.TRUSTED_JOB_BOARD_HOSTS
    ]
    payload["candidate_final_apply_source_counts"] = dict(counts.most_common(8))
    payload["candidate_final_indeed_apply_jobs"] = indeed
    payload["candidate_final_other_trusted_apply_jobs"] = trusted_other
    payload["serpapi_internal_monthly_cap_default"] = SAFE_INTERNAL_MONTHLY_CAP
    payload["serpapi_provider_guard_remains_authoritative"] = True


def adaptive_stamp_yield_metadata() -> None:
    _ORIGINAL_STAMP()
    payload = acquisition.load_payload()
    if not payload:
        return
    stamp_attempt_telemetry(payload, _PLANNED_ACTUAL_PROFILES)
    payload.update(profile_precision.learning_metadata(payload))
    payload["candidate_ai_tool_policy_gate_version"] = ai_policy.AI_TOOL_POLICY_GATE_VERSION
    payload["candidate_rejects_explicit_ai_tool_bans"] = True
    allowed = 0
    confirmation = 0
    for row in payload.get("jobs") or []:
        if not isinstance(row, dict):
            continue
        status, signal = ai_policy.policy_signal(row)
        row["ai_tool_policy_gate_version"] = ai_policy.AI_TOOL_POLICY_GATE_VERSION
        row["ai_tool_policy_status"] = status
        row["ai_tool_policy_signal"] = signal
        row["ai_tool_use_permission_confirm_required"] = status != "explicitly-allowed"
        if status == "explicitly-allowed":
            allowed += 1
        else:
            confirmation += 1
    payload["candidate_ai_tool_policy_explicitly_allowed"] = allowed
    payload["candidate_ai_tool_policy_confirmation_required"] = confirmation
    stamp_apply_source_metadata(payload)
    acquisition.OUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def install() -> None:
    # The connected account currently exposes more headroom than the old 220
    # internal ceiling. Keep a five-search safety buffer under the observed
    # 250-search plan while the free Account API remains the hard real-time guard.
    acquisition.DEFAULT_MONTHLY_REQUEST_CAP = max(
        int(acquisition.DEFAULT_MONTHLY_REQUEST_CAP), SAFE_INTERNAL_MONTHLY_CAP
    )
    acquisition.build_row = trusted_source_build_row
    acquisition_quality.prefilter_rejection_reason = policy_aware_prefilter
    supply.select_query_profiles = adaptive_select_query_profiles
    supply.stamp_yield_metadata = adaptive_stamp_yield_metadata


def main() -> None:
    install()
    supply.main()


if __name__ == "__main__":
    main()
