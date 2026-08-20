#!/usr/bin/env python3
"""Add current RWS TrainAI Japanese remote data work without SerpApi.

RWS publishes its TrainAI roles on Lever. This supplement queries the documented
Lever postings API with Japan/Tokyo location filters, maps only rows that already
satisfy the existing Japanese/remote/AI-data prefilter, and sends them through
the same production builder used by every other candidate source.

It does not weaken remote, automation, autonomy, presence, LLM, AI-use-policy,
or trusted-application gates, and it never uses a search API or secret.
"""
from __future__ import annotations

import argparse
import json
import urllib.parse
from pathlib import Path

import supplement_public_ats as base
import supplement_targeted_public_ats as targeted

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FEED = ROOT / "data" / "jobs.json"
VERSION = 1
STOCK_TARGET = 100
SITE = "rws"
COMPANY = "RWS TrainAI"
LOCATIONS = ("Tokyo", "Japan")
PAGE_SIZE = 200


def _load(path: Path | None) -> dict:
    if not path:
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _fetch_location(location: str) -> list[dict]:
    params = urllib.parse.urlencode(
        {"mode": "json", "limit": PAGE_SIZE, "skip": 0, "location": location}
    )
    payload = base._fetch_json(
        f"https://api.lever.co/v0/postings/{SITE}?{params}"
    )
    if not isinstance(payload, list):
        raise RuntimeError("RWS Lever response is not a list")
    return [row for row in payload if isinstance(row, dict)]


def _fetch_rws_japan() -> tuple[list[dict], dict[str, int]]:
    by_key: dict[str, dict] = {}
    stats: dict[str, int] = {}
    for location in LOCATIONS:
        rows = _fetch_location(location)
        stats[f"raw_{location.lower()}"] = len(rows)
        for row in rows:
            key = str(row.get("id") or row.get("applyUrl") or row.get("hostedUrl") or "")
            if key:
                by_key[key] = row
    return list(by_key.values()), stats


def _map(posts: list[dict]) -> list[dict]:
    mapped: list[dict] = []
    for post in posts:
        row = base._map_lever(post, SITE, COMPANY)
        if not row:
            continue
        row["_target_category"] = row.pop(
            "_public_ats_category", "targeted_ats_rws_trainai_japan"
        )
        row["_target_published"] = row.pop("_public_ats_published_at", None)
        row.pop("_public_ats_remote_structured", None)
        row["_target_provider"] = COMPANY
        mapped.append(row)
    return mapped


def supplement(
    payload: dict,
    previous_payload: dict | None = None,
    *,
    posts: list[dict] | None = None,
) -> dict:
    before = len([row for row in payload.get("jobs") or [] if isinstance(row, dict)])
    payload["candidate_rws_trainai_version"] = VERSION
    payload["candidate_rws_trainai_uses_serpapi"] = False
    payload["candidate_rws_trainai_quality_gate_unchanged"] = True
    payload["candidate_rws_trainai_pool_before"] = before

    if before >= STOCK_TARGET:
        payload["candidate_rws_trainai_skipped"] = "pool-at-or-above-user-stock-target"
        payload["candidate_rws_trainai_pool_after"] = before
        return payload

    errors: list[str] = []
    stats: dict[str, int] = {}
    if posts is None:
        try:
            posts, stats = _fetch_rws_japan()
        except Exception as exc:
            posts = []
            errors.append(f"rws:{type(exc).__name__}")
    else:
        stats["raw_override"] = len(posts)

    mapped = _map(posts)
    result, accepted_by_provider, accepted = targeted._build_rows(
        payload, previous_payload or {}, mapped
    )
    after = len([row for row in result.get("jobs") or [] if isinstance(row, dict)])
    result["candidate_rws_trainai_raw"] = len(posts)
    result["candidate_rws_trainai_mapped"] = len(mapped)
    result["candidate_rws_trainai_deterministic_accepted"] = accepted
    result["candidate_rws_trainai_accepted_by_provider"] = dict(accepted_by_provider)
    result["candidate_rws_trainai_stats"] = stats
    result["candidate_rws_trainai_errors"] = errors
    result["candidate_rws_trainai_pool_after"] = after
    result["candidate_rws_trainai_user_stock_ready"] = after >= STOCK_TARGET
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feed", type=Path, default=DEFAULT_FEED)
    parser.add_argument("--previous", type=Path)
    args = parser.parse_args()
    payload = _load(args.feed)
    if not payload:
        raise SystemExit(f"feed missing or invalid: {args.feed}")
    result = supplement(payload, _load(args.previous))
    args.feed.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        "RWS TrainAI supplement: "
        f"raw={result.get('candidate_rws_trainai_raw', 0)} "
        f"mapped={result.get('candidate_rws_trainai_mapped', 0)} "
        f"accepted={result.get('candidate_rws_trainai_deterministic_accepted', 0)} "
        f"pool={result.get('candidate_rws_trainai_pool_after')}"
    )


if __name__ == "__main__":
    main()
