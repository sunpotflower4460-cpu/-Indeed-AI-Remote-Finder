#!/usr/bin/env python3
"""High-yield Indeed discovery v5.

This revision keeps the v4 truth model but improves yield per paid Google index
request. It scans nested result/sitelink objects for additional Indeed job keys,
puts broad high-yield query profiles first, and paces remaining monthly quota
across the days left in the month.

No backend request is made to Indeed itself.
"""
from __future__ import annotations

from typing import Iterator

import indeed_index_core as core
import supplement_indeed_web_index_v2 as legacy
from supplement_indeed_web_index_v2 import *  # noqa: F401,F403

INDEX_VERSION = 5
MAX_REQUESTS_PER_RUN = 2
RESULTS_PER_QUERY = legacy.RESULTS_PER_QUERY

BOOST_PROFILES: tuple[tuple[str, str], ...] = (
    (
        "broad-ai-remote",
        'site:jp.indeed.com/viewjob (在宅 OR remote) ("AIトレーナー" OR rater OR evaluator OR アノテーション OR "データラベリング" OR 翻訳)',
    ),
    (
        "search-vjk-broad-ai-remote",
        'site:jp.indeed.com/q- inurl:vjk (在宅 OR remote) ("AIトレーナー" OR rater OR evaluator OR アノテーション OR "データラベリング" OR 翻訳)',
    ),
)
SEARCH_PROFILES: tuple[tuple[str, str], ...] = BOOST_PROFILES + tuple(
    item for item in legacy.SEARCH_PROFILES if item[0] not in {name for name, _ in BOOST_PROFILES}
)


def _walk_dicts(value: object) -> Iterator[dict]:
    """Yield every dict so nested sitelinks can contribute concrete job keys."""
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def extract_seeds(payload: dict, profile: str) -> list[dict]:
    """Extract top-level and nested Indeed job references without weakening truth labels."""
    rows = payload.get("organic_results") or []
    if not isinstance(rows, list):
        return []

    found: dict[str, dict] = {}
    for top in rows:
        if not isinstance(top, dict):
            continue
        for node in _walk_dicts(top):
            link = node.get("link") or node.get("url")
            reference = core.indexed_indeed_reference(link)
            if not reference:
                continue
            url, jk, link_kind = reference
            is_top = node is top
            indexed_title = core.clean_title(node.get("title") or (top.get("title") if is_top else ""))
            if link_kind == "viewjob-jk":
                # A direct job URL remains promotion-eligible only when its own
                # indexed result/sitelink title is available.
                if not indexed_title:
                    continue
                title = indexed_title
            else:
                title = ""

            snippet = node.get("snippet") or (top.get("snippet") if is_top else "")
            candidate = core._stamp_seed_truth(
                {
                    "jk": jk,
                    "url": url,
                    "title": title[:240],
                    "indexed_page_title": indexed_title[:240],
                    "snippet": " ".join(str(snippet or "").split())[:420],
                    "profile": profile,
                    "last_seen": core.NOW.isoformat(),
                    "indeed_index_link_kind": link_kind,
                }
            )
            existing = found.get(jk)
            if existing:
                existing_direct = existing.get("indeed_index_link_kind") == "viewjob-jk"
                candidate_direct = link_kind == "viewjob-jk"
                if existing_direct and not candidate_direct:
                    continue
                if existing_direct == candidate_direct:
                    # Keep the richer same-strength evidence.
                    old_weight = len(str(existing.get("title") or "")) + len(str(existing.get("snippet") or ""))
                    new_weight = len(str(candidate.get("title") or "")) + len(str(candidate.get("snippet") or ""))
                    if old_weight >= new_weight:
                        continue
            found[jk] = candidate
    return list(found.values())


def request_budget(payload: dict) -> tuple[int, int, int, int]:
    """Pace remaining quota across remaining days instead of spending future daily headroom."""
    used, cap, days_left = core.monthly_headroom(payload)
    remaining = max(0, cap - used)
    daily_pace = remaining // max(1, days_left)
    budget = min(MAX_REQUESTS_PER_RUN, remaining, daily_pace)
    surplus = max(0, remaining - days_left)
    return budget, used, cap, surplus


def install() -> None:
    legacy.INDEX_VERSION = INDEX_VERSION
    legacy.MAX_REQUESTS_PER_RUN = MAX_REQUESTS_PER_RUN
    legacy.SEARCH_PROFILES = SEARCH_PROFILES
    legacy.extract_seeds = extract_seeds
    legacy.request_budget = request_budget


def main() -> None:
    install()
    legacy.main()
    payload = core.load_json(core.OUT)
    if not payload:
        return
    payload["candidate_indeed_index_version"] = INDEX_VERSION
    payload["candidate_indeed_index_yield_boost_version"] = 1
    payload["candidate_indeed_index_nested_result_links_scanned"] = True
    payload["candidate_indeed_index_high_yield_profile_count"] = len(BOOST_PROFILES)
    payload["candidate_indeed_index_quota_pacing"] = "remaining-quota-divided-by-days-left"
    core.write_payload(payload)


if __name__ == "__main__":
    main()
