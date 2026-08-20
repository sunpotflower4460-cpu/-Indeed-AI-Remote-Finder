#!/usr/bin/env python3
"""Legacy scoring/Indeed-URL helper plus a minimal standalone refresh path.

The production refresh is orchestrated by `acquisition_supply_yield.py`; this
module remains the shared home for deterministic scoring helpers imported by
`acquisition.py` and for a small direct fallback refresh.

Both paths follow the same remote-evidence rule: search location/provider
classification is discovery context only. A listing earns remote confidence
from its own text. The deprecated Google Jobs Work From Home `ltype` filter is
not used.

Primary acquisition uses SerpApi's Google Jobs API. We only keep jobs whose
structured apply_options explicitly contain an Indeed application URL. This
avoids crawling/scraping Indeed pages while still making Indeed the final
application destination.

Required for live refresh:
    SERPAPI_KEY (GitHub Actions secret)

If the key is absent, the script exits successfully without replacing the
existing feed. This lets the app remain usable with the last known-good data.
"""
from __future__ import annotations

import html
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "jobs.json"
NOW = datetime.now(timezone.utc)
DEFAULT_SEARCH_ORIGIN = "Tokyo, Japan"


def configured_search_origin() -> str:
    return os.environ.get("SERPAPI_SEARCH_ORIGIN", "").strip() or DEFAULT_SEARCH_ORIGIN


# Minimal standalone fallback queries. Production uses the much broader rotating
# supply strategy in acquisition_supply.py.
QUERIES = [
    (
        "structured",
        '完全在宅 フルリモート (データ入力 OR 商品登録 OR データ整理 OR 転記 OR スプレッドシート OR 集計 OR タグ付け)',
    ),
    (
        "ai_language",
        '完全在宅 フルリモート (アノテーション OR AIトレーナー OR AI評価 OR 文字起こし OR 校正 OR 翻訳 OR リサーチ)',
    ),
]

REMOTE_STRONG = {
    "完全在宅": 74, "フルリモート": 74, "完全リモート": 74,
    "100%リモート": 74, "100％リモート": 74,
    "fully remote": 74, "100% remote": 74,
    "全国どこからでも": 68, "勤務地自由": 60,
}
# High-confidence rows require wording that explicitly means full remote.
# Ambiguous convenience wording such as 「勤務地自由」 can contribute to a
# review score, but can never by itself satisfy this gate.
REMOTE_EXPLICIT_FULL = (
    "完全在宅", "フルリモート", "完全リモート",
    "100%リモート", "100％リモート", "fully remote", "100% remote",
)
REMOTE_MEDIUM = {
    "在宅勤務": 28, "在宅ワーク": 28, "リモートワーク": 28,
    "在宅": 22, "remote": 22, "work from home": 28, "anywhere": 24,
}
REMOTE_NEG = {
    "一部在宅": -35, "週1出社": -55, "週2出社": -60, "週3出社": -65,
    "出社あり": -65, "出社": -55, "常駐": -75, "出勤": -45,
    "ハイブリッド": -40, "hybrid": -40, "対面": -55, "訪問": -65,
}
NEGATED_RISK_PHRASES = [
    "出社不要", "出社なし", "出社はありません", "出社一切なし", "出社の必要なし",
    "出社の必要はありません", "出社する必要なし", "出社する必要はありません",
    "通勤不要", "通勤なし", "出勤不要", "出勤なし", "出勤はありません",
    "常駐なし", "常駐不要", "常駐はありません",
    "電話なし", "電話対応なし", "電話対応不要", "電話対応はありません",
    "架電なし", "架電不要", "テレアポなし", "テレアポ不要",
    "対面なし", "対面不要", "対面対応なし", "対面対応不要", "対面対応はありません",
    "訪問なし", "訪問不要", "訪問はありません", "接客なし", "接客不要",
]

AUTO_STRONG = {
    "アノテーション": 34, "annotation": 34, "labeling": 32, "タグ付け": 30,
    "データ入力": 30, "data entry": 30, "転記": 30, "入力業務": 28,
    "文字起こし": 32, "transcription": 32,
    "aiトレーナー": 28, "ai trainer": 28, "ai評価": 30, "データ評価": 28,
    "rater": 28, "分類": 26, "要約": 28, "校正": 27, "proofreading": 27,
    "商品登録": 27, "データ整理": 27, "データ収集": 24, "データチェック": 27,
    "品質チェック": 24, "品質評価": 24, "リスト作成": 25, "定型": 22,
    "商品説明文": 24, "カテゴリー設定": 24, "在庫情報の更新": 24,
}
AUTO_MEDIUM = {
    "リサーチ": 18, "research": 18, "情報収集": 18, "ファクトチェック": 16,
    "翻訳": 18, "translation": 18, "ライティング": 15, "記事作成": 14,
    "メール": 12, "チャット": 10, "事務": 10, "excel": 14,
    "スプレッドシート": 14, "spreadsheet": 14, "集計": 16, "csv": 14,
    "shopify": 16, "ec運用": 12, "モデレーション": 18, "moderation": 18,
    "コンテンツレビュー": 16, "content review": 16, "qa": 12,
    "画像編集": 10, "画像加工": 10, "seo": 8,
}

HARD_RISK = {
    "テレアポ", "電話営業", "新規営業", "法人営業", "個人営業", "接客",
    "訪問", "出社", "常駐", "対面", "運転", "介護", "看護", "保育",
    "調理", "倉庫", "配送", "工事", "警備", "清掃", "店舗", "店頭",
    "現場作業", "施工", "ドライバー", "配達", "販売スタッフ", "梱包",
    "撮影業務", "商品撮影",
}
SOFT_RISK = {
    "電話対応": 18, "電話": 10, "顧客折衝": 22, "商談": 25, "営業": 22,
    "カスタマーサポート": 13, "カスタマーサクセス": 16,
    "オンライン面談": 8, "ミーティング": 8, "会議": 8,
    "講師": 18, "コンサル": 18, "マネジメント": 20, "採用面接": 24,
    "クリエイティブディレクション": 18, "撮影": 24, "指示出し": 12,
    "ディレクター": 16, "ディレクション": 16,
}

TAG_RULES = [
    ("完全リモート", list(REMOTE_EXPLICIT_FULL)),
    ("データ", ["データ入力", "data entry", "データ整理", "データ収集", "転記", "集計", "csv"]),
    ("AI評価", ["アノテーション", "annotation", "aiトレーナー", "ai trainer", "ai評価", "データ評価", "rater", "分類", "タグ付け", "labeling"]),
    ("文章", ["文字起こし", "transcription", "翻訳", "translation", "校正", "proofreading", "要約", "ライティング"]),
    ("リサーチ", ["リサーチ", "research", "情報収集", "ファクトチェック"]),
    ("事務", ["事務", "メール", "チャット", "excel", "スプレッドシート", "spreadsheet"]),
    ("EC", ["商品登録", "shopify", "ec運用", "商品説明文"]),
]


@dataclass
class Scores:
    remote: int
    automation: int
    freshness: int
    risk: int
    overall: int
    tier: str
    remote_reasons: list[str]
    automation_reasons: list[str]
    risk_reasons: list[str]


def clean(value: str | None) -> str:
    value = html.unescape(re.sub(r"<[^>]+>", " ", value or ""))
    return re.sub(r"\s+", " ", value).strip()


def clamp(value: float) -> int:
    return max(0, min(100, round(value)))


def risk_text(text: str) -> str:
    t = text.lower()
    for phrase in NEGATED_RISK_PHRASES:
        t = t.replace(phrase.lower(), " ")
    return t


def parse_relative_posted_at(value: str | None, now: datetime | None = None) -> datetime | None:
    """Convert common Google Jobs relative date strings to an approximate timestamp."""
    if not value:
        return None
    now = now or NOW
    s = clean(value).lower()

    if s in {"新着", "たった今", "just posted", "today"}:
        return now
    m = re.search(r"(\d+)\s*(?:分|minutes?)\s*前?", s)
    if m:
        return now - timedelta(minutes=int(m.group(1)))
    m = re.search(r"(\d+)\s*(?:時間|hours?|hrs?)\s*前?", s)
    if m:
        return now - timedelta(hours=int(m.group(1)))
    m = re.search(r"(\d+)\s*(?:日|days?)\s*(?:以上)?\s*前?", s)
    if m:
        days = int(m.group(1))
        if "以上" in s or "+" in s:
            days = max(days, 31)
        return now - timedelta(days=days)
    m = re.search(r"(\d+)\s*(?:週|weeks?)\s*前?", s)
    if m:
        return now - timedelta(weeks=int(m.group(1)))
    m = re.search(r"(\d+)\s*(?:か月|ヶ月|ヵ月|months?)\s*前?", s)
    if m:
        return now - timedelta(days=30 * int(m.group(1)))

    m = re.search(r"(\d+)\+?\s*days?\s*ago", s)
    if m:
        days = int(m.group(1))
        if "+" in s:
            days = max(days, 31)
        return now - timedelta(days=days)
    m = re.search(r"(\d+)\s*hours?\s*ago", s)
    if m:
        return now - timedelta(hours=int(m.group(1)))
    m = re.search(r"(\d+)\s*weeks?\s*ago", s)
    if m:
        return now - timedelta(weeks=int(m.group(1)))
    return None


def freshness_score(published: datetime | None, previous: dict | None) -> int:
    if published:
        age = max(0.0, (NOW - published).total_seconds() / 86400)
        if age <= 1:
            score = 98
        elif age <= 3:
            score = 92
        elif age <= 7:
            score = 84
        elif age <= 14:
            score = 70
        elif age <= 30:
            score = 52
        elif age <= 60:
            score = 34
        else:
            score = 18
    else:
        score = 40

    if previous:
        score += min(10, int(previous.get("seen_count") or 1) * 2)
        try:
            last_seen = previous.get("last_seen")
            last = datetime.fromisoformat(last_seen.replace("Z", "+00:00")) if last_seen else None
            if last and NOW - last <= timedelta(days=3):
                score += 5
        except Exception:
            pass
    return clamp(score)


def score_job(
    text: str,
    published: datetime | None,
    previous: dict | None,
    *,
    remote_api_filter: bool = False,
) -> Scores:
    t = text.lower()
    rt = risk_text(text)

    remote = 10
    remote_reasons: list[str] = []
    if remote_api_filter:
        remote += 58
        remote_reasons.append("Google Jobs:在宅勤務フィルタ")
    for key, points in REMOTE_STRONG.items():
        if key.lower() in t:
            remote += points
            remote_reasons.append(key)
    for key, points in REMOTE_MEDIUM.items():
        if key.lower() in t:
            remote += points
            remote_reasons.append(key)
    for key, points in REMOTE_NEG.items():
        if key.lower() in rt:
            remote += points
            remote_reasons.append(f"注意:{key}")
    if not remote_reasons:
        remote -= 25
    remote = clamp(remote)

    automation = 12
    automation_reasons: list[str] = []
    strong_hits = 0
    for key, points in AUTO_STRONG.items():
        if key.lower() in t:
            automation += points
            strong_hits += 1
            automation_reasons.append(key)
    for key, points in AUTO_MEDIUM.items():
        if key.lower() in t:
            automation += points
            automation_reasons.append(key)
    if strong_hits >= 2:
        automation += 12
    elif strong_hits == 0:
        automation -= 18
    automation = clamp(automation)

    risk_reasons = [key for key in HARD_RISK if key.lower() in rt]
    soft_hits = [(key, penalty) for key, penalty in SOFT_RISK.items() if key.lower() in rt]
    risk = clamp(sum(p for _, p in soft_hits) + (70 if risk_reasons else 0))
    risk_reasons.extend([key for key, _ in soft_hits])

    fresh = freshness_score(published, previous)
    overall = clamp(0.40 * automation + 0.32 * remote + 0.18 * fresh + 10 - 0.42 * risk)
    hard = any(key.lower() in rt for key in HARD_RISK)
    if hard:
        overall = min(overall, 54)

    explicit_full_remote = any(key.lower() in t for key in REMOTE_EXPLICIT_FULL)
    high_fresh = published is not None and NOW - published <= timedelta(days=14)
    review_fresh = published is None or NOW - published <= timedelta(days=30)

    if (
        automation >= 82
        and remote >= 82
        and high_fresh
        and risk <= 8
        and not hard
        and strong_hits >= 2
        and explicit_full_remote
    ):
        tier = "high"
    elif automation >= 64 and remote >= 62 and risk <= 35 and not hard and review_fresh:
        tier = "review"
    else:
        tier = "hidden"

    return Scores(
        remote=remote,
        automation=automation,
        freshness=fresh,
        risk=risk,
        overall=overall,
        tier=tier,
        remote_reasons=remote_reasons[:6],
        automation_reasons=automation_reasons[:8],
        risk_reasons=risk_reasons[:6],
    )


def tags_for(text: str) -> list[str]:
    t = text.lower()
    tags = [label for label, keys in TAG_RULES if any(key.lower() in t for key in keys)]
    return tags[:5] or ["要確認"]


def previous_jobs() -> dict[str, dict]:
    try:
        data = json.loads(OUT.read_text(encoding="utf-8"))
        rows = data.get("jobs", []) if isinstance(data, dict) else []
        return {
            str(row["id"]): row
            for row in rows
            if isinstance(row, dict) and row.get("id")
        }
    except Exception:
        return {}


def canonical_indeed_url(link: str) -> tuple[str, str] | None:
    """Return (canonical_url, job_id) only for explicit Indeed application URLs."""
    try:
        parsed = urllib.parse.urlparse(link)
        host = parsed.netloc.lower().split(":")[0]
        if not (host == "indeed.com" or host.endswith(".indeed.com")):
            return None
        params = urllib.parse.parse_qs(parsed.query)
        if "/viewjob" not in parsed.path.lower():
            return None
        job_id = str((params.get("jk") or [""])[0]).strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{6,128}", job_id):
            return None
        encoded = urllib.parse.quote(job_id, safe="")
        return f"https://jp.indeed.com/viewjob?jk={encoded}", job_id
    except Exception:
        return None


def find_indeed_apply(job: dict) -> tuple[str, str] | None:
    if not isinstance(job, dict):
        return None
    options = job.get("apply_options") or []
    if not isinstance(options, list):
        return None
    for option in options:
        if not isinstance(option, dict):
            continue
        title = clean(str(option.get("title") or ""))
        link = clean(str(option.get("link") or ""))
        if "indeed" not in title.lower() and "indeed." not in link.lower():
            continue
        found = canonical_indeed_url(link)
        if found:
            return found
    return None


def flatten_highlights(job: dict) -> str:
    if not isinstance(job, dict):
        return ""
    sections = job.get("job_highlights") or []
    if not isinstance(sections, list):
        return ""
    parts: list[str] = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        parts.append(clean(str(section.get("title") or "")))
        items = section.get("items") or []
        if not isinstance(items, list):
            continue
        for item in items:
            parts.append(clean(str(item)))
    return " ".join(p for p in parts if p)


def serpapi_fetch(query: str, api_key: str) -> dict:
    params = {
        "engine": "google_jobs",
        "q": query,
        "location": configured_search_origin(),
        "hl": "ja",
        "gl": "jp",
        "api_key": api_key,
        "output": "json",
    }
    url = "https://serpapi.com/search.json?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "AI-Remote-Finder/7.0", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("SerpApi response is not an object")
    return payload


def build_row(job: dict, category: str, previous: dict[str, dict]) -> dict | None:
    if not isinstance(job, dict):
        return None
    indeed = find_indeed_apply(job)
    if not indeed:
        return None
    url, jid = indeed

    title = clean(str(job.get("title") or ""))
    company = clean(str(job.get("company_name") or ""))
    location = clean(str(job.get("location") or ""))
    description = clean(str(job.get("description") or ""))
    highlights = flatten_highlights(job)
    raw_extensions = job.get("extensions") or []
    extensions = " ".join(clean(str(x)) for x in raw_extensions) if isinstance(raw_extensions, list) else ""
    via = clean(str(job.get("via") or ""))
    if not title:
        return None

    detected = job.get("detected_extensions") or {}
    if not isinstance(detected, dict):
        detected = {}
    posted_text = clean(str(detected.get("posted_at") or ""))
    published = parse_relative_posted_at(posted_text)
    old = previous.get(jid)

    text = " ".join([title, company, location, description, highlights, extensions])
    scores = score_job(text, published, old, remote_api_filter=False)
    if scores.tier == "hidden":
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
        "tier": scores.tier,
        "score": scores.overall,
        "automation_confidence": scores.automation,
        "remote_confidence": scores.remote,
        "freshness_confidence": scores.freshness,
        "human_dependency_risk": scores.risk,
        "automation_reasons": scores.automation_reasons,
        "remote_reasons": scores.remote_reasons,
        "risk_reasons": scores.risk_reasons,
        "tags": tags_for(text),
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

    previous = previous_jobs()
    found: dict[str, dict] = {}
    errors: list[str] = []
    query_success = 0
    raw_jobs = 0
    indeed_apply_jobs = 0
    malformed_jobs = 0

    for category, query in QUERIES:
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

            for index, job in enumerate(jobs):
                if not isinstance(job, dict):
                    malformed_jobs += 1
                    print(f"WARN malformed job skipped [{category}#{index}]", file=sys.stderr)
                    continue
                try:
                    if find_indeed_apply(job):
                        indeed_apply_jobs += 1
                    row = build_row(job, category, previous)
                except Exception as exc:
                    malformed_jobs += 1
                    print(
                        f"WARN job skipped [{category}#{index}]: {type(exc).__name__}",
                        file=sys.stderr,
                    )
                    continue
                if not row:
                    continue
                current = found.get(row["id"])
                if not current or (row["tier"] == "high", row["score"]) > (
                    current["tier"] == "high", current["score"]
                ):
                    found[row["id"]] = row
        except Exception as exc:
            errors.append(f"{category}: {exc}")
            print(f"WARN query failed [{category}]: {exc}", file=sys.stderr)

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
    )[:80]

    payload = {
        "generated_at": NOW.isoformat(),
        "query_success": query_success,
        "query_total": len(QUERIES),
        "raw_jobs": raw_jobs,
        "indeed_apply_jobs": indeed_apply_jobs,
        "malformed_jobs": malformed_jobs,
        "errors": errors[:8],
        "method": "serpapi-google-jobs-indeed-apply-only",
        "provider_configured": True,
        "search_origin": configured_search_origin(),
        "jobs": jobs,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    high = sum(1 for row in jobs if row["tier"] == "high")
    review = sum(1 for row in jobs if row["tier"] == "review")
    print(
        f"wrote {len(jobs)} candidates ({high} high / {review} review); "
        f"queries {query_success}/{len(QUERIES)}, raw {raw_jobs}, "
        f"Indeed apply {indeed_apply_jobs}, malformed {malformed_jobs}"
    )


if __name__ == "__main__":
    main()
