#!/usr/bin/env python3
"""Production adapter for adaptive acquisition.

SerpApi's current Google Jobs API supports ltype=1 as the Working From Home
filter. Production uses that structured filter and treats it as remote evidence
for REVIEW-tier scoring only. The deterministic HIGH tier still requires the
job text itself to contain explicit full-remote wording, so this does not weaken
our strict top tier.

While the rolling pool is below 30, query every configured search theme in one
refresh to bootstrap a usable queue quickly. Once the pool recovers,
acquisition.py's smaller adaptive request counts take over.

REVIEW also intentionally keeps a broader next-best band: the listing must come
from the structured work-from-home acquisition path, contain at least one
AI-automatable work signal detected from the actual job text, stay within the
freshness window, and avoid high human/physical risk. These rows remain clearly
labeled 要確認; the strict HIGH thresholds are untouched.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import timedelta

import acquisition


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
    acquisition.MAX_REQUESTS_PER_RUN = len(acquisition.QUERY_PROFILES)
    acquisition.review_fallback = production_review_fallback

    base_score_job = acquisition.legacy.score_job

    def score_with_remote_filter(text, published, previous, *, remote_api_filter=False):
        return base_score_job(text, published, previous, remote_api_filter=True)

    acquisition.legacy.score_job = score_with_remote_filter

    def serpapi_fetch_work_from_home(query: str, api_key: str) -> dict:
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
        url = "https://serpapi.com/search.json?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "AI-Remote-Finder/6.2", "Accept": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError("SerpApi response is not an object")
        return payload

    acquisition.serpapi_fetch = serpapi_fetch_work_from_home


def main() -> None:
    configure_production_policy()
    acquisition.main()


if __name__ == "__main__":
    main()
