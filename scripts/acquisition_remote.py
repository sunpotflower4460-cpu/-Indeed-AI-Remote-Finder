#!/usr/bin/env python3
"""Production adapter for adaptive acquisition.

The production policy has two independent requirements:

1. The work must be genuinely remote enough to be usable from home.
2. The work must be technically suitable for asynchronous AI substitution.

The second point is intentionally stricter than a generic "AI can help" score.
Jobs that inherently require calls, live customer interaction, meetings,
on-call human coverage, negotiation, continuous coordination, or similar
synchronous human attention are excluded even when some text/data subtasks are
automatable. Generic real-time processing or monitoring is not rejected by
word alone because unattended AI/RPA can perform it; human-attention context is
required for that kind of exclusion.

Discovery uses the same configurable Google Jobs search origin as the generic
acquisition layer (Tokyo, Japan by default). The deprecated Work From Home
`ltype` filter is not used and provider-side remote classification is not treated
as evidence. Remote confidence must come from the listing text itself. The
stricter v2 quality layer additionally requires explicit unconditional full-
remote wording before publication.

For pagination, prefer SerpApi's own `serpapi_pagination.next` URL. Any legacy
`ltype` parameter present in a server-generated URL is deliberately removed
while the server-generated `uds` / pagination state is retained. The URL is
host/path validated and the API key is replaced in memory before the request;
it is never written to feed/logs.

Before counted Google Jobs requests, production queries SerpApi's free Account
API. Provider-reported hourly/monthly usage becomes a hard upper bound so
repeated workflow triggers cannot burn through the allowance. Raw account data
is never logged or persisted.
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from datetime import timedelta

import acquisition

ACCOUNT_API_URL = "https://serpapi.com/account.json"
ACCOUNT_HOURLY_RESERVE = 2
USER_DISPLAY_TARGET = 100
SERVER_POOL_TARGET = 150
AUTONOMY_POLICY_VERSION = 2

# These phrases are inherently human/synchronous enough to exclude early.
# Ambiguous words such as "real-time monitoring" are deliberately NOT here:
# software can monitor or respond in real time without a person being present.
AUTONOMY_BLOCKERS = (
    "コールセンター",
    "電話受付",
    "電話対応",
    "受電",
    "架電",
    "テレアポ",
    "問い合わせ対応",
    "チャット対応",
    "チャットサポート",
    "カスタマーサポート",
    "カスタマーサクセス",
    "顧客対応",
    "オンコール",
    "顧客折衝",
    "商談",
    "採用面接",
    "面談対応",
    "会議参加",
    "ミーティング参加",
    "mtg参加",
    "定例会議",
    "定例mtg",
    "進行管理",
    "ディレクション",
    "マネジメント",
    "スケジュール調整",
    "指示出し",
)

# Contextual evidence that monitoring/rapid-response work is explicitly human,
# rather than an unattended automated process.
AUTONOMY_HUMAN_CONTEXT_BLOCKERS = (
    "有人監視",
    "有人対応",
    "監視オペレーター",
    "監視員",
    "人による監視",
    "スタッフによる監視",
    "担当者による監視",
    "オペレーターによる監視",
)

AUTONOMY_HUMAN_CONTEXT_PATTERNS = (
    re.compile(
        r"(?:顧客|ユーザー|問い合わせ|電話|チャット)[^。\n]{0,24}"
        r"(?:即時|リアルタイム)[^。\n]{0,16}(?:対応|返信|応答)",
        re.I,
    ),
    re.compile(
        r"(?:有人|人手|スタッフ|担当者|オペレーター)[^。\n]{0,16}"
        r"(?:常時|リアルタイム)?[^。\n]{0,12}(?:監視|対応)",
        re.I,
    ),
    re.compile(
        r"(?:常時|リアルタイム)?監視[^。\n]{0,30}"
        r"(?:スタッフ|担当者|オペレーター|人手)[^。\n]{0,20}"
        r"(?:対応|確認|連絡)",
        re.I,
    ),
)

AUTONOMY_NEGATIONS = (
    "電話対応なし",
    "電話対応不要",
    "電話対応はありません",
    "電話受付なし",
    "受電なし",
    "受電不要",
    "架電なし",
    "架電不要",
    "テレアポなし",
    "テレアポ不要",
    "問い合わせ対応なし",
    "問い合わせ対応不要",
    "チャット対応なし",
    "チャット対応不要",
    "顧客対応なし",
    "顧客対応不要",
    "会議参加なし",
    "会議参加不要",
    "ミーティング参加なし",
    "ミーティング参加不要",
    "mtg参加なし",
    "mtg参加不要",
    "有人監視なし",
    "有人監視不要",
    "有人対応なし",
    "有人対応不要",
    "オンコールなし",
    "オンコール不要",
)


class SerpApiNoResultsError(RuntimeError):
    pass


class SerpApiRateLimitError(RuntimeError):
    pass


class SerpApiPaginationError(RuntimeError):
    pass


class SerpApiInvalidRequestError(RuntimeError):
    pass


class SerpApiProviderError(RuntimeError):
    pass


def _nonnegative_int(value) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None


def provider_request_budget(account: dict, *, reserve: int = ACCOUNT_HOURLY_RESERVE) -> int | None:
    """Return safe provider-side request headroom, or None if unknown."""
    if not isinstance(account, dict):
        return None
    limits: list[int] = []

    hourly_limit = _nonnegative_int(account.get("account_rate_limit_per_hour"))
    hourly_used = _nonnegative_int(account.get("this_hour_searches"))
    if hourly_limit is not None and hourly_used is not None:
        limits.append(max(0, hourly_limit - hourly_used - max(0, reserve)))

    total_left = _nonnegative_int(account.get("total_searches_left"))
    if total_left is None:
        total_left = _nonnegative_int(account.get("plan_searches_left"))
    if total_left is not None:
        limits.append(total_left)

    return min(limits) if limits else None


def provider_month_usage(account: dict) -> int | None:
    if not isinstance(account, dict):
        return None
    return _nonnegative_int(account.get("this_month_usage"))


def fetch_serpapi_account(api_key: str) -> dict:
    params = urllib.parse.urlencode({"api_key": api_key})
    request = urllib.request.Request(
        f"{ACCOUNT_API_URL}?{params}",
        headers={"User-Agent": "AI-Remote-Finder/7.0", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("SerpApi account response is not an object")
    return payload


def raise_classified_provider_error(payload: dict) -> None:
    """Raise only a safe error class; never expose the provider's raw message."""
    message = str(payload.get("error") or "").strip()
    if not message:
        return
    lower = message.lower()
    if any(term in lower for term in ("no result", "no jobs", "hasn't returned", "has not returned", "empty result")):
        raise SerpApiNoResultsError("provider returned no further results")
    if any(term in lower for term in ("rate limit", "throughput", "too many request", "quota")):
        raise SerpApiRateLimitError("provider rate limit")
    if any(term in lower for term in ("next_page_token", "page token", "pagination")):
        raise SerpApiPaginationError("provider pagination error")
    if any(term in lower for term in ("invalid parameter", "incorrect parameter", "not supported", "unsupported", "missing parameter")):
        raise SerpApiInvalidRequestError("provider request rejected")
    raise SerpApiProviderError("provider error")


def job_text(job: dict) -> str:
    if not isinstance(job, dict):
        return ""
    raw_extensions = job.get("extensions") or []
    extensions = (
        " ".join(acquisition.legacy.clean(str(x)) for x in raw_extensions)
        if isinstance(raw_extensions, list)
        else ""
    )
    return " ".join(
        [
            acquisition.legacy.clean(str(job.get("title") or "")),
            acquisition.legacy.clean(str(job.get("location") or "")),
            acquisition.legacy.clean(str(job.get("description") or "")),
            acquisition.legacy.flatten_highlights(job),
            extensions,
        ]
    ).lower()


def autonomy_blockers(job: dict) -> list[str]:
    """Return human-attention blockers after stripping explicit negation."""
    text = job_text(job)
    for phrase in AUTONOMY_NEGATIONS:
        text = text.replace(phrase.lower(), " ")

    found = [phrase for phrase in AUTONOMY_BLOCKERS if phrase.lower() in text]
    found.extend(
        phrase for phrase in AUTONOMY_HUMAN_CONTEXT_BLOCKERS if phrase.lower() in text
    )
    for pattern in AUTONOMY_HUMAN_CONTEXT_PATTERNS:
        match = pattern.search(text)
        if match:
            found.append(match.group(0))
    return list(dict.fromkeys(found))[:8]


def production_review_fallback(scores, published) -> bool:
    fresh = published is None or acquisition.NOW - published <= timedelta(days=30)
    positive_remote = any(not str(x).startswith("注意:") for x in scores.remote_reasons)
    return bool(
        fresh
        and scores.automation >= 32
        and scores.remote >= 62
        and scores.risk <= 25
        and scores.automation_reasons
        and positive_remote
    )


def configure_production_policy() -> None:
    if getattr(acquisition, "_production_remote_policy_configured", False):
        return
    acquisition._production_remote_policy_configured = True

    # User-facing availability is 100 jobs, while the server maintains up to
    # 150 quality-gated rows so applications/declines do not immediately drain
    # the visible stock. The rotating supply layer keeps replenishing until the
    # larger server target is reached.
    acquisition.DISPLAY_TARGET = USER_DISPLAY_TARGET
    acquisition.POOL_TARGET = SERVER_POOL_TARGET
    acquisition.POOL_LIMIT = SERVER_POOL_TARGET
    acquisition.MAX_REQUESTS_PER_RUN = max(
        acquisition.MAX_REQUESTS_PER_RUN,
        len(acquisition.QUERY_PROFILES),
    )
    acquisition.review_fallback = production_review_fallback

    base_score_job = acquisition.legacy.score_job

    def score_without_provider_remote_assumption(text, published, previous, *, remote_api_filter=False):
        # Search/provider classification is discovery-only. Remote confidence
        # must be earned by listing text even when this adapter is run directly.
        return base_score_job(text, published, previous, remote_api_filter=False)

    acquisition.legacy.score_job = score_without_provider_remote_assumption
    base_build_row = acquisition.build_row

    def build_row_with_remote_evidence(job, category, previous):
        # A job that requires synchronous human attention is outside the product
        # definition even if its text/data subtask is technically automatable.
        if autonomy_blockers(job):
            return None

        row = base_build_row(job, category, previous)
        if not row or not isinstance(job, dict):
            return row

        row["autonomy_attention_risk"] = "low"
        row["autonomy_policy_version"] = AUTONOMY_POLICY_VERSION
        tags = list(row.get("tags") or [])
        if "張り付きリスク低" not in tags:
            tags.append("張り付きリスク低")
        row["tags"] = tags[:5]

        if row.get("tier") != "review":
            return row

        text = job_text(job)
        explicit_full_remote = any(
            phrase.lower() in text for phrase in acquisition.legacy.REMOTE_EXPLICIT_FULL
        )
        row["remote_search_only"] = not explicit_full_remote
        if row["remote_search_only"]:
            reasons = list(row.get("remote_reasons") or [])
            marker = "検索条件:在宅候補（完全在宅は本文要確認）"
            if marker not in reasons:
                reasons.append(marker)
            row["remote_reasons"] = reasons[:8]
            tags = list(row.get("tags") or [])
            if "在宅要確認" not in tags:
                tags.append("在宅要確認")
            row["tags"] = tags[:5]
        return row

    acquisition.build_row = build_row_with_remote_evidence
    pagination_next_urls: dict[str, str] = {}

    def read_serpapi_url(url: str, api_key: str) -> dict:
        parsed = urllib.parse.urlparse(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or host not in {"serpapi.com", "www.serpapi.com"}:
            raise RuntimeError("invalid SerpApi pagination URL host")
        if parsed.path not in {"/search", "/search.json"}:
            raise RuntimeError("invalid SerpApi pagination URL path")

        pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        pairs = [
            (key, value)
            for key, value in pairs
            if key not in {"api_key", "output", "ltype"}
        ]
        pairs.extend([("api_key", api_key), ("output", "json")])
        safe_url = urllib.parse.urlunparse(
            ("https", host, parsed.path, "", urllib.parse.urlencode(pairs), "")
        )
        request = urllib.request.Request(
            safe_url,
            headers={"User-Agent": "AI-Remote-Finder/7.0", "Accept": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError("SerpApi response is not an object")
        raise_classified_provider_error(payload)
        return payload

    def remember_next_url(payload: dict) -> None:
        pagination = payload.get("serpapi_pagination") or {}
        if not isinstance(pagination, dict):
            return
        token = str(pagination.get("next_page_token") or "").strip()
        next_url = str(pagination.get("next") or "").strip()
        if token and next_url:
            pagination_next_urls[token] = next_url

    def serpapi_fetch_remote_candidates(
        query: str,
        api_key: str,
        next_page_token: str | None = None,
    ) -> dict:
        if next_page_token:
            server_next = pagination_next_urls.pop(next_page_token, "")
            if server_next:
                payload = read_serpapi_url(server_next, api_key)
                remember_next_url(payload)
                return payload

        params = {
            "engine": "google_jobs",
            "q": query,
            "location": acquisition.configured_search_origin(),
            "hl": "ja",
            "gl": "jp",
            "api_key": api_key,
            "output": "json",
        }
        if next_page_token:
            params["next_page_token"] = next_page_token
        url = "https://serpapi.com/search.json?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "AI-Remote-Finder/7.0", "Accept": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError("SerpApi response is not an object")
        raise_classified_provider_error(payload)
        remember_next_url(payload)
        return payload

    acquisition.serpapi_fetch = serpapi_fetch_remote_candidates


def configure_provider_budget(api_key: str) -> int | None:
    """Apply provider-reported usage as stricter runtime guards."""
    if not api_key:
        return None
    try:
        account = fetch_serpapi_account(api_key)
    except Exception:
        print("SerpApi account guard unavailable; using local safety limits only.")
        return None

    provider_cap = provider_request_budget(account)
    exact_month_usage = provider_month_usage(account)

    if exact_month_usage is not None:
        base_previous_request_count = acquisition.previous_request_count
        current_month = acquisition.month_key()

        def provider_synced_request_count(payload: dict, month: str) -> int:
            if month == current_month:
                return exact_month_usage
            return base_previous_request_count(payload, month)

        acquisition.previous_request_count = provider_synced_request_count

    if provider_cap is not None:
        base_request_limit = acquisition.request_limit_for_pool

        def provider_guarded_request_limit(pool_size: int) -> int:
            return min(base_request_limit(pool_size), provider_cap)

        acquisition.request_limit_for_pool = provider_guarded_request_limit

    return provider_cap


def stamp_policy_metadata() -> None:
    try:
        payload = acquisition.load_payload()
        if not payload:
            return
        payload["candidate_server_pool_target"] = SERVER_POOL_TARGET
        payload["candidate_user_display_target"] = USER_DISPLAY_TARGET
        payload["candidate_quality_policy"] = "ai-substitutable-async-remote"
        payload["autonomy_policy_version"] = AUTONOMY_POLICY_VERSION
        acquisition.OUT.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


def main() -> None:
    configure_production_policy()
    api_key = os.environ.get("SERPAPI_KEY", "").strip()
    provider_cap = configure_provider_budget(api_key)
    if provider_cap == 0:
        print(
            "SerpApi provider usage guard has no safe request headroom; "
            "preserving last known-good feed."
        )
        return
    acquisition.main()
    stamp_policy_metadata()


if __name__ == "__main__":
    main()
