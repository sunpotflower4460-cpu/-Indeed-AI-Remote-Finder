#!/usr/bin/env python3
"""Persist a safe, coarse production-refresh outcome into the public feed."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import acquisition

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FEED = ROOT / "data" / "jobs.json"
DEFAULT_PREVIOUS_FEED = Path("/tmp/previous-jobs.json")
ALLOWED_OUTCOMES = {"success", "failure", "cancelled", "skipped"}


def normalize_outcome(value: object) -> str:
    outcome = str(value or "").strip().lower()
    return outcome if outcome in ALLOWED_OUTCOMES else "unknown"


def resolve_effective_outcome(
    payload: dict,
    previous_payload: dict | None,
    step_outcome: str,
) -> str:
    """Treat an exit-0 no-op as skipped when the feed generation did not move."""
    normalized = normalize_outcome(step_outcome)
    if normalized != "success" or not previous_payload:
        return normalized

    current_generated = str(payload.get("generated_at") or "").strip()
    previous_generated = str(previous_payload.get("generated_at") or "").strip()
    if current_generated and current_generated != previous_generated:
        return "success"
    return "skipped"


def stamp(
    path: Path = DEFAULT_FEED,
    *,
    outcome: str | None = None,
    previous_path: Path | None = None,
) -> dict:
    payload = acquisition.load_payload(path)
    if not payload:
        raise RuntimeError("feed missing or invalid")

    step_outcome = normalize_outcome(
        outcome if outcome is not None else os.environ.get("ACQUISITION_OUTCOME")
    )
    previous_payload = (
        acquisition.load_payload(previous_path)
        if previous_path is not None and previous_path.exists()
        else None
    )
    effective = resolve_effective_outcome(payload, previous_payload, step_outcome)

    payload["candidate_refresh_pipeline_version"] = 2
    payload["candidate_refresh_attempted_at"] = datetime.now(timezone.utc).isoformat()
    payload["candidate_acquisition_step_outcome"] = step_outcome
    payload["candidate_acquisition_outcome"] = effective
    payload["candidate_refresh_preserved_previous_feed"] = effective != "success"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    previous = DEFAULT_PREVIOUS_FEED if DEFAULT_PREVIOUS_FEED.exists() else None
    payload = stamp(previous_path=previous)
    print(
        "Candidate acquisition outcome: "
        f"step={payload.get('candidate_acquisition_step_outcome')} "
        f"effective={payload.get('candidate_acquisition_outcome')} "
        f"preserved_previous={payload.get('candidate_refresh_preserved_previous_feed')}"
    )


if __name__ == "__main__":
    main()
