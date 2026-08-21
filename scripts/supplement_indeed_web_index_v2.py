#!/usr/bin/env python3
"""Near-direct Indeed discovery through the public Google index.

The backend never requests Indeed pages without partner permission. v4 searches
both directly indexed `/viewjob?jk=` pages and indexed Indeed search-result URLs
carrying `vjk=<job key>`. Search-vjk seeds are discovery-only and are never used
to promote a screened candidate because their organic page title is not a
reliable per-job title.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import indeed_index_core as legacy
from indeed_index_core import (  # re-export for compatibility/tests
    BASELINE_REQUESTS_PER_DAY,
    MATCH_THRESHOLD,
    canonical_indeed_url,
    clean_title,
    extract_seeds,
    indexed_indeed_reference,
    load_json,
    match_score,
    merge_seeds,
    monthly_headroom,
    promote_matches,
    title_similarity,
    write_payload,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "jobs.json"
INDEX_VERSION = 4
MAX_REQUESTS_PER_RUN = 2
RESULTS_PER_QUERY = 20

# Put a direct-viewjob query beside a broad Indeed search-page/vjk query at the
# front of the rotation. On a version bump the cursor restarts here, so scarce
# monthly quota immediately samples both public index surfaces.
SEARCH_PROFILES: tuple[tuple[str, str], ...] = (
    ("ai-trainer", 'site:jp.indeed.com/viewjob 在宅 "AIトレーナー"'),
    ("search-vjk-ai-trainer", 'site:jp.indeed.com/q- inurl:vjk "AIトレーナー" 在宅'),
    ("annotation", 'site:jp.indeed.com/viewjob 在宅 アノテーション'),
    ("search-vjk-annotation", 'site:jp.indeed.com/q- inurl:vjk アノテーション 在宅'),
    ("senior-rater", 'site:jp.indeed.com/viewjob "Senior Rater"'),
    ("search-vjk-rater", 'site:jp.indeed.com/q- inurl:vjk rater remote'),
    ("data-labeling", 'site:jp.indeed.com/viewjob 在宅 "データラベリング"'),
    ("search-vjk-data-labeling", 'site:jp.indeed.com/q- inurl:vjk "データラベリング" 在宅'),
    ("translation", 'site:jp.indeed.com/viewjob 在宅 翻訳'),
    ("search-vjk-translation", 'site:jp.indeed.com/q- inurl:vjk 翻訳 在宅 AI'),
    ("remote-ai-general", 'site:jp.indeed.com/viewjob "完全在宅" AI'),
    ("search-vjk-remote-ai", 'site:jp.indeed.com/q- inurl:vjk AI 完全在宅'),
    ("dataannotation", 'site:jp.indeed.com/viewjob DataAnnotation "AIトレーナー"'),
    ("search-vjk-dataannotation", 'site:jp.indeed.com/q- inurl:vjk DataAnnotation "AIトレーナー"'),
    ("telus-rater", 'site:jp.indeed.com/viewjob "TELUS Digital" rater'),
    ("search-vjk-telus", 'site:jp.indeed.com/q- inurl:vjk TELUS rater'),
    ("ai-evaluation", 'site:jp.indeed.com/viewjob 在宅 "AI評価"'),
    ("quality-assurance-rater", 'site:jp.indeed.com/viewjob "Quality Assurance Rater"'),
    ("rater", 'site:jp.indeed.com/viewjob 在宅 rater'),
    ("evaluator", 'site:jp.indeed.com/viewjob 在宅 evaluator'),
    ("ai-data", 'site:jp.indeed.com/viewjob 在宅 "AIデータ"'),
    ("data-entry", 'site:jp.indeed.com/viewjob 在宅 "データ入力"'),
    ("proofreading", 'site:jp.indeed.com/viewjob 在宅 校正'),
    ("localization", 'site:jp.indeed.com/viewjob 在宅 ローカライズ'),
    ("bilingual-editor", 'site:jp.indeed.com/viewjob 在宅 "バイリンガル" 編集'),
    ("transcription", 'site:jp.indeed.com/viewjob 在宅 "文字起こし"'),
    ("research", 'site:jp.indeed.com/viewjob 在宅 リサーチ'),
    ("fact-check", 'site:jp.indeed.com/viewjob 在宅 "ファクトチェック"'),
    ("quality-review", 'site:jp.indeed.com/viewjob 在宅 "品質評価"'),
    ("search-evaluation", 'site:jp.indeed.com/viewjob 在宅 "検索評価"'),
    ("search-quality", 'site:jp.indeed.com/viewjob remote "search quality"'),
    ("ads-quality", 'site:jp.indeed.com/viewjob remote "ads quality"'),
    ("content-review", 'site:jp.indeed.com/viewjob 在宅 "コンテンツレビュー"'),
    ("prompt-evaluation", 'site:jp.indeed.com/viewjob 在宅 プロンプト 評価'),
    ("chatbot-training", 'site:jp.indeed.com/viewjob 在宅 チャットボット 学習'),
    ("generative-ai-review", 'site:jp.indeed.com/viewjob 在宅 "生成AI" 評価'),
    ("llm-evaluation", 'site:jp.indeed.com/viewjob remote LLM 評価'),
    ("qa-testing", 'site:jp.indeed.com/viewjob 在宅 QA テスト'),
    ("data-quality", 'site:jp.indeed.com/viewjob 在宅 "データ品質"'),
    ("full-remote-ai", 'site:jp.indeed.com/viewjob "フルリモート" AI'),
)

NO_RESULTS_MARKERS = (
    "hasn't returned any results",
    "has not returned any results",
    "no results",
    "did not return any results",
)


def normalize_provider_payload(payload: object) -> dict:
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
    raise RuntimeError("provider-search-error")


def serpapi_search(query: str, api_key: str) -> dict:
    params = {
        "engine": "google",
        "q": query,
        "google_domain": "google.co.jp",
        "hl": "ja",
        "gl": "jp",
        "num": RESULTS_PER_QUERY,
        "api_key": api_key,
        "output": "json",
    }
    url = "https://serpapi.com/search.json?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "AI-Remote-Finder/12.0", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return normalize_provider_payload(payload)


def request_budget(payload: dict) -> tuple[int, int, int, int]:
    used, cap, days_left = monthly_headroom(payload)
    remaining = max(0, cap - used)
    protected_future = BASELINE_REQUESTS_PER_DAY * max(0, days_left - 1)
    surplus = max(0, remaining - protected_future)
    budget = min(MAX_REQUESTS_PER_RUN, remaining, surplus)
    return budget, used, cap, surplus


def _previous_payload() -> dict:
    previous_path = (
        Path(sys.argv[2])
        if len(sys.argv) >= 3 and sys.argv[1] == "--previous"
        else None
    )
    return load_json(previous_path) if previous_path else {}


def _profile_map(previous: dict, payload: dict, key: str) -> dict[str, str]:
    source = previous.get(key) or payload.get(key) or {}
    if not isinstance(source, dict):
        return {}
    allowed = {name for name, _ in SEARCH_PROFILES}
    return {
        str(name): str(value)
        for name, value in source.items()
        if str(name) in allowed and str(value).strip()
    }


def _version(payload: dict) -> int:
    try:
        return int(payload.get("candidate_indeed_index_version") or 0)
    except Exception:
        return 0


def main() -> None:
    payload = load_json(OUT)
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

    # Reset only when moving from an older discovery contract so v4 immediately
    # probes both direct viewjob and search-vjk surfaces. Thereafter rotate.
    if max(_version(previous), _version(payload)) < INDEX_VERSION:
        cursor = 0
    else:
        try:
            cursor = int(
                previous.get("candidate_indeed_index_cursor")
                or payload.get("candidate_indeed_index_cursor")
                or 0
            ) % len(SEARCH_PROFILES)
        except Exception:
            cursor = 0

    attempt_history = _profile_map(
        previous, payload, "candidate_indeed_index_profile_last_attempt"
    )
    success_history = _profile_map(
        previous, payload, "candidate_indeed_index_profile_last_success"
    )

    fresh: list[dict] = []
    attempted = 0
    successful = 0
    no_result_searches = 0
    errors: list[str] = []
    profiles_run: list[str] = []
    now_iso = legacy.NOW.isoformat()

    for offset in range(budget):
        profile, query = SEARCH_PROFILES[(cursor + offset) % len(SEARCH_PROFILES)]
        profiles_run.append(profile)
        attempt_history[profile] = now_iso
        attempted += 1
        used += 1
        try:
            result = serpapi_search(query, api_key)
            successful += 1
            success_history[profile] = now_iso
            if result.get("_indeed_index_no_results"):
                no_result_searches += 1
            fresh.extend(extract_seeds(result, profile))
        except Exception as exc:
            errors.append(type(exc).__name__)

    fresh_by_jk: dict[str, dict] = {}
    for seed in fresh:
        if not isinstance(seed, dict):
            continue
        jk = str(seed.get("jk") or "").strip()
        if not jk:
            continue
        existing = fresh_by_jk.get(jk)
        # Prefer direct viewjob evidence if both surfaces found the same key.
        if existing and existing.get("indeed_index_link_kind") == "viewjob-jk":
            continue
        fresh_by_jk[jk] = seed
    fresh = list(fresh_by_jk.values())

    seeds = merge_seeds(old_seeds, fresh)
    promoted = promote_matches(payload, seeds)
    all_profiles = [name for name, _ in SEARCH_PROFILES]
    unseen = [name for name in all_profiles if name not in attempt_history]
    exact_seed_count = sum(
        1 for seed in seeds if seed.get("indeed_index_link_kind") == "viewjob-jk"
    )
    vjk_seed_count = sum(
        1 for seed in seeds if seed.get("indeed_index_link_kind") == "search-vjk"
    )
    fresh_exact = sum(
        1 for seed in fresh if seed.get("indeed_index_link_kind") == "viewjob-jk"
    )
    fresh_vjk = sum(
        1 for seed in fresh if seed.get("indeed_index_link_kind") == "search-vjk"
    )

    payload["candidate_indeed_index_version"] = INDEX_VERSION
    payload["candidate_indeed_index_method"] = (
        "google-public-index-viewjob-jk-plus-search-vjk-to-indeed-job-key"
    )
    payload["candidate_indeed_index_direct_indeed_requests"] = 0
    payload["candidate_indeed_index_results_per_query"] = RESULTS_PER_QUERY
    payload["candidate_indeed_index_query_profile"] = profiles_run[0] if profiles_run else None
    payload["candidate_indeed_index_query_profiles"] = profiles_run
    payload["candidate_indeed_index_profile_count"] = len(SEARCH_PROFILES)
    payload["candidate_indeed_index_profile_last_attempt"] = attempt_history
    payload["candidate_indeed_index_profile_last_success"] = success_history
    payload["candidate_indeed_index_profile_coverage_count"] = len(attempt_history)
    payload["candidate_indeed_index_profile_success_coverage_count"] = len(success_history)
    payload["candidate_indeed_index_unseen_profiles"] = unseen
    payload["candidate_indeed_index_hits_run"] = len(fresh)
    payload["candidate_indeed_index_exact_url_hits_run"] = fresh_exact
    payload["candidate_indeed_index_search_vjk_hits_run"] = fresh_vjk
    payload["candidate_indeed_index_seed_count"] = len(seeds)
    payload["candidate_indeed_index_exact_url_seed_count"] = exact_seed_count
    payload["candidate_indeed_index_search_vjk_seed_count"] = vjk_seed_count
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
    payload["candidate_indeed_page_body_directly_accessed"] = False
    payload["candidate_indeed_page_body_access_reason"] = (
        "Indeed backend pages are not automatically fetched without partner permission"
    )
    payload["candidate_indeed_index_truth_note"] = (
        "Public Google index evidence may be either an exact Indeed /viewjob?jk URL "
        "or an Indeed search URL containing vjk (a concrete viewed-job key). Search-vjk "
        "keys are shown only as discovery leads and cannot promote a screened candidate. "
        "The backend does not fetch Indeed job-page bodies."
    )
    payload["candidate_indeed_index_budget_surplus_before_run"] = surplus

    if attempted:
        payload["serpapi_requests_month"] = used
        payload["serpapi_requests_run"] = int(payload.get("serpapi_requests_run") or 0) + attempted
        payload["serpapi_monthly_requests_remaining_after_run"] = max(0, cap - used)

    write_payload(payload)
    print(
        "Indeed index v4: "
        f"attempted={attempted}, success={successful}, hits={len(fresh)} "
        f"(exact={fresh_exact}, vjk={fresh_vjk}), seeds={len(seeds)} "
        f"(exact={exact_seed_count}, vjk={vjk_seed_count}), promoted={promoted}, "
        f"coverage={len(attempt_history)}/{len(SEARCH_PROFILES)}, "
        f"month={used}/{cap}, surplus_before={surplus}"
    )


if __name__ == "__main__":
    main()
