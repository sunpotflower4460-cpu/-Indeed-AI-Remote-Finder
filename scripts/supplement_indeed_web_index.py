#!/usr/bin/env python3
"""Stable entrypoint for current Indeed public-index discovery.

The implementation lives in supplement_indeed_web_index_v2.py; that historical
filename remains to avoid breaking workflow imports. The current v4 contract
covers both directly indexed `/viewjob?jk=` URLs and Indeed search-page `vjk`
job keys, while never requesting Indeed backend pages without partner permission.

Safety contract:
- Google public index only (`engine=google` via SerpApi)
- candidate_indeed_index_direct_indeed_requests is always 0
- search-vjk evidence is discovery-only and cannot promote a candidate
- no backend request is made to jp.indeed.com
"""
from supplement_indeed_web_index_v2 import *  # noqa: F401,F403
from supplement_indeed_web_index_v2 import main


if __name__ == "__main__":
    main()
