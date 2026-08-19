#!/usr/bin/env python3
"""Fail if a published candidate violates remote/autonomy quality invariants."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FEED = ROOT / "data" / "jobs.json"
QUALITY_GATE = "async-ai-remote"
REVIEW_AUTOMATION_MIN = 55
REVIEW_HUMAN_RISK_MAX = 25
EXPLICIT_FULL_REMOTE = {
    "完全在宅",
    "フルリモート",
    "完全リモート",
    "100%リモート",
    "100％リモート",
    "fully remote",
    "100% remote",
}
PARTIAL_REMOTE_PHRASES = (
    "一部在宅",
    "一部リモート",
    "ハイブリッド勤務",
    "ハイブリッドワーク",
    "在宅あり",
    "リモートあり",
    "出社あり",
    "出社併用",
    "在宅併用",
    "リモート併用",
    "テレワーク併用",
    "慣れたら在宅",
    "慣れたらリモート",
    "慣れてから在宅",
    "慣れてからリモート",
)
REMOTE_NEGATIONS = (
    "ハイブリッド勤務は不可",
    "ハイブリッド勤務不可",
    "ハイブリッド不可",
    "一部在宅ではありません",
    "一部リモートではありません",
    "出社併用なし",
    "出社併用不要",
)
REMOTE_WEEKLY_PATTERNS = (
    re.compile(r"(?:在宅(?:勤務|ワーク)?|リモート(?:勤務|ワーク)?|テレワーク)\s*週\s*[1-6１-６一二三四五六]\s*(?:[～〜~\-－ー]\s*[1-6１-６一二三四五六])?\s*日", re.I),
    re.compile(r"週\s*[1-6１-６一二三四五六]\s*(?:[～〜~\-－ー]\s*[1-6１-６一二三四五六])?\s*日\s*(?:程度\s*)?(?:の)?\s*(?:在宅|リモート|テレワーク)", re.I),
    re.compile(r"(?:在宅|リモート|テレワーク)\s*(?:勤務)?\s*月\s*[1-9１-９]\s*回", re.I),
    re.compile(r"月\s*[1-9１-９]\s*回\s*(?:程度\s*)?(?:の)?\s*(?:在宅|リモート|テレワーク)", re.I),
)


def _quality_active(payload: dict) -> bool:
    try:
        return int(payload.get("candidate_quality_policy_version") or 0) >= 1
    except Exception:
        return False


def _row_text(row: dict) -> str:
    return " ".join(str(row.get(key) or "") for key in ("title", "location", "snippet")).lower()


def partial_remote_signal(row: dict) -> str | None:
    text = _row_text(row)
    for phrase in REMOTE_NEGATIONS:
        text = text.replace(phrase.lower(), " ")
    for phrase in PARTIAL_REMOTE_PHRASES:
        if phrase.lower() in text:
            return phrase
    for pattern in REMOTE_WEEKLY_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(0)
    return None


def validate(payload: dict) -> list[str]:
    errors: list[str] = []
    jobs = payload.get("jobs")
    if not isinstance(jobs, list):
        return ["jobs must be a list"]

    malformed = payload.get("malformed_jobs")
    if malformed is not None and (
        not isinstance(malformed, int) or isinstance(malformed, bool) or malformed < 0
    ):
        errors.append("malformed_jobs must be a non-negative integer")

    quality_active = _quality_active(payload)

    for index, row in enumerate(jobs):
        if not isinstance(row, dict):
            continue
        prefix = f"jobs[{index}]"
        reasons = row.get("remote_reasons") or []
        if not isinstance(reasons, list):
            errors.append(f"{prefix}.remote_reasons must be a list")
            continue
        normalized = {str(value or "").strip().lower() for value in reasons}
        warnings = [value for value in normalized if value.startswith("注意:")]
        if warnings:
            errors.append(f"{prefix} contains contradictory remote signal: {sorted(warnings)[0]}")

        explicit_remote = any(
            phrase.lower() in normalized for phrase in EXPLICIT_FULL_REMOTE
        )
        if row.get("tier") == "high" and not explicit_remote:
            errors.append(f"{prefix} high tier lacks explicit full-remote evidence")

        remote_search_only = row.get("remote_search_only")
        if remote_search_only not in {None, True, False}:
            errors.append(f"{prefix}.remote_search_only must be boolean")
        if remote_search_only is True:
            if row.get("tier") != "review":
                errors.append(f"{prefix} remote-search-only row must be review tier")
            tags = row.get("tags") or []
            if not isinstance(tags, list) or "在宅要確認" not in tags:
                errors.append(f"{prefix} remote-search-only row must show 在宅要確認 tag")

        if quality_active:
            if row.get("quality_gate") != QUALITY_GATE:
                errors.append(f"{prefix} missing current quality gate")
            if row.get("autonomy_attention_risk") != "low":
                errors.append(f"{prefix} autonomy attention risk is not low")
            if remote_search_only is True:
                errors.append(f"{prefix} quality feed cannot contain remote-search-only rows")
            if not explicit_remote:
                errors.append(f"{prefix} quality feed lacks explicit full-remote evidence")
            partial = partial_remote_signal(row)
            if partial:
                errors.append(f"{prefix} contains partial/hybrid remote wording: {partial}")
            if row.get("tier") == "review":
                automation = int(row.get("automation_confidence") or 0)
                risk = int(row.get("human_dependency_risk") or 0)
                if automation < REVIEW_AUTOMATION_MIN:
                    errors.append(
                        f"{prefix} review automation {automation} below {REVIEW_AUTOMATION_MIN}"
                    )
                if risk > REVIEW_HUMAN_RISK_MAX:
                    errors.append(
                        f"{prefix} review human risk {risk} above {REVIEW_HUMAN_RISK_MAX}"
                    )

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
    print(f"remote feed validation passed: {len(payload.get('jobs', []))} jobs")


if __name__ == "__main__":
    main()
