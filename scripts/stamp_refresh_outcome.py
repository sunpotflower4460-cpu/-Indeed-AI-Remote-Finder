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
ALLOWED_OUTCOMES = {"success", "failure", "cancelled", "skipped"}


def normalize_outcome(value: object) -> str:
    outcome = str(value or "").strip().lower()
    return outcome if outcome in ALLOWED_OUTCOMES else "unknown"


def stamp(path: Path = DEFAULT_FEED, *, outcome: str | None = None) -> dict:
    payload = acquisition.load_payload(path)
    if not payload:
        raise RuntimeError("feed missing or invalid")
    normalized = normalize_outcome(
        outcome if outcome is not None else os.environ.get("ACQUISITION_OUTCOME")
    )
    payload["candidate_refresh_pipeline_version"] = 1
    payload["candidate_refresh_attempted_at"] = datetime.now(timezone.utc).isoformat()
    payload["candidate_acquisition_outcome"] = normalized
    payload["candidate_refresh_preserved_previous_feed"] = normalized != "success"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    payload = stamp()
    print(
        "Candidate acquisition outcome: "
        f"{payload.get('candidate_acquisition_outcome')} "
        f"preserved_previous={payload.get('candidate_refresh_preserved_previous_feed')}"
    )


if __name__ == "__main__":
    main()
