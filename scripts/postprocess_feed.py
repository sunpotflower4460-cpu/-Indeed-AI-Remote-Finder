#!/usr/bin/env python3
"""Post-process refreshed results into a stable rolling candidate pool.

- Drop rows that explicitly contradict full-remote work.
- Collapse duplicate postings with the same normalized company/title.
- Keep recently seen, autonomy-screened missing jobs for up to 14 days as REVIEW.
- Rank live/new rows ahead of carried reserve rows so the app changes day to day.
- Keep at most 100 ranked candidates in the server-side pool.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FEED = ROOT / "data" / "jobs.json"
CARRYOVER_MAX = timedelta(days=14)
PUBLISHED_MAX = timedelta(days=30)
DISPLAY_TARGET = 30
POOL_LIMIT = 100
REMOTE_CONTRADICTIONS = (
    "フルリモート不可",
    "完全在宅不可",
    "完全リモート不可",
    "100%リモート不可",
    "100％リモート不可",
    "フルリモートではありません",
    "完全在宅ではありません",
    "完全リモートではありません",
    "100%リモートではありません",
    "100％リモートではありません",
    "フルリモートではない",
    "完全在宅ではない",
    "完全リモートではない",
    "100%リモートではない",
    "100％リモートではない",
    "フルリモートではなく",
    "完全在宅ではなく",
    "完全リモートではなく",
    "not fully remote",
    "not 100% remote",
)


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


def normalize_identity(value: str | None) -> str:
    value = unicodedata.normalize("NFKC", value or "").lower()
    value = re.sub(r"[\s\-_–—|｜・/\\()[\]{}【】『』「」]+", "", value)
    return value.strip()


def fingerprint(row: dict) -> str:
    company = normalize_identity(row.get("company"))
    title = normalize_identity(row.get("title"))
    jid = str(row.get("id") or "")
    if not company or not title:
        return f"id:{jid}"
    return f"{company}|{title}"


def hybrid_wording_is_negated(text: str) -> bool:
    if re.search(r"ハイブリッド(?:\s*勤務)?\s*(?:は|が)?\s*(?:不可|なし|ではありません|ではない)", text):
        return True
    return any(phrase in text for phrase in ("not hybrid", "hybrid not allowed"))


def has_remote_contradiction(row: dict) -> bool:
    text = " ".join(str(row.get(key) or "") for key in ("title", "location", "snippet")).lower()
    if any(phrase.lower() in text for phrase in REMOTE_CONTRADICTIONS):
        return True

    hybrid_is_negated = hybrid_wording_is_negated(text)
    for reason in row.get("remote_reasons") or []:
        value = str(reason or "").strip()
        if not value.startswith("注意:"):
            continue
        signal = value.removeprefix("注意:").strip().lower()
        if signal in {"ハイブリッド", "hybrid"} and hybrid_is_negated:
            continue
        return True
    return False


def drop_remote_contradictions(rows: list[dict]) -> tuple[list[dict], int]:
    kept = [row for row in rows if not has_remote_contradiction(row)]
    return kept, len(rows) - len(kept)


def row_rank(row: dict) -> tuple[int, int, int, int, int]:
    return (
        1 if row.get("tier") == "high" else 0,
        1 if not row.get("carryover") else 0,
        int(row.get("freshness_confidence") or 0),
        int(row.get("score") or 0),
        int(row.get("automation_confidence") or 0),
    )


def dedupe_rows(rows: list[dict]) -> tuple[list[dict], int]:
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(fingerprint(row), []).append(row)

    merged: list[dict] = []
    removed = 0
    for group in groups.values():
        group = sorted(group, key=row_rank, reverse=True)
        best = copy.deepcopy(group[0])
        if len(group) > 1:
            removed += len(group) - 1
            locations = []
            for row in group:
                loc = str(row.get("location") or "").strip()
                if loc and loc not in locations:
                    locations.append(loc)
            best["duplicate_count"] = len(group)
            best["alternate_locations"] = locations[:8]
        else:
            best["duplicate_count"] = int(best.get("duplicate_count") or 1)
        merged.append(best)
    return merged, removed


def carryover_rows(current: list[dict], previous: list[dict], now: datetime) -> list[dict]:
    current_ids = {str(row.get("id") or "") for row in current}
    current_fp = {fingerprint(row) for row in current}
    carried: list[dict] = []
    for old in previous:
        jid = str(old.get("id") or "")
        if not jid or jid in current_ids or fingerprint(old) in current_fp:
            continue
        if old.get("tier") not in {"high", "review"}:
            continue
        # Do not retain legacy rows that have never passed the current
        # synchronous-attention/autonomy gate. They may re-enter only if a fresh
        # scan evaluates them under the new policy.
        if old.get("autonomy_attention_risk") != "low":
            continue
        if has_remote_contradiction(old):
            continue
        last_seen = parse_iso(old.get("last_seen"))
        if not last_seen:
            continue
        missing_for = now - last_seen
        if missing_for > CARRYOVER_MAX:
            continue
        published = parse_iso(old.get("search_published_at"))
        if published and now - published > PUBLISHED_MAX:
            continue

        days_missing = max(0, int(missing_for.total_seconds() // 86400))
        row = copy.deepcopy(old)
        row["tier"] = "review"
        row["carryover"] = True
        row["pool_reserve"] = True
        row["carryover_reason"] = "最新スキャンでは未再検出。直近14日以内の予備候補として保持"
        row["freshness_confidence"] = min(
            int(row.get("freshness_confidence") or 0),
            max(34, 58 - days_missing * 2),
        )
        row["score"] = min(int(row.get("score") or 0), max(46, 72 - days_missing * 2))
        carried.append(row)
    return carried


def sort_key(row: dict) -> tuple[int, int, int, int, int, float]:
    first_seen = parse_iso(row.get("first_seen"))
    first_ts = first_seen.timestamp() if first_seen else 0.0
    return (
        0 if row.get("tier") == "high" else 1,
        0 if not row.get("carryover") else 1,
        1 if row.get("remote_search_only") else 0,
        -int(row.get("freshness_confidence") or 0),
        -int(row.get("score") or 0),
        -first_ts,
    )


def process(current_payload: dict, previous_payload: dict | None = None) -> dict:
    generated = parse_iso(current_payload.get("generated_at")) or datetime.now(timezone.utc)
    current = [row for row in current_payload.get("jobs", []) if isinstance(row, dict)]
    previous = [row for row in (previous_payload or {}).get("jobs", []) if isinstance(row, dict)]
    previous_ids = {str(row.get("id") or "") for row in previous}

    current, contradiction_dropped = drop_remote_contradictions(current)
    current, removed = dedupe_rows(current)
    live_ids = {str(row.get("id") or "") for row in current}
    carried = carryover_rows(current, previous, generated)
    combined, removed_after_carry = dedupe_rows(current + carried)
    removed += removed_after_carry

    combined.sort(key=sort_key)
    visible = combined[:POOL_LIMIT]
    current_payload["jobs"] = visible
    current_payload["candidate_pool_size"] = len(visible)
    current_payload["live_jobs"] = sum(1 for row in visible if str(row.get("id") or "") in live_ids)
    current_payload["new_jobs"] = sum(
        1 for row in visible
        if str(row.get("id") or "") not in previous_ids and not row.get("carryover")
    )
    current_payload["remote_search_only_jobs"] = sum(1 for row in visible if row.get("remote_search_only"))
    current_payload["deduplicated_jobs"] = removed
    current_payload["remote_contradiction_dropped"] = contradiction_dropped
    current_payload["carryover_jobs"] = sum(1 for row in visible if row.get("carryover"))
    current_payload["pool_under_display_target"] = len(visible) < int(current_payload.get("candidate_display_target") or DISPLAY_TARGET)
    current_payload["postprocessed"] = True
    return current_payload


def load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feed", type=Path, default=DEFAULT_FEED)
    parser.add_argument("--previous", type=Path)
    args = parser.parse_args()

    current = load(args.feed)
    if not current:
        raise SystemExit(f"feed missing or invalid: {args.feed}")
    previous = load(args.previous) if args.previous else None
    result = process(current, previous)
    args.feed.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"postprocessed {len(result.get('jobs', []))} jobs; "
        f"live {result.get('live_jobs', 0)}, new {result.get('new_jobs', 0)}, "
        f"reserve {result.get('carryover_jobs', 0)}, remote-text-check {result.get('remote_search_only_jobs', 0)}, "
        f"deduped {result.get('deduplicated_jobs', 0)}, "
        f"remote contradictions {result.get('remote_contradiction_dropped', 0)}"
    )


if __name__ == "__main__":
    main()
