#!/usr/bin/env python3
"""Final quality veto for published AI-substitutable remote candidates.

This gate is deliberately asymmetric. Missing LLM coverage never removes a
candidate, so provider/API outages cannot empty the deterministic feed. It does,
however, reject two classes of explicit mismatch before publication:

1. Listing text that requires a human to remain continuously present/online,
   wait for work, monitor in real time, or respond within an immediate SLA.
2. An available LLM audit that confirms physical, synchronous, human-dependent,
   or materially low-automation work.

A fixed work schedule by itself is NOT a blocker: software can run on a schedule.
The blocker is an explicit requirement for continuous human attention.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FEED = ROOT / "data" / "jobs.json"
PRESENCE_GATE_VERSION = 1

# Explicit continuous-presence wording. Keep this narrow: ordinary fixed hours,
# deadlines, or scheduled batch work are not enough to reject a role.
PRESENCE_BLOCKERS = (
    "常時ログイン",
    "常時オンライン",
    "常時接続",
    "常時待機",
    "オンライン待機",
    "待機業務",
    "リアルタイム監視",
    "リアルタイムで監視",
    "即時対応必須",
    "即時応答必須",
    "即レス必須",
    "always online",
    "stay online",
    "remain online",
    "continuous monitoring",
    "real-time monitoring",
    "live monitoring",
    "immediate response required",
    "online throughout the shift",
)

PRESENCE_NEGATIONS = (
    "常時ログイン不要",
    "常時ログインは不要",
    "常時オンライン不要",
    "常時オンラインは不要",
    "常時接続不要",
    "常時接続は不要",
    "オンライン待機なし",
    "オンライン待機不要",
    "待機業務なし",
    "待機業務ではありません",
    "リアルタイム監視なし",
    "リアルタイム監視不要",
    "即時対応不要",
    "即時応答不要",
    "即レス不要",
    "no need to stay online",
    "no continuous monitoring",
    "no real-time monitoring",
    "no immediate response required",
)

PRESENCE_PATTERNS = (
    re.compile(
        r"(?:勤務|稼働|シフト)[^。\n]{0,28}(?:常時|ずっと|常に)[^。\n]{0,16}"
        r"(?:オンライン|ログイン|接続|待機)",
        re.I,
    ),
    re.compile(
        r"(?:勤務|稼働|シフト)[^。\n]{0,28}(?:オンライン|ログイン|接続)[^。\n]{0,16}"
        r"(?:必須|必要)",
        re.I,
    ),
    re.compile(r"(?:5|10|15|20|30)[分分]\s*以内[^。\n]{0,12}(?:返信|応答|回答|対応)", re.I),
    re.compile(r"respond\s+within\s+\d{1,2}\s+minutes?", re.I),
    re.compile(r"(?:must|required to)\s+(?:stay|remain)\s+online", re.I),
)

LLM_PRESENCE_TERMS = (
    "常時",
    "リアルタイム",
    "即時",
    "待機",
    "オンコール",
    "real-time",
    "realtime",
    "immediate",
    "standby",
    "always online",
    "on-call",
)


def _row_text(row: dict) -> str:
    return " ".join(
        str(row.get(key) or "") for key in ("title", "location", "snippet")
    ).lower()


def presence_requirement_signal(row: dict) -> str | None:
    """Return explicit continuous-human-presence evidence, if any."""
    if not isinstance(row, dict):
        return None
    text = _row_text(row)
    scrubbed = text
    # Remove explicit negations before searching positive blocker phrases.
    for phrase in PRESENCE_NEGATIONS:
        scrubbed = scrubbed.replace(phrase.lower(), " ")

    for phrase in PRESENCE_BLOCKERS:
        if phrase.lower() in scrubbed:
            return phrase
    for pattern in PRESENCE_PATTERNS:
        match = pattern.search(scrubbed)
        if match:
            return match.group(0)
    return None


def llm_reject_reason(row: dict) -> str | None:
    review = row.get("llm_review")
    if not isinstance(review, dict):
        return None
    verdict = str(review.get("verdict") or "")
    human = str(review.get("human_dependency") or "")
    sync = str(review.get("synchronous_human_interaction") or "")
    physical = review.get("physical_presence_required")
    try:
        confidence = int(review.get("confidence") or 0)
        automatable = int(review.get("automatable_fraction") or 0)
    except Exception:
        return None
    blockers = [
        str(x or "").strip()
        for x in review.get("blockers") or []
        if str(x or "").strip()
    ]

    if verdict == "reject":
        return "verdict-reject"
    if physical is True:
        return "physical-presence"
    if sync == "frequent":
        return "frequent-sync"
    if human == "high":
        return "high-human-dependency"
    if confidence >= 80 and sync == "occasional":
        return "confirmed-occasional-sync"
    if confidence >= 80 and human == "medium":
        return "confirmed-medium-human-dependency"
    # A reviewed job below 75% end-to-end automation is too weak for this feed.
    if confidence >= 80 and automatable < 75:
        return "confirmed-low-automation"
    blocker_text = " ".join(blockers).lower()
    if confidence >= 75 and any(term.lower() in blocker_text for term in LLM_PRESENCE_TERMS):
        return "confirmed-continuous-presence"
    if confidence >= 85 and blockers and automatable < 90:
        return "confirmed-material-blocker"
    return None


def reject_reason(row: dict) -> str | None:
    if presence_requirement_signal(row):
        return "continuous-human-presence"
    return llm_reject_reason(row)


def apply(payload: dict) -> dict:
    jobs = payload.get("jobs") or []
    if not isinstance(jobs, list):
        return payload
    kept: list[dict] = []
    dropped: list[dict] = []
    reasons: dict[str, int] = {}
    presence_dropped = 0
    llm_dropped = 0

    for row in jobs:
        if not isinstance(row, dict):
            kept.append(row)
            continue
        reason = reject_reason(row)
        if not reason:
            row["continuous_presence_risk"] = "low"
            row["presence_gate_version"] = PRESENCE_GATE_VERSION
            kept.append(row)
            continue
        dropped.append(row)
        reasons[reason] = reasons.get(reason, 0) + 1
        if reason == "continuous-human-presence":
            presence_dropped += 1
        else:
            llm_dropped += 1

    payload["jobs"] = kept
    payload["candidate_presence_gate_version"] = PRESENCE_GATE_VERSION
    payload["candidate_requires_no_continuous_human_presence"] = True
    payload["quality_gate_dropped"] = len(dropped)
    payload["presence_quality_dropped"] = presence_dropped
    payload["llm_quality_dropped"] = llm_dropped
    payload["llm_quality_drop_reasons"] = reasons
    payload["candidate_pool_size"] = len(kept)
    payload["live_jobs"] = sum(
        1 for row in kept if isinstance(row, dict) and not row.get("carryover")
    )
    payload["carryover_jobs"] = sum(
        1 for row in kept if isinstance(row, dict) and row.get("carryover")
    )
    payload["remote_search_only_jobs"] = sum(
        1 for row in kept if isinstance(row, dict) and row.get("remote_search_only")
    )
    target = int(payload.get("candidate_display_target") or 30)
    payload["pool_under_display_target"] = len(kept) < target
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feed", type=Path, default=DEFAULT_FEED)
    args = parser.parse_args()
    payload = json.loads(args.feed.read_text(encoding="utf-8"))
    result = apply(payload)
    args.feed.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"final quality gate kept {len(result.get('jobs', []))} jobs; "
        f"dropped {result.get('quality_gate_dropped', 0)} "
        f"(presence={result.get('presence_quality_dropped', 0)}, "
        f"llm={result.get('llm_quality_dropped', 0)})"
    )


if __name__ == "__main__":
    main()
