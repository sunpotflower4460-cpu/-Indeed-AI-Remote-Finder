#!/usr/bin/env python3
"""Fail CI if the generated job feed violates safety/quality invariants."""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FEED = ROOT / "data" / "jobs.json"


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def validate(payload: dict) -> list[str]:
    errors: list[str] = []
    generated = parse_iso(payload.get("generated_at"))
    if not generated:
        errors.append("generated_at is missing/invalid")
        generated = datetime.now(timezone.utc)

    jobs = payload.get("jobs")
    if not isinstance(jobs, list):
        return errors + ["jobs must be a list"]
    if len(jobs) > 80:
        errors.append(f"jobs exceeds limit: {len(jobs)}")

    ids: set[str] = set()
    for i, row in enumerate(jobs):
        prefix = f"jobs[{i}]"
        if not isinstance(row, dict):
            errors.append(f"{prefix} must be an object")
            continue
        jid = str(row.get("id") or "")
        if not jid:
            errors.append(f"{prefix}.id missing")
        elif jid in ids:
            errors.append(f"duplicate id: {jid}")
        ids.add(jid)

        if not str(row.get("title") or "").strip():
            errors.append(f"{prefix}.title missing")

        url = str(row.get("url") or "")
        parsed = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qs(parsed.query)
        host = parsed.netloc.lower()
        url_jid = (params.get("jk") or [""])[0]
        if host != "jp.indeed.com" or parsed.path.lower() != "/viewjob" or not url_jid or url_jid != jid:
            errors.append(f"{prefix}.url is not canonical Indeed viewjob for id={jid}")

        for key in ("score", "automation_confidence", "remote_confidence", "freshness_confidence", "human_dependency_risk"):
            value = row.get(key)
            if not isinstance(value, (int, float)) or not 0 <= value <= 100:
                errors.append(f"{prefix}.{key} must be 0..100")

        tier = row.get("tier")
        if tier not in {"high", "review"}:
            errors.append(f"{prefix}.tier invalid: {tier!r}")
        if tier == "high":
            if (row.get("automation_confidence") or 0) < 82:
                errors.append(f"{prefix} high tier automation < 82")
            if (row.get("remote_confidence") or 0) < 82:
                errors.append(f"{prefix} high tier remote < 82")
            risk = row.get("human_dependency_risk")
            if not isinstance(risk, (int, float)) or risk > 8:
                errors.append(f"{prefix} high tier human risk > 8")
            published = parse_iso(row.get("search_published_at"))
            if not published:
                errors.append(f"{prefix} high tier requires known publish time")
            elif generated - published > timedelta(days=14, hours=1):
                errors.append(f"{prefix} high tier is older than 14 days")

        published = parse_iso(row.get("search_published_at"))
        if published and published > generated + timedelta(hours=1):
            errors.append(f"{prefix} publish time is in the future")

    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feed", type=Path, default=DEFAULT_FEED)
    args = parser.parse_args()
    try:
        payload = json.loads(args.feed.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"invalid JSON: {exc}", file=sys.stderr)
        raise SystemExit(1)
    errors = validate(payload)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
    print(f"feed validation passed: {len(payload.get('jobs', []))} jobs")


if __name__ == "__main__":
    main()
