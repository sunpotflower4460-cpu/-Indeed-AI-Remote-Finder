#!/usr/bin/env python3
"""Production acquisition entrypoint seeded by exact Indeed index discoveries.

The normal precision pipeline remains authoritative. When the previous index
probe found an actual jp.indeed.com/viewjob URL, the newest indexed title gets
one first-page Google Jobs probe before the normal rotating profiles. This lets
structured job details and the exact Indeed destination converge without ever
fetching the Indeed page itself.
"""
from __future__ import annotations

import re

import acquisition
import acquisition_precision


def _seed_profile() -> tuple[str, str] | None:
    payload = acquisition.load_payload()
    seeds = payload.get("candidate_indeed_index_seeds") or []
    if not isinstance(seeds, list):
        return None
    for seed in seeds:
        if not isinstance(seed, dict):
            continue
        title = re.sub(r"\s+", " ", str(seed.get("title") or "")).strip()
        jk = re.sub(r"[^A-Za-z0-9_-]", "", str(seed.get("jk") or ""))[:12]
        if len(title) < 4 or not jk:
            continue
        # The title originates from a real indexed Indeed viewjob result. The
        # Indeed term biases Google Jobs toward exposing its Indeed apply option.
        return f"indeed_index_seed_{jk}", f'"{title[:180]}" Indeed'
    return None


def install_seed_priority() -> None:
    seed = _seed_profile()
    if not seed:
        return
    original = acquisition.rotated_profiles

    def seeded_rotated_profiles(cursor: int) -> list[tuple[str, str]]:
        rows = original(cursor)
        name, query = seed
        return [(name, query)] + [item for item in rows if item[0] != name]

    acquisition.rotated_profiles = seeded_rotated_profiles


def main() -> None:
    install_seed_priority()
    acquisition_precision.main()


if __name__ == "__main__":
    main()
