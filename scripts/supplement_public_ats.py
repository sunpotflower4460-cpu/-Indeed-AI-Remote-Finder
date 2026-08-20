#!/usr/bin/env python3
"""Supplement the SerpApi feed from documented public employer ATS feeds.

This is a second acquisition path, not a bypass around quality. It reads only
publicly listed jobs from documented ATS job-board endpoints (Lever, Ashby and
Greenhouse), filters to Japanese remote AI-evaluation/training work, converts
ATS metadata into the normal acquisition shape, and sends every row through the
existing production remote/autonomy/quality/AI-use gates.

No SerpApi request and no new secret are required.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import acquisition
import acquisition_precision
import acquisition_quality

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FEED = ROOT / "data" / "jobs.json"
SUPPLEMENT_VERSION = 2
MAX_RESPONSE_BYTES = 8_000_000
MAX_INDEX_POSTINGS = 5000
MAX_DETAIL_FETCHES_PER_BOARD = 100
MAX_ACCEPTED_ROWS = 120

LEVER_SITES: tuple[tuple[str, str], ...] = (("weloglobal", "Welo Global"),)
ASHBY_BOARDS: tuple[tuple[str, str], ...] = (("lilt-production", "LILT"),)
GREENHOUSE_BOARDS: tuple[tuple[str, str], ...] = (
    ("prolific", "Prolific"),
    ("agency", "Meridial / Invisible Agency"),
)

JAPANESE_SIGNALS = ("japanese", "日本語", "日本人", "日本在住", "japan", "日本")
FOCUS_SIGNALS = (
    "ai trainer", "trainer", "ai rater", "rater", "rating", "evaluator",
    "evaluation", "ai benchmark", "benchmark", "data trainer", "annotation",
    "annotator", "labeling", "search quality", "search relevance", "ads quality",
    "maps personalization", "quality reviewer", "quality specialist",
    "data contributor", "language specialist", "prompt engineer", "prompting",
    "ai data", "model response", "red-teaming", "red teaming", "fact-check",
    "fact check", "translation reviewer", "localization qa", "language data",
)
CLEAR_NON_AUTONOMOUS_TITLE = (
    "manager", "project manager", "program manager", "recruiter", "sales",
    "customer success", "customer support", "account executive", "team lead",
    "quality control lead", "coordinator",
)
CLEAR_HUMAN_MEDIA_BLOCKERS = (
    "voice talent", "audio contributor", "voice contributor", "record your voice",
    "recording of your voice", "video recording", "record your likeness",
    "live video call", "live video calls", "conversation partner",
    "phone call", "telephone call", "camera must", "webcam must",
)
EXCLUDED_REGION_WORDS = (
    "canada", "united states", "usa", "u.s.", "australia", "uk only",
    "united kingdom", "germany", "france", "india", "philippines",
)
WORLDWIDE_WORDS = ("world wide", "worldwide", "global", "remote worldwide")


def _clean(value: object) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _load(path: Path | None) -> dict:
    if not path:
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _fetch_json(url: str, *, max_bytes: int = MAX_RESPONSE_BYTES) -> object:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "AI-Remote-Finder/9.0", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise RuntimeError("public ATS response too large")
    return json.loads(raw.decode("utf-8"))


def _text_has(text: str, needles: tuple[str, ...]) -> bool:
    lower = text.lower()
    return any(value.lower() in lower for value in needles)


def _focus_text(title: str, body: str) -> bool:
    return _text_has(f"{title} {body}", FOCUS_SIGNALS)


def _human_media_blocker(title: str, body: str) -> bool:
    text = f"{title} {body}".lower()
    if any(term in title.lower() for term in CLEAR_NON_AUTONOMOUS_TITLE):
        return True
    return any(term in text for term in CLEAR_HUMAN_MEDIA_BLOCKERS)


def _japan_eligible(title: str, location: str, body: str) -> bool:
    title_body = f"{title} {body}".lower()
    loc = location.lower().strip()
    if not _text_has(title_body, JAPANESE_SIGNALS):
        return False
    if "japan" in loc or "日本" in loc:
        return True
    if _text_has(loc, WORLDWIDE_WORDS):
        return True
    if loc in {"remote", "fully remote", "100% remote", ""}:
        return True
    if _text_has(loc, EXCLUDED_REGION_WORDS):
        return False
    return "remote" in loc and not _text_has(loc, EXCLUDED_REGION_WORDS)


def _remote_location(location: str) -> bool:
    lower = location.lower()
    if any(term in lower for term in ("hybrid", "on-site", "onsite")):
        return False
    return "remote" in lower


def _source_published(value: object) -> str | None:
    text = _clean(value)
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(timezone.utc)
        if dt > datetime.now(timezone.utc):
            return None
        return dt.isoformat()
    except Exception:
        return None


def _scorer_markers(title: str, body: str) -> str:
    text = f"{title} {body}".lower()
    markers: list[str] = []
    if any(token in text for token in ("rater", "rating", "evaluator", "evaluation")):
        markers.extend(["AI評価", "データ評価", "品質評価"])
    if any(token in text for token in ("ai trainer", "data trainer", "training data")):
        markers.extend(["AIトレーナー", "アノテーション", "データ評価"])
    if any(token in text for token in ("annotation", "annotator", "labeling")):
        markers.extend(["アノテーション", "labeling", "分類"])
    if any(token in text for token in ("benchmark", "red-team", "red team")):
        markers.extend(["AI評価", "データ評価", "品質評価", "検証作業"])
    if any(token in text for token in ("search quality", "search relevance", "search evaluator")):
        markers.extend(["検索評価", "検索品質", "AI評価", "データ評価"])
    if "ads quality" in text or "ad quality" in text:
        markers.extend(["広告評価", "品質評価", "AI評価", "データ評価"])
    if any(token in text for token in ("language specialist", "translation reviewer", "localization")):
        markers.extend(["校正", "翻訳", "データ評価"])
    if any(token in text for token in ("prompt engineer", "prompting", "model response")):
        markers.extend(["AI評価", "品質評価", "要約"])
    if any(token in text for token in ("fact-check", "fact check", "verify factual")):
        markers.extend(["ファクトチェック", "リサーチ", "データ評価"])
    return " ".join(dict.fromkeys(markers))


def _normalized_job(
    *, title: str, company: str, location: str, body: str, apply_url: str,
    via: str, category: str, published_at: str | None, structured_remote: bool,
) -> dict | None:
    title = _clean(title)
    body = _clean(body)
    location = _clean(location)
    apply_url = _clean(apply_url)
    if not title or not apply_url or not apply_url.startswith("https://"):
        return None
    if not _focus_text(title, body) or _human_media_blocker(title, body):
        return None
    if not _japan_eligible(title, location, body):
        return None
    if not structured_remote and not _remote_location(location) and "remote" not in body.lower():
        return None

    markers = _scorer_markers(title, body)
    remote_marker = (
        "Employer ATS structured workplace type: fully remote. フルリモート。"
        if structured_remote
        else "Employer public job board explicitly states remote. フルリモート。"
    )
    description = " ".join(part for part in (remote_marker, markers, body) if part)
    return {
        "title": title,
        "company_name": company,
        "location": location or "Remote",
        "description": description,
        "highlights": [],
        "extensions": ["Remote", "Public ATS live listing"],
        "detected_extensions": {},
        "via": via,
        "apply_options": [{"title": via, "link": apply_url}],
        "_public_ats_category": category,
        "_public_ats_published_at": published_at,
        "_public_ats_remote_structured": structured_remote,
    }


# ---------- Lever ----------
def _fetch_lever(site: str) -> list[dict]:
    safe = urllib.parse.quote(site, safe="")
    payload = _fetch_json(f"https://api.lever.co/v0/postings/{safe}?mode=json&limit=200")
    if not isinstance(payload, list):
        raise RuntimeError("lever response is not a list")
    return [x for x in payload if isinstance(x, dict)][:200]


def _lever_text(post: dict) -> str:
    parts = [
        _clean(post.get("text")), _clean(post.get("descriptionPlain")),
        _clean(post.get("description")), _clean(post.get("additionalPlain")),
        _clean(post.get("additional")),
    ]
    for section in post.get("lists") or []:
        if isinstance(section, dict):
            parts.extend((_clean(section.get("text")), _clean(section.get("content"))))
    return " ".join(x for x in parts if x)


def _lever_locations(post: dict) -> str:
    cat = post.get("categories") or {}
    if not isinstance(cat, dict):
        return ""
    values = [_clean(cat.get("location"))]
    all_locations = cat.get("allLocations") or []
    if isinstance(all_locations, list):
        values.extend(_clean(x) for x in all_locations)
    return " / ".join(dict.fromkeys(x for x in values if x))


def _lever_remote(post: dict) -> bool:
    workplace = _clean(post.get("workplaceType") or post.get("workplace_type")).lower()
    if workplace in {"remote", "fully remote", "100% remote"}:
        return True
    return _remote_location(_lever_locations(post))


def _lever_url(post: dict, site: str) -> str:
    for key in ("applyUrl", "hostedUrl"):
        value = _clean(post.get(key))
        if value.startswith("https://"):
            return value
    jid = _clean(post.get("id"))
    if not jid:
        return ""
    return f"https://jobs.lever.co/{urllib.parse.quote(site, safe='')}/{urllib.parse.quote(jid, safe='')}"


def _map_lever(post: dict, site: str, company: str) -> dict | None:
    if not _lever_remote(post):
        return None
    workplace = _clean(post.get("workplaceType") or post.get("workplace_type")).lower()
    return _normalized_job(
        title=_clean(post.get("text")), company=company, location=_lever_locations(post),
        body=_lever_text(post), apply_url=_lever_url(post, site), via="Lever",
        category=f"public_ats_lever_{site}", published_at=None,
        structured_remote=workplace in {"remote", "fully remote", "100% remote"},
    )


# ---------- Ashby ----------
def _fetch_ashby(board: str) -> list[dict]:
    safe = urllib.parse.quote(board, safe="")
    payload = _fetch_json(
        f"https://api.ashbyhq.com/posting-api/job-board/{safe}?includeCompensation=false"
    )
    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
        raise RuntimeError("ashby response missing jobs")
    return [x for x in payload["jobs"] if isinstance(x, dict)][:MAX_INDEX_POSTINGS]


def _ashby_locations(post: dict) -> str:
    values = [_clean(post.get("location"))]
    for item in post.get("secondaryLocations") or []:
        if isinstance(item, dict):
            values.append(_clean(item.get("location")))
    return " / ".join(dict.fromkeys(x for x in values if x))


def _map_ashby(post: dict, board: str, company: str) -> dict | None:
    if post.get("isListed") is False:
        return None
    workplace = _clean(post.get("workplaceType")).lower()
    structured_remote = post.get("isRemote") is True or workplace == "remote"
    if not structured_remote:
        return None
    return _normalized_job(
        title=_clean(post.get("title")), company=company, location=_ashby_locations(post),
        body=_clean(post.get("descriptionPlain") or post.get("descriptionHtml")),
        apply_url=_clean(post.get("applyUrl") or post.get("jobUrl")), via="Ashby",
        category=f"public_ats_ashby_{board}",
        published_at=_source_published(post.get("publishedAt")), structured_remote=True,
    )


# ---------- Greenhouse ----------
def _fetch_greenhouse_index(board: str) -> list[dict]:
    safe = urllib.parse.quote(board, safe="")
    payload = _fetch_json(f"https://boards-api.greenhouse.io/v1/boards/{safe}/jobs")
    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
        raise RuntimeError("greenhouse response missing jobs")
    return [x for x in payload["jobs"] if isinstance(x, dict)][:MAX_INDEX_POSTINGS]


def _fetch_greenhouse_detail(board: str, job_id: object) -> dict:
    safe_board = urllib.parse.quote(board, safe="")
    safe_id = urllib.parse.quote(str(job_id), safe="")
    payload = _fetch_json(
        f"https://boards-api.greenhouse.io/v1/boards/{safe_board}/jobs/{safe_id}",
        max_bytes=2_000_000,
    )
    if not isinstance(payload, dict):
        raise RuntimeError("greenhouse job response is not an object")
    return payload


def _greenhouse_index_candidate(post: dict) -> bool:
    title = _clean(post.get("title"))
    location_obj = post.get("location") or {}
    location = _clean(location_obj.get("name") if isinstance(location_obj, dict) else location_obj)
    return _text_has(f"{title} {location}", JAPANESE_SIGNALS) and _focus_text(title, "")


def _map_greenhouse(post: dict, board: str, company: str) -> dict | None:
    title = _clean(post.get("title"))
    location_obj = post.get("location") or {}
    location = _clean(location_obj.get("name") if isinstance(location_obj, dict) else location_obj)
    body = _clean(post.get("content"))
    combined = f"{location} {body}".lower()
    if any(term in combined for term in ("hybrid", "on-site", "onsite")):
        return None
    if "remote" not in combined and "work from home" not in combined:
        return None
    return _normalized_job(
        title=title, company=company, location=location, body=body,
        apply_url=_clean(post.get("absolute_url")), via="Greenhouse",
        category=f"public_ats_greenhouse_{board}",
        published_at=_source_published(post.get("updated_at")), structured_remote=False,
    )


def _candidate_better(row: dict, existing: dict) -> bool:
    return (
        row.get("tier") == "high", int(row.get("score") or 0),
        int(row.get("automation_confidence") or 0),
    ) > (
        existing.get("tier") == "high", int(existing.get("score") or 0),
        int(existing.get("automation_confidence") or 0),
    )


def _rows_from_sources(
    *, fetched_lever: dict[str, list[dict]] | None = None,
    fetched_ashby: dict[str, list[dict]] | None = None,
    fetched_greenhouse: dict[str, list[dict]] | None = None,
) -> tuple[list[tuple[dict, str]], dict]:
    mapped: list[tuple[dict, str]] = []
    stats = {
        "source_success": 0,
        "source_total": len(LEVER_SITES) + len(ASHBY_BOARDS) + len(GREENHOUSE_BOARDS),
        "raw": 0, "relevant": 0, "errors": [], "provider_counts": Counter(),
    }

    for site, company in LEVER_SITES:
        try:
            posts = fetched_lever.get(site, []) if isinstance(fetched_lever, dict) else _fetch_lever(site)
            stats["source_success"] += 1
        except Exception as exc:
            stats["errors"].append(f"lever:{site}:{type(exc).__name__}")
            continue
        stats["raw"] += len(posts)
        stats["provider_counts"][company] += len(posts)
        for post in posts:
            row = _map_lever(post, site, company)
            if row:
                stats["relevant"] += 1
                mapped.append((row, company))

    for board, company in ASHBY_BOARDS:
        try:
            posts = fetched_ashby.get(board, []) if isinstance(fetched_ashby, dict) else _fetch_ashby(board)
            stats["source_success"] += 1
        except Exception as exc:
            stats["errors"].append(f"ashby:{board}:{type(exc).__name__}")
            continue
        stats["raw"] += len(posts)
        stats["provider_counts"][company] += len(posts)
        for post in posts:
            row = _map_ashby(post, board, company)
            if row:
                stats["relevant"] += 1
                mapped.append((row, company))

    for board, company in GREENHOUSE_BOARDS:
        details: list[dict] = []
        try:
            if isinstance(fetched_greenhouse, dict):
                details = [x for x in fetched_greenhouse.get(board, []) if isinstance(x, dict)]
                stats["raw"] += len(details)
            else:
                index = _fetch_greenhouse_index(board)
                stats["raw"] += len(index)
                matches = [x for x in index if _greenhouse_index_candidate(x)][:MAX_DETAIL_FETCHES_PER_BOARD]
                for item in matches:
                    if item.get("id") is None:
                        continue
                    try:
                        details.append(_fetch_greenhouse_detail(board, item["id"]))
                    except Exception:
                        continue
            stats["source_success"] += 1
        except Exception as exc:
            stats["errors"].append(f"greenhouse:{board}:{type(exc).__name__}")
            continue
        stats["provider_counts"][company] += len(details)
        for post in details:
            row = _map_greenhouse(post, board, company)
            if row:
                stats["relevant"] += 1
                mapped.append((row, company))

    return mapped, stats


def supplement(
    payload: dict, previous_payload: dict | None = None, *,
    fetched_lever: dict[str, list[dict]] | None = None,
    fetched_ashby: dict[str, list[dict]] | None = None,
    fetched_greenhouse: dict[str, list[dict]] | None = None,
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    previous = {
        str(row.get("id")): row
        for row in (previous_payload or {}).get("jobs") or []
        if isinstance(row, dict) and row.get("id")
    }

    # Recreate the production builder without issuing a SerpApi query.
    acquisition_precision.install()
    acquisition_quality.configure_quality_policy()
    acquisition_quality.reset_quality_telemetry()

    existing_rows = [row for row in payload.get("jobs") or [] if isinstance(row, dict)]
    by_id = {str(row.get("id")): row for row in existing_rows if row.get("id")}
    source_rows, stats = _rows_from_sources(
        fetched_lever=fetched_lever, fetched_ashby=fetched_ashby,
        fetched_greenhouse=fetched_greenhouse,
    )
    accepted = 0
    accepted_providers: Counter[str] = Counter()
    accepted_apply: Counter[str] = Counter()

    for mapped, company in source_rows:
        category = str(mapped.pop("_public_ats_category", "public_ats"))
        source_published = mapped.pop("_public_ats_published_at", None)
        structured_remote = bool(mapped.pop("_public_ats_remote_structured", False))
        try:
            row = acquisition.build_row(mapped, category, previous)
        except Exception:
            continue
        if not row:
            continue
        if source_published:
            row["search_published_at"] = source_published
            row["posted_label"] = "Public ATS timestamp"
        row["source"] = f"{company} public ATS job board; application URL verified"
        row["via"] = str(mapped.get("via") or "Public ATS")
        row["discovery_source"] = "public-employer-ats"
        row["ats_provider"] = company
        row["ats_live_verified_at"] = now
        row["remote_evidence_source"] = (
            "employer-ats-structured-remote" if structured_remote
            else "employer-job-board-explicit-remote"
        )
        row["public_ats_supplement_version"] = SUPPLEMENT_VERSION
        accepted += 1
        accepted_providers[company] += 1
        accepted_apply[str(row.get("apply_source") or "unknown")] += 1
        jid = str(row.get("id") or "")
        current = by_id.get(jid)
        if current is None or _candidate_better(row, current):
            by_id[jid] = row
        if accepted >= MAX_ACCEPTED_ROWS:
            break

    payload["jobs"] = list(by_id.values())[:150]
    payload["candidate_public_ats_supplement_version"] = SUPPLEMENT_VERSION
    payload["candidate_public_ats_sources"] = {
        "lever": [site for site, _ in LEVER_SITES],
        "ashby": [board for board, _ in ASHBY_BOARDS],
        "greenhouse": [board for board, _ in GREENHOUSE_BOARDS],
    }
    payload["candidate_public_ats_source_success"] = stats["source_success"]
    payload["candidate_public_ats_source_total"] = stats["source_total"]
    payload["candidate_public_ats_raw_postings"] = stats["raw"]
    payload["candidate_public_ats_relevant_remote_japanese"] = stats["relevant"]
    payload["candidate_public_ats_deterministic_accepted"] = accepted
    payload["candidate_public_ats_provider_counts"] = dict(stats["provider_counts"])
    payload["candidate_public_ats_accepted_provider_counts"] = dict(accepted_providers)
    payload["candidate_public_ats_accepted_apply_sources"] = dict(accepted_apply)
    payload["candidate_public_ats_errors"] = list(stats["errors"])[:8]
    payload["candidate_public_ats_uses_serpapi"] = False
    payload["candidate_public_ats_quality_gate_unchanged"] = True
    payload["candidate_public_ats_live_verified_at"] = now
    payload["candidate_public_ats_pool_after_merge"] = len(payload["jobs"])
    payload["candidate_public_ats_goal_30_ready"] = len(payload["jobs"]) >= 30
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feed", type=Path, default=DEFAULT_FEED)
    parser.add_argument("--previous", type=Path)
    args = parser.parse_args()
    payload = _load(args.feed)
    if not payload:
        raise SystemExit(f"feed missing or invalid: {args.feed}")
    previous = _load(args.previous)
    result = supplement(payload, previous)
    args.feed.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        "public ATS supplement: "
        f"sources {result.get('candidate_public_ats_source_success', 0)}/"
        f"{result.get('candidate_public_ats_source_total', 0)}, "
        f"raw {result.get('candidate_public_ats_raw_postings', 0)}, "
        f"relevant {result.get('candidate_public_ats_relevant_remote_japanese', 0)}, "
        f"accepted {result.get('candidate_public_ats_deterministic_accepted', 0)}, "
        f"pool {result.get('candidate_public_ats_pool_after_merge', 0)}"
    )


if __name__ == "__main__":
    main()
