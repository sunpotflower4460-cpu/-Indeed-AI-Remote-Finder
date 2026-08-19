#!/usr/bin/env python3
"""Fail CI if the generated job feed violates safety/quality invariants."""
from __future__ import annotations

import argparse
import json
import re
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


def validate_llm(row: dict, prefix: str, errors: list[str]) -> None:
    review = row.get("llm_review")
    strict_flag = row.get("llm_strict_pass")
    if review is None:
        if strict_flag is True:
            errors.append(f"{prefix}.llm_strict_pass true without llm_review")
        return
    if not isinstance(review, dict):
        errors.append(f"{prefix}.llm_review must be an object")
        return
    digest = str(row.get("llm_input_hash") or "")
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        errors.append(f"{prefix}.llm_input_hash invalid")
    if not str(row.get("llm_model") or "").strip():
        errors.append(f"{prefix}.llm_model missing")

    verdict = review.get("verdict")
    human = review.get("human_dependency")
    sync = review.get("synchronous_human_interaction")
    sensitivity = review.get("data_sensitivity_risk")
    if verdict not in {"strong", "uncertain", "reject"}:
        errors.append(f"{prefix}.llm_review.verdict invalid")
    if human not in {"low", "medium", "high"}:
        errors.append(f"{prefix}.llm_review.human_dependency invalid")
    if sync not in {"none", "occasional", "frequent"}:
        errors.append(f"{prefix}.llm_review.synchronous_human_interaction invalid")
    if sensitivity not in {"low", "unknown", "elevated"}:
        errors.append(f"{prefix}.llm_review.data_sensitivity_risk invalid")
    if not isinstance(review.get("physical_presence_required"), bool):
        errors.append(f"{prefix}.llm_review.physical_presence_required must be boolean")
    for key in ("automatable_fraction", "confidence"):
        value = review.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= 100:
            errors.append(f"{prefix}.llm_review.{key} must be 0..100")
    for key in ("automation_plan", "blockers", "questions_to_confirm"):
        value = review.get(key)
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            errors.append(f"{prefix}.llm_review.{key} must be a string list")

    expected_strict = bool(
        verdict == "strong"
        and (review.get("automatable_fraction") or 0) >= 90
        and (review.get("confidence") or 0) >= 80
        and human == "low"
        and review.get("physical_presence_required") is False
        and sync == "none"
        and not (review.get("blockers") or [])
    )
    if review.get("strict_pass") is not expected_strict:
        errors.append(f"{prefix}.llm_review.strict_pass inconsistent")
    if strict_flag is not expected_strict:
        errors.append(f"{prefix}.llm_strict_pass inconsistent")
    if strict_flag is True and row.get("tier") != "high":
        errors.append(f"{prefix} LLM strict pass requires deterministic high tier")


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
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= 100:
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
        validate_llm(row, prefix, errors)

    strict_count = sum(1 for row in jobs if isinstance(row, dict) and row.get("llm_strict_pass") is True)
    reviewed_count = sum(1 for row in jobs if isinstance(row, dict) and isinstance(row.get("llm_review"), dict))
    if payload.get("llm_strict_jobs") is not None and payload.get("llm_strict_jobs") != strict_count:
        errors.append("llm_strict_jobs metadata inconsistent")
    if payload.get("llm_reviewed_jobs") is not None and payload.get("llm_reviewed_jobs") != reviewed_count:
        errors.append("llm_reviewed_jobs metadata inconsistent")
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
