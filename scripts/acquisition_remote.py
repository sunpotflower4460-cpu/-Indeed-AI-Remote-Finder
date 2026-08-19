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

    def serpapi_fetch_work_from_home(
        query: str,
        api_key: str,
        next_page_token: str | None = None,
    ) -> dict:
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
            params["next_page_token"] = next_page_token
        url = "https://serpapi.com/search.json?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "AI-Remote-Finder/6.4", "Accept": "application/json"},
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
