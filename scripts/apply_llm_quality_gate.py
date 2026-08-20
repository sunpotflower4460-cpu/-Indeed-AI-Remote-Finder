#!/usr/bin/env python3
"""Final quality veto for published AI-substitutable remote candidates.

This gate is deliberately asymmetric. Missing LLM coverage never removes a
candidate, so provider/API outages cannot empty the deterministic feed. It does,
however, reject two classes of explicit mismatch before publication:

1. Listing text that explicitly requires the *human worker* to remain present,
   observable, at their desk/device, or available for human identity checks.
2. An available LLM audit that confirms physical, synchronous, human-dependent,
   or materially low-automation work.

A fixed schedule, an always-on software session, or a fast machine-response SLA
is NOT enough by itself: unattended software can satisfy those technically. The
presence blocker must imply that the person themselves must stay available.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FEED = ROOT / "data" / "jobs.json"
PRESENCE_GATE_VERSION = 1

# Human-presence requirements that software cannot satisfy merely by remaining
# logged in. Keep this narrow so automatable always-on jobs are not discarded.
PRESENCE_BLOCKERS = (
    "カメラ常時on",
    "カメラ常時オン",
    "常時カメラon",
    "常時カメラオン",
    "webカメラ常時on",
    "webカメラ常時オン",
    "zoom常時接続",
    "teams常時接続",
    "meet常時接続",
    "画面共有常時",
    "常時画面共有",
    "pc前で待機",
    "pcの前で待機",
    "パソコン前で待機",
    "パソコンの前で待機",
    "端末前で待機",
    "在席必須",
    "在席確認",
    "離席不可",
    "離席禁止",
    "本人が即時応答",
    "本人による即時応答",
    "本人確認に随時対応",
    "camera on throughout",
    "webcam on throughout",
    "continuous screen sharing",
    "must remain at your computer",
    "must stay at your desk",
    "presence monitoring",
    "random attendance checks",
    "random check-ins",
)

PRESENCE_NEGATIONS = (
    "カメラ常時on不要",
    "カメラ常時オン不要",
    "カメラ常時onではありません",
    "カメラ常時オンではありません",
    "zoom常時接続不要",
    "teams常時接続不要",
    "画面共有常時不要",
    "常時画面共有不要",
    "pc前待機不要",
    "パソコン前待機不要",
    "在席必須ではありません",
    "在席確認なし",
    "在席確認不要",
    "離席可能",
    "離席可",
    "no webcam requirement",
    "camera does not need to stay on",
    "no continuous screen sharing",
    "no presence monitoring",
    "no attendance checks",
)

PRESENCE_PATTERNS = (
    re.compile(
        r"(?:カメラ|webカメラ|webcam|zoom|teams|google\s*meet|meet|画面共有)"
        r"[^。\n]{0,24}(?:常時|ずっと|常に|勤務中|稼働中)[^。\n]{0,16}"
        r"(?:on|オン|接続|共有|必須|必要)",
        re.I,
    ),
    re.compile(
        r"(?:勤務|稼働|シフト)[^。\n]{0,30}(?:カメラ|webcam|画面共有)"
        r"[^。\n]{0,16}(?:on|オン|接続|共有|必須|必要)",
        re.I,
    ),
    re.compile(
        r"(?:pc|パソコン|端末|デスク|席)[^。\n]{0,14}(?:前|に|で)"
        r"[^。\n]{0,12}(?:待機|在席|離席不可|離席禁止)",
        re.I,
    ),
    re.compile(
        r"(?:ランダム|随時|不定期)[^。\n]{0,18}(?:在席確認|本人確認|呼び出し)"
        r"[^。\n]{0,18}(?:即時|すぐ|応答|対応)",
        re.I,
    ),
    re.compile(
        r"(?:本人|作業者|担当者)[^。\n]{0,18}(?:5|10|15|20|30|５|１０|１５|２０|３０)"
        r"\s*分\s*以内[^。\n]{0,12}(?:返信|応答|回答|対応)",
        re.I,
    ),
    re.compile(r"(?:must|required to)\s+(?:remain|stay)\s+(?:at|by)\s+(?:your\s+)?(?:computer|desk)", re.I),
)

LLM_PRESENCE_TERMS = (
    "本人待機",
    "人間の待機",
    "在席",
    "カメラ",
    "webcam",
    "画面共有",
    "本人確認",
    "離席不可",
    "human standby",
    "human presence",
    "at the desk",
    "at the computer",
    "attendance check",
    "presence monitoring",
)


def _row_text(row: dict) -> str:
    return " ".join(
        str(row.get(key) or "") for key in ("title", "location", "snippet")
    ).lower()


def presence_requirement_signal(row: dict) -> str | None:
    """Return explicit human-presence evidence, if any."""
    if not isinstance(row, dict):
        return None
    text = _row_text(row)
    scrubbed = text
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
    if confidence >= 80 and automatable < 75:
        return "confirmed-low-automation"
    blocker_text = " ".join(blockers).lower()
    if confidence >= 75 and any(term.lower() in blocker_text for term in LLM_PRESENCE_TERMS):
        return "confirmed-human-presence"
    if confidence >= 85 and blockers and automatable < 90:
        return "confirmed-material-blocker"
    return None


def reject_reason(row: dict) -> str | None:
    if presence_requirement_signal(row):
        return "continuous-human-presence"
    return llm_reject_reason(row)


def row_is_new_for_refresh(row: dict) -> bool:
    """Identify a first-seen live row using acquisition's persisted lifecycle fields."""
    if not isinstance(row, dict) or row.get("carryover"):
        return False
    try:
        seen_count = int(row.get("seen_count") or 0)
    except (TypeError, ValueError):
        seen_count = 0
    if seen_count == 1:
        return True
    if seen_count > 1:
        return False
    first_seen = str(row.get("first_seen") or "").strip()
    last_seen = str(row.get("last_seen") or "").strip()
    return bool(first_seen and last_seen and first_seen == last_seen)


def apply(payload: dict) -> dict:
    jobs = payload.get("jobs") or []
    if not isinstance(jobs, list):
        return payload
    kept: list[dict] = []
    dropped: list[dict] = []
    all_reasons: dict[str, int] = {}
    presence_reasons: dict[str, int] = {}
    llm_reasons: dict[str, int] = {}

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
        all_reasons[reason] = all_reasons.get(reason, 0) + 1
        if reason == "continuous-human-presence":
            presence_reasons[reason] = presence_reasons.get(reason, 0) + 1
        else:
            llm_reasons[reason] = llm_reasons.get(reason, 0) + 1

    payload["jobs"] = kept
    payload["candidate_presence_gate_version"] = PRESENCE_GATE_VERSION
    payload["candidate_requires_no_continuous_human_presence"] = True
    payload["quality_gate_dropped"] = len(dropped)
    payload["quality_gate_drop_reasons"] = all_reasons
    payload["presence_quality_dropped"] = sum(presence_reasons.values())
    payload["presence_quality_drop_reasons"] = presence_reasons
    payload["llm_quality_dropped"] = sum(llm_reasons.values())
    payload["llm_quality_drop_reasons"] = llm_reasons
    payload["candidate_pool_size"] = len(kept)
    payload["live_jobs"] = sum(
        1 for row in kept if isinstance(row, dict) and not row.get("carryover")
    )
    payload["new_jobs"] = sum(
        1 for row in kept if isinstance(row, dict) and row_is_new_for_refresh(row)
    )
    payload["carryover_jobs"] = sum(
        1 for row in kept if isinstance(row, dict) and row.get("carryover")
    )
    payload["remote_search_only_jobs"] = sum(
        1 for row in kept if isinstance(row, dict) and row.get("remote_search_only")
    )
    payload["llm_reviewed_jobs"] = sum(
        1 for row in kept if isinstance(row, dict) and isinstance(row.get("llm_review"), dict)
    )
    payload["llm_strict_jobs"] = sum(
        1 for row in kept if isinstance(row, dict) and row.get("llm_strict_pass") is True
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
