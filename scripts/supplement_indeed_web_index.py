#!/usr/bin/env python3
"""Stable entrypoint for current Indeed public-index discovery.

The current v5 implementation lives in supplement_indeed_web_index_v5.py. It
keeps the v4 truth model, adds high-yield broad profiles, scans nested public
search-result links/sitelinks for additional concrete Indeed job keys, and paces
remaining SerpApi quota across the rest of the month.

Safety contract:
- Google public index only (`engine=google` via SerpApi)
- candidate_indeed_index_direct_indeed_requests is always 0
- search-vjk evidence is discovery-only and cannot promote a candidate
- no backend request is made to jp.indeed.com
"""
from supplement_indeed_web_index_v5 import *  # noqa: F401,F403
from supplement_indeed_web_index_v5 import main


if __name__ == "__main__":
    main()
