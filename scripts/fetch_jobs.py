#!/usr/bin/env python3
"""Refresh AI-automatable remote-work candidates without scraping Indeed pages.

The collector reads public Bing RSS search results that point to Indeed. It never
requests an Indeed job page itself. Candidate snippets are scored conservatively;
the user must open Indeed to confirm the listing is still active and that AI use
is allowed by the employer/contract.
"""
from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
import html
import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "jobs.json"
NOW = datetime.now(timezone.utc)

QUERIES = [
    ("data", 'site:jp.indeed.com/viewjob ("完全在宅" OR "フルリモート") ("データ入力" OR 転記 OR "データ整理")'),
    ("annotation", 'site:jp.indeed.com/viewjob ("完全在宅" OR "フルリモート") (アノテーション OR labeling OR "AIトレーナー")'),
    ("ai_eval", 'site:jp.indeed.com/viewjob ("完全在宅" OR "フルリモート") ("AI評価" OR "データ評価" OR rater)'),
    ("transcription", 'site:jp.indeed.com/viewjob ("完全在宅" OR "フルリモート") (文字起こし OR transcription)'),
    ("proofreading", 'site:jp.indeed.com/viewjob ("完全在宅" OR "フルリモート") (校正 OR proofreading OR 要約)'),
    ("classification", 'site:jp.indeed.com/viewjob ("完全在宅" OR "フルリモート") (分類 OR タグ付け OR labeling)'),
    ("research", 'site:jp.indeed.com/viewjob ("完全在宅" OR "フルリモート") (リサーチ OR research OR "情報収集")'),
    ("translation", 'site:jp.indeed.com/viewjob ("完全在宅" OR "フルリモート") (翻訳 OR translation)'),
    ("ec", 'site:jp.indeed.com/viewjob ("完全在宅" OR "フルリモート") (商品登録 OR Shopify OR "EC運用")'),
    ("spreadsheet", 'site:jp.indeed.com/viewjob ("完全在宅" OR "フルリモート") (Excel OR スプレッドシート OR 集計)'),
    ("qa", 'site:jp.indeed.com/viewjob ("完全在宅" OR "フルリモート") ("品質チェック" OR "データチェック" OR QA)'),
    ("content", 'site:jp.indeed.com/viewjob ("完全在宅" OR "フルリモート") ("コンテンツレビュー" OR moderation OR モデレーション)'),
]

REMOTE_STRONG = {
    "完全在宅": 74, "フルリモート": 74, "完全リモート": 74,
    "100%リモート": 74, "fully remote": 74, "100% remote": 74,
    "全国どこからでも": 68, "勤務地自由": 60,
}
REMOTE_MEDIUM = {
    "在宅勤務": 28, "在宅ワーク": 28, "リモートワーク": 28,
    "在宅": 22, "remote": 22, "work from home": 28,
}
REMOTE_NEG = {
    "一部在宅": -35, "週1出社": -55, "週2出社": -60, "週3出社": -65,
    "出社あり": -65, "出社": -55, "常駐": -75, "出勤": -45,
    "ハイブリッド": -40, "hybrid": -40, "対面": -55, "訪問": -65,
}

NEGATED_RISK_PHRASES = [
    "出社不要", "出社なし", "出社はありません", "出社一切なし", "出社の必要なし",
    "通勤不要", "出勤不要", "常駐なし", "常駐不要",
    "電話なし", "電話対応なし", "電話対応不要", "架電なし", "テレアポなし",
    "対面なし", "対面不要", "訪問なし", "訪問不要", "接客なし", "接客不要",
]

AUTO_STRONG = {
    "アノテーション": 34, "annotation": 34, "labeling": 32, "タグ付け": 30,
    "データ入力": 30, "data entry": 30, "転記": 30, "入力業務": 28,
    "文字起こし": 32, "transcription": 32,
    "aiトレーナー": 28, "ai trainer": 28, "ai評価": 30, "データ評価": 28,
    "rater": 28, "分類": 26, "要約": 28, "校正": 27, "proofreading": 27,
    "商品登録": 27, "データ整理": 27, "データ収集": 24, "データチェック": 27,
    "品質チェック": 24, "品質評価": 24, "リスト作成": 25, "定型": 22,
}
AUTO_MEDIUM = {
    "リサーチ": 18, "research": 18, "情報収集": 18,
    "翻訳": 18, "translation": 18, "ライティング": 15, "記事作成": 14,
    "メール": 12, "チャット": 10, "事務": 10, "excel": 14,
    "スプレッドシート": 14, "spreadsheet": 14, "集計": 16, "csv": 14,
    "shopify": 16, "ec運用": 12, "モデレーション": 18, "moderation": 18,
    "コンテンツレビュー": 16, "content review": 16, "qa": 12,
}

HARD_RISK = {
    "テレアポ", "電話営業", "新規営業", "法人営業", "個人営業", "接客",
    "訪問", "出社", "常駐", "対面", "運転", "介護", "看護", "保育",
    "調理", "倉庫", "配送", "工事", "警備", "清掃", "店舗", "店頭",
    "現場作業", "施工", "ドライバー", "配達", "販売スタッフ",
}
SOFT_RISK = {
    "電話対応": 18, "電話": 10, "顧客折衝": 22, "商談": 25, "営業": 22,
    "カスタマーサポート": 13, "カスタマーサクセス": 16,
    "オンライン面談": 8, "ミーティング": 8, "会議": 8,
    "講師": 18, "コンサル": 18, "マネジメント": 20, "採用面接": 24,
    "クリエイティブディレクション": 18, "撮影": 24,
}

TAG_RULES = [
    ("完全リモート", list(REMOTE_STRONG)),
    ("データ", ["データ入力", "data entry", "データ整理", "データ収集", "転記", "集計", "csv"]),
    ("AI評価", ["アノテーション", "annotation", "aiトレーナー", "ai trainer", "ai評価", "データ評価", "rater", "分類", "タグ付け", "labeling"]),
    ("文章", ["文字起こし", "transcription", "翻訳", "translation", "校正", "proofreading", "要約", "ライティング"]),
    ("リサーチ", ["リサーチ", "research", "情報収集"]),
    ("事務", ["事務", "メール", "チャット", "excel", "スプレッドシート", "spreadsheet"]),
    ("EC", ["商品登録", "shopify", "ec運用"]),
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

def normalize_title(value: str) -> str:
    value = re.sub(r"\s*[-|｜]\s*Indeed.*$", "", value, flags=re.I)
    value = re.sub(r"\s*[-|｜]\s*インディード.*$", "", value, flags=re.I)
    return value.strip()

def direct_url(link: str) -> str:
    try:
        parsed = urllib.parse.urlparse(link)
        params = urllib.parse.parse_qs(parsed.query)
        for key in ("url", "u", "target"):
            if key in params:
                candidate = urllib.parse.unquote(params[key][0])
                host = urllib.parse.urlparse(candidate).netloc.lower()
                if host == "indeed.com" or host.endswith(".indeed.com"):
                    return candidate
    except Exception:
        pass
    return link

def is_indeed_job_url(link: str) -> bool:
    parsed = urllib.parse.urlparse(link)
    host = parsed.netloc.lower().split(":")[0]
    if not (host == "indeed.com" or host.endswith(".indeed.com")):
        return False
    return "/viewjob" in parsed.path.lower() and bool(re.search(r"(?:^|&)jk=", parsed.query, re.I))

def parse_rss_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None

def clamp(value: float) -> int:
    return max(0, min(100, round(value)))

def risk_text(text: str) -> str:
    t = text.lower()
    for phrase in NEGATED_RISK_PHRASES:
        t = t.replace(phrase.lower(), " ")
    return t

def freshness_score(published: datetime | None, previous: dict | None) -> int:
    if published:
        age = max(0.0, (NOW - published).total_seconds() / 86400)
        if age <= 1: score = 98
        elif age <= 3: score = 92
        elif age <= 7: score = 84
        elif age <= 14: score = 70
        elif age <= 30: score = 52
        elif age <= 60: score = 34
        else: score = 18
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

def score_job(text: str, published: datetime | None, previous: dict | None) -> Scores:
    t = text.lower()
    rt = risk_text(text)
    remote = 10
    remote_reasons: list[str] = []
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
    if automation >= 82 and remote >= 82 and fresh >= 55 and risk <= 8 and not hard and strong_hits >= 2:
        tier = "high"
    elif automation >= 64 and remote >= 62 and risk <= 35 and not hard and (published is None or fresh >= 45):
        tier = "review"
    else:
        tier = "hidden"
    return Scores(remote, automation, fresh, risk, overall, tier, remote_reasons[:6], automation_reasons[:8], risk_reasons[:6])

def tags_for(text: str) -> list[str]:
    t = text.lower()
    tags = [label for label, keys in TAG_RULES if any(key.lower() in t for key in keys)]
    return tags[:5] or ["要確認"]

def fetch(query: str) -> bytes:
    url = "https://www.bing.com/search?" + urllib.parse.urlencode({"q": query, "format": "rss", "setlang": "ja-JP", "count": "20"})
    request = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; AI-Remote-Finder/2.1; public-search-index-only)",
        "Accept": "application/rss+xml,application/xml,text/xml;q=0.9,*/*;q=0.8",
    })
    with urllib.request.urlopen(request, timeout=12) as response:
        return response.read()

def previous_jobs() -> dict[str, dict]:
    try:
        data = json.loads(OUT.read_text(encoding="utf-8"))
        return {row["id"]: row for row in data.get("jobs", []) if row.get("id")}
    except Exception:
        return {}

def item_id(link: str) -> str:
    match = re.search(r"[?&]jk=([A-Za-z0-9_-]+)", link)
    return match.group(1) if match else hashlib.sha1(link.encode()).hexdigest()[:18]

def main() -> None:
    previous = previous_jobs()
    found: dict[str, dict] = {}
    errors: list[str] = []
    query_success = 0
    def fetch_one(pair: tuple[str, str]):
        category, query = pair
        return category, ET.fromstring(fetch(query))
    results = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(fetch_one, pair): pair for pair in QUERIES}
        for future in as_completed(futures):
            category, _ = futures[future]
            try:
                results.append(future.result())
                query_success += 1
            except Exception as exc:
                errors.append(f"{category}: {exc}")
                print(f"WARN query failed [{category}]: {exc}", file=sys.stderr)
    for category, root in results:
        for item in root.findall(".//item"):
            title = normalize_title(clean(item.findtext("title")))
            snippet = clean(item.findtext("description"))
            link = direct_url(clean(item.findtext("link")))
            published = parse_rss_date(item.findtext("pubDate"))
            if not title or not is_indeed_job_url(link):
                continue
            jid = item_id(link)
            old = previous.get(jid)
            text = f"{title} {snippet}"
            scores = score_job(text, published, old)
            if scores.tier == "hidden":
                continue
            row = {
                "id": jid, "title": title, "snippet": snippet, "url": link,
                "tier": scores.tier, "score": scores.overall,
                "automation_confidence": scores.automation, "remote_confidence": scores.remote,
                "freshness_confidence": scores.freshness, "human_dependency_risk": scores.risk,
                "automation_reasons": scores.automation_reasons, "remote_reasons": scores.remote_reasons,
                "risk_reasons": scores.risk_reasons, "tags": tags_for(text), "category": category,
                "search_published_at": published.isoformat() if published else None,
                "first_seen": old.get("first_seen") if old else NOW.isoformat(),
                "last_seen": NOW.isoformat(), "seen_count": int(old.get("seen_count") or 0) + 1 if old else 1,
                "source": "Indeed result surfaced via public search index",
            }
            current = found.get(jid)
            if not current or (row["tier"] == "high", row["score"]) > (current["tier"] == "high", current["score"]):
                found[jid] = row
    if query_success == 0 or (query_success < 3 and not found):
        print("ERROR: search source degraded; keeping previous feed unchanged", file=sys.stderr)
        raise SystemExit(2)
    jobs = sorted(found.values(), key=lambda row: (0 if row["tier"] == "high" else 1, -row["freshness_confidence"], -row["score"], -row["automation_confidence"]))[:140]
    payload = {"generated_at": NOW.isoformat(), "query_success": query_success, "query_total": len(QUERIES), "errors": errors[:8], "method": "public-search-index-only", "jobs": jobs}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    high = sum(1 for row in jobs if row["tier"] == "high")
    review = sum(1 for row in jobs if row["tier"] == "review")
    print(f"wrote {len(jobs)} jobs ({high} high / {review} review); queries {query_success}/{len(QUERIES)}")

if __name__ == "__main__":
    main()
