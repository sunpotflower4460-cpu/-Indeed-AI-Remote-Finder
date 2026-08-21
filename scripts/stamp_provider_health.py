#!/usr/bin/env python3
"""Persist safe SerpApi guard diagnostics without exposing account secrets.

This script intentionally stores only coarse operational state needed to explain
why a scheduled refresh did or did not search. Raw account responses, email,
API keys, and provider error text are never written to the public feed.

The workflow runs this immediately after the Indeed web-index supplement. Before
stamping provider health, it verifies that the current v2 Indeed discovery step
actually wrote its runtime telemetry, then applies the fail-closed company-evidence
hardening pass before any candidate can reach postprocessing or final validation.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import acquisition
import acquisition_remote
import harden_indeed_index_matches
import validate_indeed_discovery_runtime

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FEED = ROOT / "data" / "jobs.json"


def safe_status(api_key: str) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    if not api_key:
        return {
            "serpapi_guard_checked_at": now,
            "serpapi_guard_status": "not-configured",
            "serpapi_safe_request_headroom": None,
        }
    try:
        account = acquisition_remote.fetch_serpapi_account(api_key)
        headroom = acquisition_remote.provider_request_budget(account)
        month_usage = acquisition_remote.provider_month_usage(account)
    except Exception:
        return {
            "serpapi_guard_checked_at": now,
            "serpapi_guard_status": "account-check-unavailable",
            "serpapi_safe_request_headroom": None,
        }

    status = "ready"
    if headroom == 0:
        status = "no-safe-request-headroom"
    result = {
        "serpapi_guard_checked_at": now,
        "serpapi_guard_status": status,
        "serpapi_safe_request_headroom": headroom,
    }
    if month_usage is not None:
        result["serpapi_provider_month_usage"] = month_usage
    return result


def stamp(path: Path = DEFAULT_FEED, *, api_key: str | None = None) -> dict:
    payload = acquisition.load_payload(path)
    if not payload:
        raise RuntimeError("feed missing or invalid")
    payload.update(safe_status((api_key if api_key is not None else os.environ.get("SERPAPI_KEY", "")).strip()))
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    # The index supplement runs immediately before this workflow step. Fail
    # visibly if it crashed before writing current telemetry instead of silently
    # carrying a stale zero-result feed forward.
    validate_indeed_discovery_runtime.validate(
        validate_indeed_discovery_runtime.load_payload(DEFAULT_FEED)
    )
    # Then apply truth-first disambiguation before adding provider telemetry or
    # allowing postprocess/final gates to see promoted rows.
    harden_indeed_index_matches.main()
    payload = stamp()
    print(
        "SerpApi guard status: "
        f"{payload.get('serpapi_guard_status')} "
        f"headroom={payload.get('serpapi_safe_request_headroom')}"
    )


if __name__ == "__main__":
    main()
