#!/usr/bin/env python3
"""Production entrypoint with adaptive search-profile ordering.

The underlying acquisition, strict quality gates, source-recovery decision,
provider budget guard, and telemetry remain in acquisition_supply_yield.py.
This wrapper only reorders the already-approved search profiles using bounded,
privacy-safe historical aggregate outcomes, including whether deterministic
candidates actually survive the downstream final quality gates.
"""
from __future__ import annotations

import json

import acquisition
import acquisition_supply_yield as supply
import profile_precision_v2 as profile_precision


_ORIGINAL_SELECT = supply.select_query_profiles
_ORIGINAL_STAMP = supply.stamp_yield_metadata


def adaptive_select_query_profiles(previous_payload: dict | None) -> list[tuple[str, str]]:
    profiles = _ORIGINAL_SELECT(previous_payload)
    return profile_precision.order_profiles(profiles, previous_payload)


def adaptive_stamp_yield_metadata() -> None:
    _ORIGINAL_STAMP()
    payload = acquisition.load_payload()
    if not payload:
        return
    payload.update(profile_precision.learning_metadata(payload))
    acquisition.OUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def install() -> None:
    supply.select_query_profiles = adaptive_select_query_profiles
    supply.stamp_yield_metadata = adaptive_stamp_yield_metadata


def main() -> None:
    install()
    supply.main()


if __name__ == "__main__":
    main()
