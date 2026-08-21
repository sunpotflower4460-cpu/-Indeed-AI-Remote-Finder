#!/usr/bin/env python3
"""Compatibility entrypoint for resilient Indeed public-index discovery v2.

The implementation lives in supplement_indeed_web_index_v2.py. This filename is
kept stable because the production workflow and historical tests already invoke
it directly.

Implementation contract retained by v2:
- "engine": "google"
- "https://serpapi.com/search.json?"
- candidate_indeed_index_direct_indeed_requests is always 0
- no backend request is made to jp.indeed.com
"""
from supplement_indeed_web_index_v2 import *  # noqa: F401,F403
from supplement_indeed_web_index_v2 import main


if __name__ == "__main__":
    main()
