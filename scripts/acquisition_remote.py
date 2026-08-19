#!/usr/bin/env python3
"""Production adapter for adaptive acquisition.

SerpApi's Google Jobs endpoint still accepts ltype=1 for Work From Home results,
but Google marks that filter deprecated and Work From Home can include hybrid
roles. Production therefore uses it only to widen acquisition/REVIEW scoring.
The deterministic HIGH tier still requires explicit full-remote wording in the
job text itself.

REVIEW intentionally keeps a broader next-best band: the listing must come from
the structured work-from-home acquisition path, contain at least one
AI-automatable work signal detected from the actual job text, stay within the
freshness window, and avoid high human/physical risk. If the returned job text
does not itself prove full remote, the row is marked `remote_search_only` and
the PWA tells the user to verify complete remote eligibility.

For pagination, prefer SerpApi's own `serpapi_pagination.next` URL. Google Jobs
pagination can change which filter parameters are accepted between page 1 and
page 2, especially around deprecated filters. Reusing SerpApi's generated next
URL preserves the server-selected pagination/filter state instead of rebuilding
it locally. The URL is host/path validated and the API key is replaced in memory
before the request; it is never written to the feed or logs.

Before paid/search-counted Google Jobs requests, production also queries
SerpApi's free Account API. The provider-reported hourly and monthly usage is
used as a hard upper bound, so repeated workflow triggers cannot burn through an
hourly allowance or make our local counter drift upward after failed searches.
If Account API is temporarily unavailable, the existing local monthly guard
remains in force and the feed continues to use the last known-good policy.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import timedelta

import acquisition

ACCOUNT_API_URL = "https://serpapi.com/account.json"
ACCOUNT_HOURLY_RESERVE = 2


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
        headers={"User-Agent": "AI-Remote-Finder/6.6", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("SerpApi account response is not an object")
    return payload


def production_review_fallback(scores, published) -> bool:
    fresh = published is None or acquisition.NOW - published <= timedelta(days=30)
    positive_remote = any(not str(x).startswith("注意:") for x in scores.remote_reasons)
    return bool(
        fresh
        and scores.automation >= 22
        and scores.remote >= 62
        and scores.risk <= 35
        and scores.automation_reasons
        and positive_remote
    )


def configure_production_policy() -> None:
    if getattr(acquisition, "_production_remote_policy_configured", False):
        return
    acquisition._production_remote_policy_configured = True
    acquisition.MAX_REQUESTS_PER_RUN = max(
        acquisition.MAX_REQUESTS_PER_RUN,
        len(acquisition.QUERY_PROFILES),
    )
    acquisition.review_fallback = production_review_fallback

    base_score_job = acquisition.legacy.score_job

    def score_with_remote_filter(text, published, previous, *, remote_api_filter=False):
        return base_score_job(text, published, previous, remote_api_filter=True)

    acquisition.legacy.score_job = score_with_remote_filter

    base_build_row = acquisition.build_row

    def build_row_with_remote_evidence(job, category, previous):
        row = base_build_row(job, category, previous)
        if not row or row.get("tier") != "review" or not isinstance(job, dict):
            return row

        title = acquisition.legacy.clean(str(job.get("title") or ""))
        location = acquisition.legacy.clean(str(job.get("location") or ""))
        description = acquisition.legacy.clean(str(job.get("description") or ""))
        highlights = acquisition.legacy.flatten_highlights(job)
        raw_extensions = job.get("extensions") or []
        extensions = (
            " ".join(acquisition.legacy.clean(str(x)) for x in raw_extensions)
            if isinstance(raw_extensions, list)
            else ""
        )
        text = " ".join([title, location, description, highlights, extensions]).lower()
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
        pairs = [(key, value) for key, value in pairs if key not in {"api_key", "output"}]
        pairs.extend([("api_key", api_key), ("output", "json")])
        safe_url = urllib.parse.urlunparse(
            (
                "https",
                host,
                parsed.path,
                "",
                urllib.parse.urlencode(pairs),
                "",
            )
        )
        request = urllib.request.Request(
            safe_url,
            headers={"User-Agent": "AI-Remote-Finder/6.6", "Accept": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError("SerpApi response is not an object")
        return payload

    def remember_next_url(payload: dict) -> None:
        pagination = payload.get("serpapi_pagination") or {}
        if not isinstance(pagination, dict):
            return
        token = str(pagination.get("next_page_token") or "").strip()
        next_url = str(pagination.get("next") or "").strip()
        if token and next_url:
            pagination_next_urls[token] = next_url

    def serpapi_fetch_work_from_home(
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
            "location": "Japan",
            "hl": "ja",
            "gl": "jp",
            "ltype": "1",
            "api_key": api_key,
            "output": "json",
        }
        if next_page_token:
            # Safe fallback if an older/partial response provided a token but no
            # generated next URL. The generated URL path above is preferred.
            params["next_page_token"] = next_page_token
        url = "https://serpapi.com/search.json?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "AI-Remote-Finder/6.6", "Accept": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError("SerpApi response is not an object")
        remember_next_url(payload)
        return payload

    acquisition.serpapi_fetch = serpapi_fetch_work_from_home


def configure_provider_budget(api_key: str) -> int | None:
    """Apply provider-reported usage as stricter runtime guards.

    Returns the provider-side request budget for this run, or None if Account API
    could not be read. No raw account payload is logged or persisted.
    """
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


def main() -> None:
    configure_production_policy()
    api_key = os.environ.get("SERPAPI_KEY", "").strip()
    provider_cap = configure_provider_budget(api_key)
    if provider_cap == 0:
        print("SerpApi provider usage guard has no safe request headroom; preserving last known-good feed.")
        return
    acquisition.main()


if __name__ == "__main__":
    main()
