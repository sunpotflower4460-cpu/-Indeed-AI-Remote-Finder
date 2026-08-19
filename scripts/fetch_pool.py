#!/usr/bin/env python3
"""Build a rolling Indeed candidate pool from SerpApi Google Jobs.

Goals:
- Keep enough viable remote/AI-automatable candidates for daily applications.
- Preserve the strict deterministic `high` tier from fetch_jobs.py.
- Keep reasonable next-best digital/remote roles as `review` instead of hiding them.
- When the existing pool is below target, temporarily search more categories/pages.
- Keep an application-level monthly SerpApi attempt guard.

This script never scrapes Indeed. It only keeps Google Jobs rows whose structured
apply_options contain a canonical Indeed /viewjob URL.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import fetch_jobs as base

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "jobs.json"
NOW = datetime.now(timezone.utc)
POOL_TARGET_MIN = 30
POOL_TARGET_MAX = 80
DEFAULT_MONTHLY_SEARCH_CAP = 225
NORMAL_SEARCHES_PER_RUN = 3
BOOTSTRAP_SEARCHES_PER_RUN = 24

# The bank is intentionally broader than the strict high-confidence gate. The
# scorer still decides quality, and hard human/physical risks remain excluded.
QUERY_BANK: list[tuple[str, str]] = [
    ("data_entry", '完全在宅 OR フルリモート データ入力 転記 データ整理'),
    ("annotation", '完全在宅 OR フルリモート アノテーション AI評価 AIトレーナー rater'),
    ("writing", '完全在宅 OR フルリモート 文字起こし 校正 要約 ライティング'),
    ("research", '完全在宅 OR フルリモート リサーチ 情報収集 ファクトチェック'),
    ("translation", '完全在宅 OR フルリモート 翻訳 proofreading translation'),
    ("ec", '完全在宅 OR フルリモート 商品登録 商品説明文 EC運用 Shopify'),
    ("office", '完全在宅 OR フルリモート 事務 Excel スプレッドシート 集計 CSV'),
    ("qa", '完全在宅 OR フルリモート QA 品質チェック データチェック コンテンツレビュー'),
    ("moderation", '完全在宅 OR フルリモート モデレーション moderation 分類 タグ付け'),
    ("ai_language", '完全在宅 OR フルリモート Japanese AI trainer language evaluator'),
    ("operations", '完全在宅 OR フルリモート オペレーション 定型業務 リスト作成 入力業務'),
    ("content", '完全在宅 OR フルリモート コンテンツ作成 記事作成 SEO 画像加工'),
]


def month_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m")


def load_previous() -> dict:
    try:
        value = json.loads(OUT.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def previous_job_map(payload: dict) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for row in payload.get("jobs") or []:
        if isinstance(row, dict) and row.get("id"):
            result[str(row["id"])] = row
    return result


def current_pool_size(payload: dict) -> int:
    count = 0
    for row in payload.get("jobs") or []:
        if not isinstance(row, dict) or row.get("tier") not in {"high", "review"}:
            continue
        published = base.parse_relative_posted_at(None)
        raw = row.get("search_published_at")
        if raw:
            try:
                published = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                if published.tzinfo is None:
                    published = published.replace(tzinfo=timezone.utc)
            except Exception:
                published = None
        if published and NOW - published > timedelta(days=30):
            continue
        count += 1
    return count


def serpapi_fetch(query: str, api_key: str, next_page_token: str | None = None) -> dict:
    params = {
        "engine": "google_jobs",
        "q": query,
        "location": "Japan",
        "hl": "ja",
        "gl": "jp",
        "api_key": api_key,
        "output": "json",
    }
    # ltype is intentionally not used: Google deprecated that filter. Full
    # remote is asserted from query wording and then independently scored.
    if next_page_token:
        params["next_page_token"] = next_page_token
    url = "https://serpapi.com/search.json?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "AI-Remote-Finder/6.0", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=35) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("SerpApi response is not an object")
    return payload


def published_from(job: dict) -> tuple[str, datetime | None]:
    detected = job.get("detected_extensions") or {}
    if not isinstance(detected, dict):
        detected = {}
    posted_text = base.clean(str(detected.get("posted_at") or ""))
    return posted_text, base.parse_relative_posted_at(posted_text)


def has_hard_risk(text: str) -> bool:
    rt = base.risk_text(text)
    return any(key.lower() in rt for key in base.HARD_RISK)


def build_pool_row(job: dict, category: str, previous: dict[str, dict]) -> dict | None:
    if not isinstance(job, dict):
        return None
    indeed = base.find_indeed_apply(job)
    if not indeed:
        return None
    url, jid = indeed

    title = base.clean(str(job.get("title") or ""))
    if not title:
        return None
    company = base.clean(str(job.get("company_name") or ""))
    location = base.clean(str(job.get("location") or ""))
    description = base.clean(str(job.get("description") or ""))
    highlights = base.flatten_highlights(job)
    raw_extensions = job.get("extensions") or []
    extensions = " ".join(base.clean(str(x)) for x in raw_extensions) if isinstance(raw_extensions, list) else ""
    via = base.clean(str(job.get("via") or ""))
    posted_text, published = published_from(job)
    old = previous.get(jid)

    text = " ".join([title, company, location, description, highlights, extensions])
    scores = base.score_job(text, published, old, remote_api_filter=False)
    tier = scores.tier

    # The strict high gate is untouched. For the visible reserve pool, accept
    # one step wider than the old review gate only when the role is still
    # digital, reasonably remote, reasonably automatable, and free of hard risk.
    review_fresh = published is None or NOW - published <= timedelta(days=30)
    explicit_or_strong_remote = any(key.lower() in text.lower() for key in base.REMOTE_EXPLICIT_FULL) or scores.remote >= 62
    if tier == "hidden" and (
        scores.automation >= 45
        and scores.remote >= 55
        and scores.risk <= 45
        and not has_hard_risk(text)
        and review_fresh
        and explicit_or_strong_remote
        and bool(scores.automation_reasons)
    ):
        tier = "review"
    if tier == "hidden":
        return None

    snippet = description or highlights
    if len(snippet) > 900:
        snippet = snippet[:897].rstrip() + "..."

    return {
        "id": jid,
        "title": title,
        "company": company,
        "location": location,
        "snippet": snippet,
        "url": url,
        "tier": tier,
        "score": scores.overall,
        "automation_confidence": scores.automation,
        "remote_confidence": scores.remote,
        "freshness_confidence": scores.freshness,
        "human_dependency_risk": scores.risk,
        "automation_reasons": scores.automation_reasons,
        "remote_reasons": scores.remote_reasons,
        "risk_reasons": scores.risk_reasons,
        "tags": base.tags_for(text),
        "category": category,
        "posted_label": posted_text or None,
        "search_published_at": published.isoformat() if published else None,
        "first_seen": old.get("first_seen") if old else NOW.isoformat(),
        "last_seen": NOW.isoformat(),
        "seen_count": int(old.get("seen_count") or 0) + 1 if old else 1,
        "source": "Google Jobs via SerpApi; Indeed apply option verified",
        "via": via,
    }


def ordered_query_bank() -> list[tuple[str, str]]:
    # Rotate three slots every 12h so normal mode covers all categories over
    # time instead of repeatedly returning the same search surface.
    slot = int(NOW.timestamp() // (12 * 3600))
    start = (slot * NORMAL_SEARCHES_PER_RUN) % len(QUERY_BANK)
    return QUERY_BANK[start:] + QUERY_BANK[:start]


def main() -> None:
    api_key = os.environ.get("SERPAPI_KEY", "").strip()
    if not api_key:
        print("SERPAPI_KEY is not configured; preserving the last known-good feed.")
        return

    previous_payload = load_previous()
    previous = previous_job_map(previous_payload)
    pool_before = current_pool_size(previous_payload)
    bootstrap = pool_before < POOL_TARGET_MIN

    cap = int(os.environ.get("SERPAPI_MONTHLY_SEARCH_CAP", DEFAULT_MONTHLY_SEARCH_CAP))
    cap = max(1, min(cap, 10000))
    month = month_key(NOW)
    attempts = int(previous_payload.get("serpapi_search_attempts_month") or 0) if previous_payload.get("serpapi_budget_month") == month else 0
    remaining = max(0, cap - attempts)
    per_run_cap = BOOTSTRAP_SEARCHES_PER_RUN if bootstrap else NORMAL_SEARCHES_PER_RUN
    run_budget = min(per_run_cap, remaining)

    found: dict[str, dict] = {}
    errors: list[str] = []
    raw_jobs = 0
    indeed_apply_jobs = 0
    malformed_jobs = 0
    successful_searches = 0
    pages = 0
    searched_categories: list[str] = []

    bank = ordered_query_bank()
    # In normal mode only three categories are queried. In bootstrap mode all
    # categories get a first page, then remaining budget is used for page 2+.
    initial = bank if bootstrap else bank[:NORMAL_SEARCHES_PER_RUN]
    pagination_queue: list[tuple[str, str, str]] = []

    def consume(category: str, query: str, token: str | None = None) -> None:
        nonlocal attempts, raw_jobs, indeed_apply_jobs, malformed_jobs, successful_searches, pages
        if attempts >= cap or attempts - (int(previous_payload.get("serpapi_search_attempts_month") or 0) if previous_payload.get("serpapi_budget_month") == month else 0) >= run_budget:
            return
        attempts += 1  # conservative: reserve an attempt before the network call
        try:
            payload = serpapi_fetch(query, api_key, token)
            if payload.get("error"):
                raise RuntimeError(str(payload["error"]))
            raw_result = payload.get("jobs_results")
            jobs = raw_result if isinstance(raw_result, list) else []
            if raw_result is not None and not isinstance(raw_result, list):
                raise RuntimeError("jobs_results is not a list")
            successful_searches += 1
            pages += 1
            if category not in searched_categories:
                searched_categories.append(category)
            raw_jobs += len(jobs)
            for index, job in enumerate(jobs):
                if not isinstance(job, dict):
                    malformed_jobs += 1
                    continue
                try:
                    if base.find_indeed_apply(job):
                        indeed_apply_jobs += 1
                    row = build_pool_row(job, category, previous)
                except Exception:
                    malformed_jobs += 1
                    continue
                if not row:
                    continue
                current = found.get(row["id"])
                if not current or (row["tier"] == "high", row["score"], row["freshness_confidence"]) > (
                    current["tier"] == "high", current["score"], current["freshness_confidence"]
                ):
                    found[row["id"]] = row
            next_token = str(((payload.get("serpapi_pagination") or {}).get("next_page_token") or "")).strip()
            if bootstrap and next_token:
                pagination_queue.append((category, query, next_token))
        except Exception as exc:
            errors.append(f"{category}: {type(exc).__name__}: {exc}")
            print(f"WARN SerpApi search failed [{category}]: {type(exc).__name__}", file=sys.stderr)

    for category, query in initial:
        if attempts >= cap or successful_searches + len(errors) >= run_budget:
            break
        consume(category, query)

    while bootstrap and pagination_queue and successful_searches + len(errors) < run_budget and attempts < cap:
        category, query, token = pagination_queue.pop(0)
        consume(category, query, token)

    if successful_searches == 0:
        print("ERROR: SerpApi unavailable or monthly guard exhausted; preserving previous feed", file=sys.stderr)
        raise SystemExit(2)

    rows = sorted(
        found.values(),
        key=lambda row: (
            0 if row["tier"] == "high" else 1,
            -row["freshness_confidence"],
            -row["score"],
            -row["automation_confidence"],
        ),
    )[:POOL_TARGET_MAX]

    payload = {
        "generated_at": NOW.isoformat(),
        "query_success": successful_searches,
        "query_total": successful_searches + len(errors),
        "raw_jobs": raw_jobs,
        "indeed_apply_jobs": indeed_apply_jobs,
        "malformed_jobs": malformed_jobs,
        "errors": errors[:8],
        "method": "serpapi-rotating-google-jobs-indeed-pool",
        "provider_configured": True,
        "jobs": rows,
        "pool_target_min": POOL_TARGET_MIN,
        "pool_target_max": POOL_TARGET_MAX,
        "pool_before_refresh": pool_before,
        "serpapi_bootstrap_mode": bootstrap,
        "serpapi_categories": searched_categories,
        "serpapi_pages_fetched": pages,
        "serpapi_budget_month": month,
        "serpapi_search_attempts_month": attempts,
        "serpapi_max_search_attempts_per_month": cap,
        "serpapi_monthly_budget_exhausted": attempts >= cap,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"wrote {len(rows)} live candidates; pool before={pool_before}; "
        f"bootstrap={bootstrap}; searches={successful_searches}/{payload['query_total']}; "
        f"raw={raw_jobs}; Indeed apply={indeed_apply_jobs}; monthly attempts={attempts}/{cap}"
    )


if __name__ == "__main__":
    main()
