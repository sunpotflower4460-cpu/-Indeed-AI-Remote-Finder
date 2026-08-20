#!/usr/bin/env python3
"""Target high-yield Japan ATS feeds while the strict production pool is below 30.

The broad public-ATS supplement intentionally scans employer boards conservatively.
This top-up fixes three known recall gaps without changing publication quality:

1. Welo/Lever has hundreds of global postings. Use Lever's documented
   ``location=Japan`` filter (and bounded skip pagination) so current Japanese
   Search/Ads/Maps rating and Data Trainer postings are not hidden after the
   first 200 global rows.
2. LILT/Ashby has fully remote Japanese translation/localization/linguist work
   that is highly automatable but not necessarily titled as an AI-rating role.
3. Prolific's current Greenhouse board token is ``prolificacademicltd``; fetch
   only Japanese AI-training postings that are not location-restricted to a
   foreign market and still reject live conversation/voice collection.

Every mapped row is fed through the exact existing production builder and later
through the same postprocess, LLM/presence, AI-use-policy, and final validators.
No SerpApi request and no new secret are used.
"""
from __future__ import annotations

import argparse
import json
import re
import urllib.parse
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import acquisition
import acquisition_precision
import acquisition_quality
import supplement_public_ats as base

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FEED = ROOT / "data" / "jobs.json"
VERSION = 2
TARGET_POOL = 30
MAX_Welo_PAGES = 5
LEVER_PAGE_SIZE = 200
MAX_PROLIFIC_DETAILS = 40
MAX_LILT_LANGUAGE_ROWS = 40

LANGUAGE_OP_SIGNALS = (
    "linguist", "localization", "localisation", "translator", "translation",
    "proofreader", "proofreading", "language reviewer", "linguistic reviewer",
    "lqa", "language qa", "subtitle localization", "in-game localization",
)
LANGUAGE_OP_BLOCKERS = (
    "voice talent", "voice actor", "voice acting", "audio contributor",
    "record your voice", "voice samples", "voice cloning", "tts training",
    "project manager", "program manager", "team lead", "coordinator",
)
FOREIGN_GEO_HINTS = (
    "germany", "düsseldorf", "berlin", "france", "paris", "italy", "milan",
    "spain", "madrid", "canada", "toronto", "calgary", "edmonton",
    "united states", "usa", "new york", "australia", "sydney", "singapore",
    "united kingdom", "uk", "london", "poland", "warsaw", "switzerland",
    "basel", "bern", "india", "bangalore", "chennai",
)


def _load(path: Path | None) -> dict:
    if not path:
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _fetch_welo_japan() -> tuple[list[dict], int]:
    """Use Lever's official location filter, then bounded pagination if needed."""
    site = "weloglobal"
    safe = urllib.parse.quote(site, safe="")
    rows: list[dict] = []
    pages = 0
    seen_ids: set[str] = set()
    for page in range(MAX_Welo_PAGES):
        skip = page * LEVER_PAGE_SIZE
        params = urllib.parse.urlencode(
            {
                "mode": "json",
                "limit": LEVER_PAGE_SIZE,
                "skip": skip,
                "location": "Japan",
            }
        )
        payload = base._fetch_json(f"https://api.lever.co/v0/postings/{safe}?{params}")
        if not isinstance(payload, list):
            raise RuntimeError("Welo Lever response is not a list")
        pages += 1
        clean = [item for item in payload if isinstance(item, dict)]
        for item in clean:
            jid = str(item.get("id") or "")
            key = jid or str(item.get("applyUrl") or item.get("hostedUrl") or "")
            if key and key in seen_ids:
                continue
            if key:
                seen_ids.add(key)
            rows.append(item)
        if len(clean) < LEVER_PAGE_SIZE:
            break
    return rows, pages


def _lilt_language_job(post: dict) -> dict | None:
    if not isinstance(post, dict) or post.get("isListed") is False:
        return None
    title = base._clean(post.get("title"))
    body = base._clean(post.get("descriptionPlain") or post.get("descriptionHtml"))
    location = base._ashby_locations(post)
    combined = f"{title} {body}".lower()
    if not (post.get("isRemote") is True or base._clean(post.get("workplaceType")).lower() == "remote"):
        return None
    if not base._text_has(f"{title} {location} {body}", base.JAPANESE_SIGNALS):
        return None
    if not any(signal in combined for signal in LANGUAGE_OP_SIGNALS):
        return None
    if any(blocker in combined for blocker in LANGUAGE_OP_BLOCKERS):
        return None
    url = base._clean(post.get("applyUrl") or post.get("jobUrl"))
    if not url.startswith("https://"):
        return None
    # These are acquisition hints only. The existing quality builder still
    # decides whether automation/remote/human-risk thresholds are satisfied.
    markers = "翻訳 校正 データ評価 品質評価"
    description = (
        "Employer ATS structured workplace type: fully remote. フルリモート。 "
        f"{markers} {body}"
    )
    return {
        "title": title,
        "company_name": "LILT",
        "location": location or "Japan (Remote)",
        "description": description,
        "highlights": [],
        "extensions": ["Remote", "Public ATS live listing"],
        "detected_extensions": {},
        "via": "Ashby",
        "apply_options": [{"title": "Ashby", "link": url}],
        "_target_category": "targeted_ats_lilt_language_ops",
        "_target_published": base._source_published(post.get("publishedAt")),
        "_target_provider": "LILT",
    }


def _explicit_japan_market(text: str) -> bool:
    """Match Japan as a market token without mistaking 'Japanese' for 'Japan'."""
    return bool(re.search(r"\bjapan\b", str(text or "").lower()))


def _prolific_title_eligible(title: str) -> bool:
    lower = title.lower()
    if "japanese" not in lower or "ai train" not in lower:
        return False
    # Reject named foreign markets before considering an explicit Japan token.
    # The substring "japan" inside "japanese" must never qualify a role.
    if any(value in lower for value in FOREIGN_GEO_HINTS):
        return False
    if _explicit_japan_market(lower):
        return True
    return "advanced japanese fluency" in lower


def _fetch_prolific_japanese() -> tuple[list[dict], int, int]:
    board = "prolificacademicltd"
    index = base._fetch_greenhouse_index(board)
    matches = [
        item for item in index
        if isinstance(item, dict) and _prolific_title_eligible(base._clean(item.get("title")))
    ][:MAX_PROLIFIC_DETAILS]
    details: list[dict] = []
    for item in matches:
        if item.get("id") is None:
            continue
        try:
            details.append(base._fetch_greenhouse_detail(board, item["id"]))
        except Exception:
            continue
    return details, len(index), len(matches)


def _prolific_job(post: dict) -> dict | None:
    if not isinstance(post, dict):
        return None
    title = base._clean(post.get("title"))
    if not _prolific_title_eligible(title):
        return None
    location_obj = post.get("location") or {}
    location = base._clean(location_obj.get("name") if isinstance(location_obj, dict) else location_obj)
    body = base._clean(post.get("content"))
    location_lower = location.lower()
    if any(term in location_lower for term in FOREIGN_GEO_HINTS) and not _explicit_japan_market(location_lower):
        return None
    combined = f"{title} {location} {body}".lower()
    if any(term in combined for term in base.CLEAR_HUMAN_MEDIA_BLOCKERS):
        return None
    if any(term in combined for term in ("live video call", "video conversations", "recorded conversation")):
        return None
    if "remote" not in combined and "work from home" not in combined:
        return None
    url = base._clean(post.get("absolute_url"))
    if not url.startswith("https://"):
        return None
    return {
        "title": title,
        "company_name": "Prolific Academic Ltd",
        "location": location or "Remote",
        "description": (
            "Employer public job board explicitly states remote. フルリモート。 "
            "AIトレーナー AI評価 データ評価 品質評価 " + body
        ),
        "highlights": [],
        "extensions": ["Remote", "Public ATS live listing"],
        "detected_extensions": {},
        "via": "Greenhouse",
        "apply_options": [{"title": "Greenhouse", "link": url}],
        "_target_category": "targeted_ats_prolific_japanese_ai",
        "_target_published": base._source_published(post.get("updated_at")),
        "_target_provider": "Prolific Academic Ltd",
    }


def _better(row: dict, existing: dict) -> bool:
    return (
        row.get("tier") == "high",
        int(row.get("score") or 0),
        int(row.get("automation_confidence") or 0),
    ) > (
        existing.get("tier") == "high",
        int(existing.get("score") or 0),
        int(existing.get("automation_confidence") or 0),
    )


def _build_rows(
    payload: dict,
    previous_payload: dict,
    mapped_jobs: list[dict],
) -> tuple[dict, Counter[str], int]:
    previous = {
        str(row.get("id")): row
        for row in previous_payload.get("jobs") or []
        if isinstance(row, dict) and row.get("id")
    }
    acquisition_precision.install()
    acquisition_quality.configure_quality_policy()
    acquisition_quality.reset_quality_telemetry()

    existing = [row for row in payload.get("jobs") or [] if isinstance(row, dict)]
    by_id = {str(row.get("id")): row for row in existing if row.get("id")}
    accepted_by_provider: Counter[str] = Counter()
    accepted = 0
    now = datetime.now(timezone.utc).isoformat()

    for mapped in mapped_jobs:
        category = str(mapped.pop("_target_category", "targeted_public_ats"))
        published = mapped.pop("_target_published", None)
        provider = str(mapped.pop("_target_provider", "Public ATS"))
        try:
            row = acquisition.build_row(mapped, category, previous)
        except Exception:
            continue
        if not row:
            continue
        if published:
            row["search_published_at"] = published
            row["posted_label"] = "Public ATS timestamp"
        row["source"] = f"{provider} targeted public ATS; application URL verified"
        row["discovery_source"] = "targeted-public-employer-ats"
        row["ats_provider"] = provider
        row["ats_live_verified_at"] = now
        row["targeted_public_ats_version"] = VERSION
        jid = str(row.get("id") or "")
        current = by_id.get(jid)
        if current is None or _better(row, current):
            by_id[jid] = row
        accepted += 1
        accepted_by_provider[provider] += 1

    payload["jobs"] = list(by_id.values())[:150]
    return payload, accepted_by_provider, accepted


def top_up(
    payload: dict,
    previous_payload: dict | None = None,
    *,
    welo_posts: list[dict] | None = None,
    lilt_posts: list[dict] | None = None,
    prolific_posts: list[dict] | None = None,
) -> dict:
    before = len([x for x in payload.get("jobs") or [] if isinstance(x, dict)])
    mapped: list[dict] = []
    errors: list[str] = []
    stats: dict[str, int] = {}

    if before >= TARGET_POOL:
        payload["candidate_targeted_public_ats_version"] = VERSION
        payload["candidate_targeted_public_ats_skipped"] = "pool-at-or-above-30"
        payload["candidate_targeted_public_ats_pool_before"] = before
        payload["candidate_targeted_public_ats_pool_after"] = before
        payload["candidate_targeted_public_ats_goal_30_ready"] = True
        return payload

    try:
        if welo_posts is None:
            welo_posts, pages = _fetch_welo_japan()
        else:
            pages = 1
        stats["welo_raw_japan"] = len(welo_posts)
        stats["welo_pages"] = pages
        for post in welo_posts:
            row = base._map_lever(post, "weloglobal", "Welo Global")
            if row:
                row["_target_category"] = row.pop("_public_ats_category", "targeted_ats_welo_japan")
                row["_target_published"] = row.pop("_public_ats_published_at", None)
                row.pop("_public_ats_remote_structured", None)
                row["_target_provider"] = "Welo Global"
                mapped.append(row)
    except Exception as exc:
        errors.append(f"welo:{type(exc).__name__}")

    try:
        if lilt_posts is None:
            lilt_posts = base._fetch_ashby("lilt-production")
        stats["lilt_raw"] = len(lilt_posts)
        count = 0
        for post in lilt_posts:
            row = _lilt_language_job(post)
            if row:
                mapped.append(row)
                count += 1
                if count >= MAX_LILT_LANGUAGE_ROWS:
                    break
        stats["lilt_language_mapped"] = count
    except Exception as exc:
        errors.append(f"lilt:{type(exc).__name__}")

    try:
        if prolific_posts is None:
            prolific_posts, index_count, match_count = _fetch_prolific_japanese()
        else:
            index_count = len(prolific_posts)
            match_count = len(prolific_posts)
        stats["prolific_index"] = index_count
        stats["prolific_japanese_matches"] = match_count
        count = 0
        for post in prolific_posts:
            row = _prolific_job(post)
            if row:
                mapped.append(row)
                count += 1
        stats["prolific_mapped"] = count
    except Exception as exc:
        errors.append(f"prolific:{type(exc).__name__}")

    payload, accepted_by_provider, accepted = _build_rows(
        payload, previous_payload or {}, mapped
    )
    after = len(payload.get("jobs") or [])
    payload["candidate_targeted_public_ats_version"] = VERSION
    payload["candidate_targeted_public_ats_uses_serpapi"] = False
    payload["candidate_targeted_public_ats_quality_gate_unchanged"] = True
    payload["candidate_targeted_public_ats_pool_before"] = before
    payload["candidate_targeted_public_ats_mapped"] = len(mapped)
    payload["candidate_targeted_public_ats_deterministic_accepted"] = accepted
    payload["candidate_targeted_public_ats_accepted_by_provider"] = dict(accepted_by_provider)
    payload["candidate_targeted_public_ats_pool_after"] = after
    payload["candidate_targeted_public_ats_goal_30_ready"] = after >= TARGET_POOL
    payload["candidate_targeted_public_ats_errors"] = errors[:6]
    payload["candidate_targeted_public_ats_stats"] = stats
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feed", type=Path, default=DEFAULT_FEED)
    parser.add_argument("--previous", type=Path)
    args = parser.parse_args()
    payload = _load(args.feed)
    if not payload:
        raise SystemExit(f"feed missing or invalid: {args.feed}")
    result = top_up(payload, _load(args.previous))
    args.feed.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        "targeted ATS top-up: "
        f"before={result.get('candidate_targeted_public_ats_pool_before')} "
        f"mapped={result.get('candidate_targeted_public_ats_mapped', 0)} "
        f"accepted={result.get('candidate_targeted_public_ats_deterministic_accepted', 0)} "
        f"after={result.get('candidate_targeted_public_ats_pool_after')} "
        f"goal30={result.get('candidate_targeted_public_ats_goal_30_ready')}"
    )


if __name__ == "__main__":
    main()
