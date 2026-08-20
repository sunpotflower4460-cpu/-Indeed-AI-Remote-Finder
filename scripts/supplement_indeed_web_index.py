#!/usr/bin/env python3
"""Promote trusted candidates to exact Indeed listings using the public web index.

This deliberately does NOT request or scrape Indeed pages. It spends at most one
bounded SerpApi Google Search request when monthly headroom permits, searches for
actual jp.indeed.com/viewjob URLs, and only promotes an already quality-screened
candidate when the indexed Indeed result strongly matches that structured row.

Unmatched hits are retained as short-lived seeds so the next Google Jobs run can
search the exact indexed title. This makes discovery substantially closer to the
Indeed search surface without pretending that a search fallback is an Indeed job.
"""
from __future__ import annotations

import difflib
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "jobs.json"
NOW = datetime.now(timezone.utc)
INDEX_VERSION = 1
SEED_TTL_DAYS = 14
MAX_SEEDS = 24
MATCH_THRESHOLD = 0.78
BASELINE_REQUESTS_PER_DAY = 2

SEARCH_PROFILES: tuple[tuple[str, str], ...] = (
    (
        "ai-evaluation",
        'site:jp.indeed.com/viewjob ("完全在宅" OR "フルリモート") '
        '("AI評価" OR "AIトレーナー" OR アノテーション OR rater OR evaluator)',
    ),
    (
        "data-ops",
        'site:jp.indeed.com/viewjob ("完全在宅" OR "フルリモート") '
        '("データ入力" OR "データチェック" OR "データ整理" OR OCR)',
    ),
    (
        "japanese-language-ai",
        'site:jp.indeed.com/viewjob ("完全在宅" OR "フルリモート") '
        '(日本語 OR Japanese) (AI OR rater OR evaluator OR trainer)',
    ),
    (
        "quality-review",
        'site:jp.indeed.com/viewjob ("完全在宅" OR "フルリモート") '
        '("品質評価" OR "品質チェック" OR QA OR reviewer)',
    ),
    (
        "research-content",
        'site:jp.indeed.com/viewjob ("完全在宅" OR "フルリモート") '
        '(リサーチ OR research OR 校正 OR proofreading OR "情報整理")',
    ),
    (
        "remote-digital",
        'site:jp.indeed.com/viewjob ("完全在宅" OR "フルリモート") '
        '(在宅ワーク OR リモートワーク) (データ OR AI OR コンテンツ)',
    ),
)

GENERIC_TITLE_TERMS = {
    "indeed", "job", "jobs", "remote", "japan", "japanese", "求人", "完全在宅",
    "フルリモート", "在宅", "募集", "採用", "スタッフ", "仕事", "業務", "the", "and",
}


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def write_payload(payload: dict) -> None:
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_iso(value: object) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def canonical_indeed_url(value: object) -> tuple[str, str] | None:
    try:
        parsed = urllib.parse.urlparse(str(value or ""))
    except Exception:
        return None
    host = (parsed.hostname or "").lower().strip(".")
    if parsed.scheme.lower() != "https" or not (host == "indeed.com" or host.endswith(".indeed.com")):
        return None
    if "/viewjob" not in parsed.path.lower():
        return None
    params = urllib.parse.parse_qs(parsed.query)
    jk = str((params.get("jk") or [""])[0]).strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{6,128}", jk):
        return None
    return f"https://jp.indeed.com/viewjob?jk={urllib.parse.quote(jk, safe='')}", jk


def clean_title(value: object) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = re.sub(r"\s*[-|–—]\s*(job post\s*[-|–—]\s*)?Indeed(?:\.com)?\s*$", "", text, flags=re.I)
    text = re.sub(r"\s*[-|–—]\s*(求人|採用情報)\s*$", "", text)
    return text.strip(" -|–—")


def normalized(value: object) -> str:
    text = clean_title(value).lower()
    text = re.sub(r"[^0-9a-zぁ-んァ-ヶ一-龯]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokens(value: object) -> set[str]:
    return {
        token for token in normalized(value).split()
        if len(token) >= 2 and token not in GENERIC_TITLE_TERMS
    }


def title_similarity(seed_title: str, row_title: str) -> float:
    a, b = normalized(seed_title), normalized(row_title)
    if not a or not b:
        return 0.0
    seq = difflib.SequenceMatcher(a=a, b=b).ratio()
    ta, tb = tokens(a), tokens(b)
    overlap = len(ta & tb) / max(1, len(ta | tb))
    containment = 1.0 if (a in b or b in a) and min(len(a), len(b)) >= 8 else 0.0
    return max(seq * 0.72 + overlap * 0.28, 0.90 * containment)


def match_score(seed: dict, row: dict) -> float:
    score = title_similarity(str(seed.get("title") or ""), str(row.get("title") or ""))
    company = normalized(row.get("company"))
    indexed_text = normalized(f"{seed.get('title', '')} {seed.get('snippet', '')}")
    if company and len(company) >= 3 and company in indexed_text:
        score = min(1.0, score + 0.12)
    return score


def serpapi_search(query: str, api_key: str) -> dict:
    params = {
        "engine": "google",
        "q": query,
        "location": "Tokyo, Japan",
        "hl": "ja",
        "gl": "jp",
        "num": 10,
        "filter": "0",
        "tbs": "qdr:m",
        "api_key": api_key,
        "output": "json",
    }
    url = "https://serpapi.com/search.json?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "AI-Remote-Finder/8.0", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("SerpApi response is not an object")
    if payload.get("error"):
        raise RuntimeError(str(payload.get("error")))
    return payload


def extract_seeds(payload: dict, profile: str) -> list[dict]:
    rows = payload.get("organic_results") or []
    if not isinstance(rows, list):
        return []
    found: dict[str, dict] = {}
    for item in rows:
        if not isinstance(item, dict):
            continue
        canonical = canonical_indeed_url(item.get("link"))
        if not canonical:
            continue
        url, jk = canonical
        title = clean_title(item.get("title"))
        if not title:
            continue
        found[jk] = {
            "jk": jk,
            "url": url,
            "title": title[:240],
            "snippet": re.sub(r"\s+", " ", str(item.get("snippet") or "")).strip()[:420],
            "profile": profile,
            "last_seen": NOW.isoformat(),
        }
    return list(found.values())


def merge_seeds(previous: list[dict], fresh: list[dict]) -> list[dict]:
    cutoff = NOW - timedelta(days=SEED_TTL_DAYS)
    merged: dict[str, dict] = {}
    for item in previous:
        if not isinstance(item, dict):
            continue
        canonical = canonical_indeed_url(item.get("url"))
        seen = parse_iso(item.get("last_seen"))
        if not canonical or not seen or seen < cutoff:
            continue
        _, jk = canonical
        copied = dict(item)
        copied["jk"] = jk
        merged[jk] = copied
    for item in fresh:
        jk = str(item.get("jk") or "")
        if not jk:
            continue
        old = merged.get(jk) or {}
        item = dict(item)
        item["first_seen"] = old.get("first_seen") or NOW.isoformat()
        merged[jk] = item
    values = sorted(
        merged.values(),
        key=lambda item: parse_iso(item.get("last_seen")) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return values[:MAX_SEEDS]


def promote_matches(payload: dict, seeds: list[dict]) -> int:
    promoted = 0
    used_jk: set[str] = set()
    jobs = payload.get("jobs") or []
    if not isinstance(jobs, list):
        return 0
    for row in jobs:
        if not isinstance(row, dict):
            continue
        if canonical_indeed_url(row.get("url")) and str(row.get("apply_source_kind") or "").lower() == "indeed":
            continue
        ranked = sorted(
            ((match_score(seed, row), seed) for seed in seeds if str(seed.get("jk") or "") not in used_jk),
            key=lambda pair: pair[0],
            reverse=True,
        )
        if not ranked or ranked[0][0] < MATCH_THRESHOLD:
            continue
        score, seed = ranked[0]
        canonical = canonical_indeed_url(seed.get("url"))
        if not canonical:
            continue
        url, jk = canonical
        row["original_apply_url"] = row.get("original_apply_url") or row.get("url")
        row["original_apply_source"] = row.get("original_apply_source") or row.get("apply_source")
        row["original_apply_source_kind"] = row.get("original_apply_source_kind") or row.get("apply_source_kind")
        row["url"] = url
        row["apply_source"] = "Indeed"
        row["apply_source_kind"] = "indeed"
        row["source"] = "Google web index exact Indeed URL matched to an already screened structured candidate"
        row["indeed_index_match_version"] = INDEX_VERSION
        row["indeed_index_match_score"] = round(score, 3)
        row["indeed_index_jk"] = jk
        row["indeed_index_verified_at"] = NOW.isoformat()
        used_jk.add(jk)
        promoted += 1
    return promoted


def monthly_headroom(payload: dict) -> tuple[int, int, int]:
    try:
        used = max(0, int(payload.get("serpapi_requests_month") or 0))
    except Exception:
        used = 0
    try:
        cap = max(1, int(payload.get("serpapi_monthly_request_cap") or 245))
    except Exception:
        cap = 245
    try:
        days = max(1, int(payload.get("serpapi_month_days_remaining") or 1))
    except Exception:
        days = 1
    return used, cap, days


def main() -> None:
    payload = load_json(OUT)
    if not payload:
        return
    previous_path = Path(sys.argv[2]) if len(sys.argv) >= 3 and sys.argv[1] == "--previous" else None
    previous = load_json(previous_path) if previous_path else {}
    old_seeds = previous.get("candidate_indeed_index_seeds") or payload.get("candidate_indeed_index_seeds") or []
    if not isinstance(old_seeds, list):
        old_seeds = []

    api_key = os.environ.get("SERPAPI_KEY", "").strip()
    used, cap, days_left = monthly_headroom(payload)
    remaining = max(0, cap - used)
    # Keep enough quota for the established structured Google Jobs path. The
    # index probe consumes only genuine monthly surplus and therefore never
    # steals the app's final safety budget.
    surplus = remaining - (BASELINE_REQUESTS_PER_DAY * max(0, days_left - 1))
    should_search = bool(api_key and remaining > 0 and surplus > 0)

    cursor = int(previous.get("candidate_indeed_index_cursor") or 0) % len(SEARCH_PROFILES)
    fresh: list[dict] = []
    error: str | None = None
    requests = 0
    profile, query = SEARCH_PROFILES[cursor]
    if should_search:
        try:
            result = serpapi_search(query, api_key)
            fresh = extract_seeds(result, profile)
            requests = 1
            used += 1
        except Exception as exc:
            error = type(exc).__name__

    seeds = merge_seeds(old_seeds, fresh)
    promoted = promote_matches(payload, seeds)
    payload["candidate_indeed_index_version"] = INDEX_VERSION
    payload["candidate_indeed_index_method"] = "google-web-site-index-to-exact-indeed-viewjob"
    payload["candidate_indeed_index_direct_indeed_requests"] = 0
    payload["candidate_indeed_index_query_profile"] = profile if requests else None
    payload["candidate_indeed_index_hits_run"] = len(fresh)
    payload["candidate_indeed_index_seed_count"] = len(seeds)
    payload["candidate_indeed_index_promoted_run"] = promoted
    payload["candidate_indeed_index_request_run"] = requests
    payload["candidate_indeed_index_error"] = error
    payload["candidate_indeed_index_cursor"] = (cursor + requests) % len(SEARCH_PROFILES)
    payload["candidate_indeed_index_seeds"] = seeds
    payload["candidate_indeed_index_truth_note"] = (
        "Exact Indeed viewjob URL discovered through the public Google index; candidate content remains from the screened structured source."
    )
    if requests:
        payload["serpapi_requests_month"] = used
        payload["serpapi_requests_run"] = int(payload.get("serpapi_requests_run") or 0) + requests
        payload["serpapi_monthly_requests_remaining_after_run"] = max(0, cap - used)
    write_payload(payload)
    print(
        f"Indeed index: requests={requests}, hits={len(fresh)}, seeds={len(seeds)}, "
        f"promoted={promoted}, month={used}/{cap}, surplus_before={surplus}"
    )


if __name__ == "__main__":
    main()
