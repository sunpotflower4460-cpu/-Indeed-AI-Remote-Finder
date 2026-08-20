#!/usr/bin/env python3
"""Reject candidates that explicitly prohibit AI/external-AI assistance.

Technical automability is not equivalent to employer permission. This gate is
narrow by design: it rejects only explicit prohibition language found in the
listing text. When permission is not stated, the candidate remains eligible but
is stamped as requiring confirmation before any AI-assisted execution.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FEED = ROOT / "data" / "jobs.json"
AI_TOOL_POLICY_GATE_VERSION = 1

PROHIBITED_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("jp-generative-ai-ban", re.compile(r"(?:生成\s*ai|ai\s*ツール|chatgpt|外部\s*ai)[^。\n]{0,24}(?:使用|利用)[^。\n]{0,16}(?:禁止|不可|認められません|認めない)", re.I)),
    ("jp-no-ai-assistance", re.compile(r"(?:生成\s*ai|ai\s*ツール|chatgpt|外部\s*ai)[^。\n]{0,18}(?:を)?(?:使わない|使用しない|利用しない|使わず|使用せず|利用せず)", re.I)),
    ("en-ai-tools-prohibited", re.compile(r"(?:use of\s+)?(?:generative\s+ai|ai\s+tools?|chatgpt|external\s+ai)[^.\n]{0,28}(?:prohibited|forbidden|not\s+allowed|not\s+permitted)", re.I)),
    ("en-no-ai-assistance", re.compile(r"(?:without|no)\s+(?:generative\s+)?ai\s+(?:assistance|tools?|help)", re.I)),
    ("en-do-not-use-ai", re.compile(r"(?:do\s+not|must\s+not|cannot|can't)\s+use\s+(?:generative\s+)?ai(?:\s+tools?)?", re.I)),
)

ALLOWED_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("jp-generative-ai-allowed", re.compile(r"(?:生成\s*ai|ai\s*ツール|chatgpt)[^。\n]{0,18}(?:使用|利用)[^。\n]{0,10}(?:可|可能|ok|ＯＫ|認める|認められ)", re.I)),
    ("en-ai-tools-allowed", re.compile(r"(?:generative\s+ai|ai\s+tools?|chatgpt)[^.\n]{0,24}(?:allowed|permitted|may\s+be\s+used|can\s+be\s+used)", re.I)),
    ("en-may-use-ai", re.compile(r"(?:may|can)\s+use\s+(?:generative\s+)?ai(?:\s+tools?)?", re.I)),
)


def row_text(row: dict) -> str:
    return " ".join(str(row.get(key) or "") for key in ("title", "snippet", "location")).lower()


def policy_signal(row: dict) -> tuple[str, str | None]:
    text = row_text(row)
    for code, pattern in PROHIBITED_PATTERNS:
        if pattern.search(text):
            return "prohibited", code
    for code, pattern in ALLOWED_PATTERNS:
        if pattern.search(text):
            return "explicitly-allowed", code
    return "not-stated", None


def apply(payload: dict) -> dict:
    jobs = payload.get("jobs") or []
    if not isinstance(jobs, list):
        return payload

    kept: list[dict] = []
    dropped = 0
    allowed = 0
    unknown = 0
    reasons: dict[str, int] = {}
    for row in jobs:
        if not isinstance(row, dict):
            kept.append(row)
            continue
        status, signal = policy_signal(row)
        if status == "prohibited":
            dropped += 1
            key = signal or "explicit-ai-tool-ban"
            reasons[key] = reasons.get(key, 0) + 1
            continue
        row["ai_tool_policy_gate_version"] = AI_TOOL_POLICY_GATE_VERSION
        row["ai_tool_policy_status"] = status
        row["ai_tool_policy_signal"] = signal
        row["ai_tool_use_permission_confirm_required"] = status != "explicitly-allowed"
        if status == "explicitly-allowed":
            allowed += 1
        else:
            unknown += 1
        kept.append(row)

    payload["jobs"] = kept
    payload["candidate_ai_tool_policy_gate_version"] = AI_TOOL_POLICY_GATE_VERSION
    payload["candidate_rejects_explicit_ai_tool_bans"] = True
    payload["candidate_ai_tool_policy_dropped"] = dropped
    payload["candidate_ai_tool_policy_drop_reasons"] = reasons
    payload["candidate_ai_tool_policy_explicitly_allowed"] = allowed
    payload["candidate_ai_tool_policy_confirmation_required"] = unknown
    payload["candidate_pool_size"] = len(kept)
    payload["live_jobs"] = sum(1 for row in kept if isinstance(row, dict) and not row.get("carryover"))
    payload["carryover_jobs"] = sum(1 for row in kept if isinstance(row, dict) and row.get("carryover"))
    payload["new_jobs"] = sum(
        1
        for row in kept
        if isinstance(row, dict)
        and not row.get("carryover")
        and int(row.get("seen_count") or 0) == 1
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feed", type=Path, default=DEFAULT_FEED)
    args = parser.parse_args()
    payload = json.loads(args.feed.read_text(encoding="utf-8"))
    result = apply(payload)
    args.feed.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        "AI tool policy gate kept "
        f"{len(result.get('jobs', []))} jobs; dropped {result.get('candidate_ai_tool_policy_dropped', 0)}"
    )


if __name__ == "__main__":
    main()
