#!/usr/bin/env python3
"""Robust near-direct Indeed discovery through the public Google web index.

The production app must not claim an Indeed listing unless it has an exact
`https://jp.indeed.com/viewjob?jk=...` destination. This v2 layer searches the
public web index with short, human-like queries, never requests Indeed pages,
and reuses the existing strict title/company hardening before publication.

Why this exists:
- a Google/SerpApi no-result response must not abort the whole Indeed search;
- one overly narrow query must not make the UI show zero forever;
- request accounting must remain conservative even when a provider call fails;
- only exact viewjob URLs become Indeed seeds/candidates.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import supplement_indeed_web_index as legacy

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "jobs.json"
INDEX_VERSION = 2
MAX_REQUESTS_PER_RUN = 2

# Keep these intentionally simple. They are close to phrases a person would
# actually search and proved more robust than one large nested OR expression.
SEARCH_PROFILES: tuple[tuple[str, str], ...] = (
    ("ai-trainer", 'site:jp.indeed.com/viewjob "完全在宅" "AIトレーナー"'),
    ("rater", 'site:jp.indeed.com/viewjob "完全在宅" rater'),
    ("annotation", 'site:jp.indeed.com/viewjob "完全在宅" アノテーション'),
    ("data-entry", 'site:jp.indeed.com/viewjob "完全在宅" "データ入力"'),
    ("translation", 'site:jp.indeed.com/viewjob "完全在宅" 翻訳'),
    ("quality-review", 'site:jp.indeed.com/viewjob "フルリモート" "品質評価"'),
    ("search-evaluation", 'site:jp.indeed.com/viewjob "フルリモート" "検索評価"'),
    ("telus-rater", 'site:jp.indeed.com/viewjob "TELUS Digital" "完全在宅"'),
)

NO_RESULTS_MARKERS = (
    "hasn't returned any results",
    "has not returned any results",
    "no results",
    "did not return any results",
)


def normalize_provider_payload(payload: object) -> dict:
    """Treat a provider no-result response as a valid empty search, not failure."""
    if not isinstance(payload, dict):
        raise RuntimeError("provider-response-not-object")
    error = str(payload.get("error") or "").strip()
    if not error:
        return payload
    lowered = error.lower()
    if any(marker in lowered for marker in NO_RESULTS_MARKERS):
        return {
            "organic_results": [],
            "search_metadata": payload.get("search_metadata"),
            "_indeed_index_no_results": True,
        }
    # Keep public telemetry free of provider text/keys/plan details.
    raise RuntimeError("provider-search-error")


def serpapi_search(query: str, api_key: str) -> dict:
    """Run a minimal Google web query via SerpApi; never contact Indeed."""
    params = {
        "engine": "google",
        "q": query,
        "google_domain": "google.co.jp",
        "hl": "ja",
        "gl": "jp",
        "num": 10,
        "api_key": api_key,
        "output": "json",
    }
    url = "https://serpapi.com/search.json?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "AI-Remote-Finder/9.0", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return normalize_provider_payload(payload)


def request_budget(payload: dict) -> tuple[int, int, int, int]:
    """Spend only quota surplus after reserving the normal daily search floor."""
    used, cap, days_left = legacy.monthly_headroom(payload)
    remaining = max(0, cap - used)
    protected_future = legacy.BASELINE_REQUESTS_PER_DAY * max(0, days_left - 1)
    surplus = max(0, remaining - protected_future)
    budget = min(MAX_REQUESTS_PER_RUN, remaining, surplus)
    return budget, used, cap, surplus


def _previous_payload() -> dict:
    previous_path = (
        Path(sys.argv[2])
        if len(sys.argv) >= 3 and sys.argv[1] == "--previous"
        else None
    )
    return legacy.load_json(previous_path) if previous_path else {}


def main() -> None:
    payload = legacy.load_json(OUT)
    if not payload:
        return
    previous = _previous_payload()
    old_seeds = (
        previous.get("candidate_indeed_index_seeds")
        or payload.get("candidate_indeed_index_seeds")
        or []
    )
    if not isinstance(old_seeds, list):
        old_seeds = []

    api_key = os.environ.get("SERPAPI_KEY", "").strip()
    budget, used, cap, surplus = request_budget(payload)
    if not api_key:
        budget = 0

    try:
        cursor = int(
            previous.get("candidate_indeed_index_cursor")
            or payload.get("candidate_indeed_index_cursor")
            or 0
        ) % len(SEARCH_PROFILES)
    except Exception:
        cursor = 0

    fresh: list[dict] = []
    attempted = 0
    successful = 0
    no_result_searches = 0
    errors: list[str] = []
    profiles_run: list[str] = []

    for offset in range(budget):
        profile, query = SEARCH_PROFILES[(cursor + offset) % len(SEARCH_PROFILES)]
        profiles_run.append(profile)
        # Conservative accounting: a provider request may consume quota even if
        # the response is an error, so count it before parsing the result.
        attempted += 1
        used += 1
        try:
            result = serpapi_search(query, api_key)
            successful += 1
            if result.get("_indeed_index_no_results"):
                no_result_searches += 1
            fresh.extend(legacy.extract_seeds(result, profile))
        except Exception as exc:
            errors.append(type(exc).__name__)

    # Deduplicate fresh seeds by real Indeed job key before merging with history.
    fresh_by_jk: dict[str, dict] = {}
    for seed in fresh:
        if not isinstance(seed, dict):
            continue
        jk = str(seed.get("jk") or "").strip()
        if jk:
            fresh_by_jk[jk] = seed
    fresh = list(fresh_by_jk.values())

    seeds = legacy.merge_seeds(old_seeds, fresh)
    promoted = legacy.promote_matches(payload, seeds)

    payload["candidate_indeed_index_version"] = INDEX_VERSION
    payload["candidate_indeed_index_method"] = (
        "google-web-simple-rotating-site-index-to-exact-indeed-viewjob"
    )
    payload["candidate_indeed_index_direct_indeed_requests"] = 0
    payload["candidate_indeed_index_query_profile"] = profiles_run[0] if profiles_run else None
    payload["candidate_indeed_index_query_profiles"] = profiles_run
    payload["candidate_indeed_index_hits_run"] = len(fresh)
    payload["candidate_indeed_index_seed_count"] = len(seeds)
    payload["candidate_indeed_index_promoted_run"] = promoted
    payload["candidate_indeed_index_request_run"] = attempted
    payload["candidate_indeed_index_successful_searches"] = successful
    payload["candidate_indeed_index_no_result_searches"] = no_result_searches
    payload["candidate_indeed_index_error"] = errors[0] if errors else None
    payload["candidate_indeed_index_errors"] = errors[:4]
    payload["candidate_indeed_index_cursor"] = (
        (cursor + attempted) % len(SEARCH_PROFILES)
        if attempted
        else cursor
    )
    payload["candidate_indeed_index_seeds"] = seeds
    payload["candidate_indeed_index_truth_note"] = (
        "Exact Indeed viewjob URLs are discovered through the public Google index; "
        "no backend request is made to Indeed. Only screened structured candidates "
        "may be promoted, and later company-level hardening can revert ambiguity."
    )
    payload["candidate_indeed_index_budget_surplus_before_run"] = surplus

    if attempted:
        payload["serpapi_requests_month"] = used
        payload["serpapi_requests_run"] = int(payload.get("serpapi_requests_run") or 0) + attempted
        payload["serpapi_monthly_requests_remaining_after_run"] = max(0, cap - used)

    legacy.write_payload(payload)
    print(
        "Indeed index v2: "
        f"attempted={attempted}, success={successful}, no_results={no_result_searches}, "
        f"hits={len(fresh)}, seeds={len(seeds)}, promoted={promoted}, "
        f"month={used}/{cap}, surplus_before={surplus}"
    )


if __name__ == "__main__":
    main()
