#!/usr/bin/env python3
"""Adaptive SerpApi acquisition for a deep, rotating recommendation pool.

This module deliberately reuses the deterministic scoring and Indeed URL
validation from fetch_jobs.py. The difference is acquisition strategy:

- many rotating search themes while the pool is shallow;
- a small steady-state request budget once the pool is healthy;
- no deprecated Google Jobs ltype filter;
- a conservative monthly request cap;
- review-tier fallback for plausible next-best digital/remote work, while the
  existing high tier remains unchanged and strict.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import fetch_jobs as legacy  # noqa: E402

ROOT = SCRIPT_DIR.parent
OUT = ROOT / "data" / "jobs.json"
NOW = datetime.now(timezone.utc)

DISPLAY_TARGET = 30
POOL_TARGET = 80
POOL_LIMIT = 100
ROLLING_DAYS = 14
STEADY_REQUESTS = 2
MAX_REQUESTS_PER_RUN = 10
# Keep headroom below a small account allowance. This is a safety rail rather
# than a promise about a specific SerpApi plan; it can be raised deliberately.
DEFAULT_MONTHLY_REQUEST_CAP = 220

REMOTE_QUERY = (
    '("完全在宅" OR "フルリモート" OR "完全リモート" OR "100%リモート" '
    'OR "100％リモート" OR "在宅ワーク" OR "リモートワーク" OR "fully remote")'
)

QUERY_PROFILES: list[tuple[str, str]] = [
    ("structured_data", f'{REMOTE_QUERY} ("データ入力" OR 転記 OR "データ整理" OR "入力業務")'),
    ("ai_annotation", f'{REMOTE_QUERY} (アノテーション OR annotation OR labeling OR "AIトレーナー" OR rater)'),
    ("language_ops", f'{REMOTE_QUERY} ("文字起こし" OR transcription OR 校正 OR proofreading OR 翻訳 OR translation)'),
    ("research", f'{REMOTE_QUERY} (リサーチ OR research OR "情報収集" OR "ファクトチェック")'),
    ("ecommerce", f'{REMOTE_QUERY} ("商品登録" OR "商品説明文" OR "在庫情報" OR Shopify OR "カテゴリー設定")'),
    ("content_qa", f'{REMOTE_QUERY} ("コンテンツレビュー" OR moderation OR モデレーション OR QA OR "品質チェック")'),
    ("spreadsheet", f'{REMOTE_QUERY} (スプレッドシート OR spreadsheet OR Excel OR CSV OR 集計 OR "リスト作成")'),
    ("search_eval", f'{REMOTE_QUERY} ("検索品質" OR "検索意図" OR "データ評価" OR "品質評価" OR "AI評価")'),
    ("catalog", f'{REMOTE_QUERY} (カタログ OR "マスタデータ" OR "データ更新" OR "データメンテナンス")'),
    ("image_data", f'{REMOTE_QUERY} ("画像分類" OR "画像タグ" OR "画像アノテーション" OR OCR OR "テキスト抽出")'),
    ("backoffice", f'{REMOTE_QUERY} ("書類作成" OR "フォーム入力" OR 事務 OR "メール対応" OR "データチェック")'),
    ("accounting_data", f'{REMOTE_QUERY} ("請求書入力" OR "経費入力" OR 領収書 OR "会計データ" OR "仕訳入力")'),
    ("data_cleanup", f'{REMOTE_QUERY} ("データクレンジング" OR "データ整形" OR "重複チェック" OR "データ検証")'),
    ("web_research", f'{REMOTE_QUERY} ("Webリサーチ" OR "市場調査" OR "企業リスト" OR "情報整理")'),
    ("localization_qa", f'{REMOTE_QUERY} (localization OR ローカライズ OR "言語QA" OR "日本語評価" OR "日本語チェック")'),
    ("testing", f'{REMOTE_QUERY} (テスト OR testing OR "動作確認" OR "検証作業" OR "品質保証")'),
    ("cms_ops", f'{REMOTE_QUERY} (CMS OR WordPress OR "記事登録" OR "コンテンツ入稿" OR "ページ更新")'),
    ("document_ops", f'{REMOTE_QUERY} ("文書分類" OR "文書チェック" OR "書類チェック" OR "PDF入力" OR "資料整理")'),
]


def load_payload(path: Path = OUT) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


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


def eligible_previous_count(payload: dict, now: datetime = NOW) -> int:
    count = 0
    for row in payload.get("jobs") or []:
        if not isinstance(row, dict) or row.get("tier") not in {"high", "review"}:
            continue
        last_seen = parse_iso(row.get("last_seen"))
        if not last_seen or now - last_seen > timedelta(days=ROLLING_DAYS):
            continue
        published = parse_iso(row.get("search_published_at"))
        if published and now - published > timedelta(days=30):
            continue
        count += 1
    return count


def month_key(now: datetime = NOW) -> str:
    return now.strftime("%Y-%m")


def previous_request_count(payload: dict, month: str) -> int:
    if str(payload.get("serpapi_budget_month") or "") == month:
        try:
            return max(0, int(payload.get("serpapi_requests_month") or 0))
        except Exception:
            return 0
    generated = parse_iso(payload.get("generated_at"))
    if generated and generated.strftime("%Y-%m") == month and payload.get("provider_configured") is True:
        try:
            return max(0, int(payload.get("query_total") or 0))
        except Exception:
            return 0
    return 0


def configured_monthly_cap() -> int:
    raw = os.environ.get("SERPAPI_MONTHLY_REQUEST_CAP", "").strip()
    if not raw:
        return DEFAULT_MONTHLY_REQUEST_CAP
    try:
        return max(1, min(5000, int(raw)))
    except Exception:
        return DEFAULT_MONTHLY_REQUEST_CAP


def request_limit_for_pool(pool_size: int) -> int:
    if pool_size < DISPLAY_TARGET:
        return MAX_REQUESTS_PER_RUN
    if pool_size < 50:
        return 6
    if pool_size < POOL_TARGET:
        return 4
    return STEADY_REQUESTS


def rotated_profiles(cursor: int) -> list[tuple[str, str]]:
    if not QUERY_PROFILES:
        return []
    cursor %= len(QUERY_PROFILES)
    return QUERY_PROFILES[cursor:] + QUERY_PROFILES[:cursor]


def serpapi_fetch(query: str, api_key: str) -> dict:
    params = {
        "engine": "google_jobs",
        "q": query,
        "location": "Japan",
        "hl": "ja",
        "gl": "jp",
        "api_key": api_key,
        "output": "json",
    }
    url = "https://serpapi.com/search.json?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "AI-Remote-Finder/6.0", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("SerpApi response is not an object")
    return payload


def review_fallback(scores: legacy.Scores, published: datetime | None) -> bool:
    fresh = published is None or NOW - published <= timedelta(days=30)
    positive_remote = any(not str(x).startswith("注意:") for x in scores.remote_reasons)
    return bool(
        fresh
        and scores.automation >= 45
        and scores.remote >= 50
        and scores.risk <= 45
        and scores.automation_reasons
        and positive_remote
    )


def build_row(job: dict, category: str, previous: dict[str, dict]) -> dict | None:
    if not isinstance(job, dict):
        return None
    indeed = legacy.find_indeed_apply(job)
    if not indeed:
        return None
    url, jid = indeed

    title = legacy.clean(str(job.get("title") or ""))
    company = legacy.clean(str(job.get("company_name") or ""))
    location = legacy.clean(str(job.get("location") or ""))
    description = legacy.clean(str(job.get("description") or ""))
    highlights = legacy.flatten_highlights(job)
    raw_extensions = job.get("extensions") or []
    extensions = " ".join(legacy.clean(str(x)) for x in raw_extensions) if isinstance(raw_extensions, list) else ""
    via = legacy.clean(str(job.get("via") or ""))
    if not title:
        return None

    detected = job.get("detected_extensions") or {}
    if not isinstance(detected, dict):
        detected = {}
    posted_text = legacy.clean(str(detected.get("posted_at") or ""))
    published = legacy.parse_relative_posted_at(posted_text, NOW)
    old = previous.get(jid)
    text = " ".join([title, company, location, description, highlights, extensions])
    scores = legacy.score_job(text, published, old, remote_api_filter=False)

    tier = scores.tier
    if tier == "hidden" and review_fallback(scores, published):
        tier = "review"
    if tier == "hidden":
        return None

    snippet = description or highlights
    if len(snippet) > 640:
        snippet = snippet[:637].rstrip() + "..."

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
        "tags": legacy.tags_for(text),
        "category": category,
        "posted_label": posted_text or None,
        "search_published_at": published.isoformat() if published else None,
        "first_seen": old.get("first_seen") if old else NOW.isoformat(),
        "last_seen": NOW.isoformat(),
        "seen_count": int(old.get("seen_count") or 0) + 1 if old else 1,
        "source": "Google Jobs via SerpApi; Indeed apply option verified",
        "via": via,
    }


def main() -> None:
    api_key = os.environ.get("SERPAPI_KEY", "").strip()
    if not api_key:
        print("SERPAPI_KEY is not configured; preserving the last known-good feed.")
        return

    previous_payload = load_payload()
    previous = {
        str(row.get("id")): row
        for row in previous_payload.get("jobs") or []
        if isinstance(row, dict) and row.get("id")
    }
    pool_size = eligible_previous_count(previous_payload)
    month = month_key()
    monthly_cap = configured_monthly_cap()
    requests_month = previous_request_count(previous_payload, month)
    remaining = max(0, monthly_cap - requests_month)
    if remaining <= 0:
        print("SerpApi monthly safety cap reached; preserving the last known-good feed.")
        return

    try:
        cursor = max(0, int(previous_payload.get("serpapi_rotation_cursor") or 0))
    except Exception:
        cursor = 0
    profiles = rotated_profiles(cursor)
    desired_requests = request_limit_for_pool(pool_size)
    request_limit = min(desired_requests, remaining, len(profiles))

    found: dict[str, dict] = {}
    errors: list[str] = []
    query_success = 0
    raw_jobs = 0
    indeed_apply_jobs = 0
    malformed_jobs = 0
    requests_run = 0

    for category, query in profiles[:request_limit]:
        requests_run += 1
        requests_month += 1
        try:
            payload = serpapi_fetch(query, api_key)
            if payload.get("error"):
                raise RuntimeError(str(payload["error"]))
            raw_result = payload.get("jobs_results")
            if raw_result is None:
                jobs: list[object] = []
            elif isinstance(raw_result, list):
                jobs = raw_result
            else:
                raise RuntimeError("jobs_results is not a list")
            query_success += 1
            raw_jobs += len(jobs)

            for job in jobs:
                if not isinstance(job, dict):
                    malformed_jobs += 1
                    continue
                try:
                    if legacy.find_indeed_apply(job):
                        indeed_apply_jobs += 1
                    row = build_row(job, category, previous)
                except Exception:
                    malformed_jobs += 1
                    continue
                if not row:
                    continue
                current = found.get(row["id"])
                if not current or (row["tier"] == "high", row["score"]) > (
                    current["tier"] == "high", current["score"]
                ):
                    found[row["id"]] = row
        except Exception as exc:
            errors.append(f"{category}: {type(exc).__name__}")
            print(f"WARN query failed [{category}]: {type(exc).__name__}", file=sys.stderr)

    if query_success == 0:
        print("ERROR: SerpApi unavailable; preserving previous feed", file=sys.stderr)
        raise SystemExit(2)

    jobs = sorted(
        found.values(),
        key=lambda row: (
            0 if row["tier"] == "high" else 1,
            -row["freshness_confidence"],
            -row["score"],
            -row["automation_confidence"],
        ),
    )[:POOL_LIMIT]

    payload = {
        "generated_at": NOW.isoformat(),
        "query_success": query_success,
        "query_total": requests_run,
        "raw_jobs": raw_jobs,
        "indeed_apply_jobs": indeed_apply_jobs,
        "malformed_jobs": malformed_jobs,
        "errors": errors[:8],
        "method": "serpapi-google-jobs-adaptive-indeed-apply-only",
        "provider_configured": True,
        "candidate_display_target": DISPLAY_TARGET,
        "candidate_pool_target": POOL_TARGET,
        "candidate_pool_limit": POOL_LIMIT,
        "acquisition_mode": "replenish" if pool_size < POOL_TARGET else "steady",
        "pool_before_refresh": pool_size,
        "serpapi_budget_month": month,
        "serpapi_requests_run": requests_run,
        "serpapi_requests_month": requests_month,
        "serpapi_monthly_request_cap": monthly_cap,
        "serpapi_rotation_cursor": (cursor + requests_run) % len(QUERY_PROFILES),
        "jobs": jobs,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    high = sum(1 for row in jobs if row["tier"] == "high")
    review = sum(1 for row in jobs if row["tier"] == "review")
    print(
        f"wrote {len(jobs)} fresh candidates ({high} high / {review} review); "
        f"queries {query_success}/{requests_run}, raw {raw_jobs}, Indeed apply {indeed_apply_jobs}; "
        f"rolling pool before refresh {pool_size}, SerpApi month {requests_month}/{monthly_cap}"
    )


if __name__ == "__main__":
    main()
