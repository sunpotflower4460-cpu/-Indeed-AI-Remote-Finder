#!/usr/bin/env python3
"""Production entrypoint with adaptive search-profile ordering.

The underlying acquisition, strict quality gates, source-recovery decision,
provider budget guard, and telemetry remain in acquisition_supply_yield.py.
This wrapper reorders approved search profiles using bounded historical outcomes,
diversifies scarce windows, uses a guarded champion slot, and adds one narrow
policy invariant: listings that explicitly prohibit AI/external-AI assistance
are rejected before they can enter the candidate pool.
"""
from __future__ import annotations

import json

import acquisition
import acquisition_quality
import acquisition_supply_yield as supply
import apply_ai_tool_policy_gate as ai_policy
import profile_precision_v4 as profile_precision


_ORIGINAL_SELECT = supply.select_query_profiles
_ORIGINAL_STAMP = supply.stamp_yield_metadata
_ORIGINAL_PREFILTER = acquisition_quality.prefilter_rejection_reason


def adaptive_select_query_profiles(previous_payload: dict | None) -> list[tuple[str, str]]:
    profiles = _ORIGINAL_SELECT(previous_payload)
    return profile_precision.order_profiles(profiles, previous_payload)


def policy_aware_prefilter(job: dict) -> str | None:
    reason = _ORIGINAL_PREFILTER(job)
    if reason:
        return reason
    status, _ = ai_policy.policy_signal(job)
    if status == "prohibited":
        return "explicit-ai-tool-ban"
    return None


def adaptive_stamp_yield_metadata() -> None:
    _ORIGINAL_STAMP()
    payload = acquisition.load_payload()
    if not payload:
        return
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
    acquisition.OUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def install() -> None:
    acquisition_quality.prefilter_rejection_reason = policy_aware_prefilter
    supply.select_query_profiles = adaptive_select_query_profiles
    supply.stamp_yield_metadata = adaptive_stamp_yield_metadata


def main() -> None:
    install()
    supply.main()


if __name__ == "__main__":
    main()
