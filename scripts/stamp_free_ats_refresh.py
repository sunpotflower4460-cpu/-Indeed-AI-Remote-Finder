#!/usr/bin/env python3
"""Stamp metadata for a no-SerpApi public-ATS-only refresh."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FEED = ROOT / "data" / "jobs.json"
VERSION = 1


def stamp(payload: dict) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    payload["generated_at"] = now
    payload["candidate_free_ats_refresh_version"] = VERSION
    payload["candidate_free_ats_refresh_at"] = now
    payload["candidate_free_ats_refresh_uses_serpapi"] = False
    payload["candidate_free_ats_refresh_mode"] = "official-ats-only"
    payload["candidate_pool_size"] = len(
        [row for row in payload.get("jobs") or [] if isinstance(row, dict)]
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feed", type=Path, default=DEFAULT_FEED)
    args = parser.parse_args()
    payload = json.loads(args.feed.read_text(encoding="utf-8"))
    result = stamp(payload)
    args.feed.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"free ATS refresh stamped; pool={result.get('candidate_pool_size')} "
        "serpapi=false"
    )


if __name__ == "__main__":
    main()
