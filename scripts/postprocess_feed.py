#!/usr/bin/env python3
"""Post-process the refreshed feed for stability and usability.

- Drop rows that explicitly contradict full-remote work.
- Collapse duplicate postings with the same normalized company/title.
- Keep a recently seen but missing job for up to 48 hours as REVIEW only.
  This prevents one flaky provider refresh from making the app look empty,
  without pretending the job was rediscovered in the latest scan.
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
CARRYOVER_MAX = timedelta(hours=48)
PUBLISHED_MAX = timedelta(days=30)
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
    # Do not collapse rows solely because they share a generic title. Company is
    # part of the identity; if either side is missing, keep the provider job id.
    if not company or not title:
        return f"id:{jid}"
    return f"{company}|{title}"


def has_remote_contradiction(row: dict) -> bool:
    text = " ".join(
        str(row.get(key) or "") for key in ("title", "location", "snippet")
    ).lower()
    if any(phrase.lower() in text for phrase in REMOTE_CONTRADICTIONS):
        return True
    # The scorer records explicit negative remote signals (hybrid, required
    # office attendance, on-site, etc.) as 注意:... reasons. Because this app is
    # specifically for fully remote work, any such signal is disqualifying even
    # if positive remote wording would otherwise saturate the numeric score.
    return any(
        str(reason or "").strip().startswith("注意:")
        for reason in (row.get("remote_reasons") or [])
    )


def drop_remote_contradictions(rows: list[dict]) -> tuple[list[dict], int]:
    kept = [row for row in rows if not has_remote_contradiction(row)]
    return kept, len(rows) - len(kept)


def row_rank(row: dict) -> tuple[int, int, int, int]:
    return (
        1 if row.get("tier") == "high" else 0,
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
        if has_remote_contradiction(old):
            continue
        last_seen = parse_iso(old.get("last_seen"))
        if not last_seen or now - last_seen > CARRYOVER_MAX:
            continue
        published = parse_iso(old.get("search_published_at"))
        if published and now - published > PUBLISHED_MAX:
            continue

        row = copy.deepcopy(old)
        row["tier"] = "review"
        row["carryover"] = True
        row["carryover_reason"] = "最新スキャンでは未再検出。最大48時間だけ要確認として保持"
        row["freshness_confidence"] = min(int(row.get("freshness_confidence") or 0), 58)
        row["score"] = min(int(row.get("score") or 0), 72)
        carried.append(row)
    return carried


def process(current_payload: dict, previous_payload: dict | None = None) -> dict:
    generated = parse_iso(current_payload.get("generated_at")) or datetime.now(timezone.utc)
    current = [row for row in current_payload.get("jobs", []) if isinstance(row, dict)]
    previous = [row for row in (previous_payload or {}).get("jobs", []) if isinstance(row, dict)]

    current, contradiction_dropped = drop_remote_contradictions(current)
    current, removed = dedupe_rows(current)
    carried = carryover_rows(current, previous, generated)
    combined, removed_after_carry = dedupe_rows(current + carried)
    removed += removed_after_carry

    combined.sort(
        key=lambda row: (
            0 if row.get("tier") == "high" else 1,
            -int(row.get("freshness_confidence") or 0),
            -int(row.get("score") or 0),
            -int(row.get("automation_confidence") or 0),
        )
    )
    current_payload["jobs"] = combined[:80]
    current_payload["deduplicated_jobs"] = removed
    current_payload["remote_contradiction_dropped"] = contradiction_dropped
    current_payload["carryover_jobs"] = sum(1 for row in combined if row.get("carryover"))
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
        f"deduped {result.get('deduplicated_jobs', 0)}, "
        f"remote contradictions {result.get('remote_contradiction_dropped', 0)}, "
        f"carryover {result.get('carryover_jobs', 0)}"
    )


if __name__ == "__main__":
    main()
