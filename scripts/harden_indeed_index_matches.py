#!/usr/bin/env python3
"""Fail closed on ambiguous Indeed web-index promotions.

The preceding index supplement can only point an already screened candidate at
an exact Indeed viewjob URL. This second pass tightens truthfulness further: when
the structured candidate has a usable company name, that company must also be
visible in the indexed Indeed title/snippet for the same jk. Otherwise the
promotion is reverted to the original verified destination.

It also refreshes public source-count metadata after promotions/reverts so the
UI and the next Indeed-stock decision see the same truth.
"""
from __future__ import annotations

from collections import Counter
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "jobs.json"
VERSION = 1


def normalize(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).lower()
    text = re.sub(r"[^0-9a-zぁ-んァ-ヶ一-龯]+", "", text)
    return text.strip()


def usable_company(value: object) -> str:
    company = normalize(value)
    generic = {
        "非公開", "会社名非公開", "企業名非公開", "confidential", "undisclosed",
        "unknown", "不明", "indeed",
    }
    if not company or company in generic or len(company) < 3:
        return ""
    return company


def seed_by_jk(payload: dict) -> dict[str, dict]:
    result: dict[str, dict] = {}
    seeds = payload.get("candidate_indeed_index_seeds") or []
    if not isinstance(seeds, list):
        return result
    for seed in seeds:
        if not isinstance(seed, dict):
            continue
        jk = str(seed.get("jk") or "").strip()
        if jk:
            result[jk] = seed
    return result


def indexed_company_matches(row: dict, seed: dict | None) -> bool:
    company = usable_company(row.get("company"))
    if not company:
        return True
    if not isinstance(seed, dict):
        return False
    indexed = normalize(f"{seed.get('title', '')} {seed.get('snippet', '')}")
    return bool(indexed and company in indexed)


def revert_promotion(row: dict) -> bool:
    original_id = str(row.get("original_candidate_id") or "").strip()
    original_url = str(row.get("original_apply_url") or "").strip()
    original_source = str(row.get("original_apply_source") or "").strip()
    original_kind = str(row.get("original_apply_source_kind") or "").strip()
    if original_id:
        row["id"] = original_id
    if not original_url or not original_kind:
        row["apply_source_kind"] = original_kind or "unverified"
        row["apply_source"] = original_source or "Original source"
        if original_url:
            row["url"] = original_url
    else:
        row["url"] = original_url
        row["apply_source"] = original_source or "Original source"
        row["apply_source_kind"] = original_kind
    row["indeed_index_promotion_reverted"] = True
    row["indeed_index_revert_reason"] = "indexed-company-not-confirmed"
    row["indeed_index_hardening_version"] = VERSION
    return True


def refresh_source_counts(payload: dict) -> None:
    source_counts: Counter[str] = Counter()
    kind_counts: Counter[str] = Counter()
    indeed = 0
    trusted_other = 0
    for row in payload.get("jobs") or []:
        if not isinstance(row, dict):
            continue
        source = str(row.get("apply_source") or "").strip()
        kind = str(row.get("apply_source_kind") or "").strip()
        if source:
            source_counts[source] += 1
        if kind:
            kind_counts[kind] += 1
        if kind == "indeed" and str(row.get("url") or "").startswith("https://jp.indeed.com/viewjob?jk="):
            indeed += 1
        elif kind.startswith("trusted-"):
            trusted_other += 1
    payload["candidate_final_apply_source_counts"] = dict(source_counts.most_common(10))
    payload["candidate_final_apply_source_kind_counts"] = dict(kind_counts.most_common())
    payload["candidate_final_indeed_apply_jobs"] = indeed
    payload["candidate_final_other_trusted_apply_jobs"] = trusted_other


def process(payload: dict) -> dict:
    seeds = seed_by_jk(payload)
    reviewed = 0
    kept = 0
    reverted = 0
    for row in payload.get("jobs") or []:
        if not isinstance(row, dict) or int(row.get("indeed_index_match_version") or 0) <= 0:
            continue
        reviewed += 1
        jk = str(row.get("indeed_index_jk") or "").strip()
        if indexed_company_matches(row, seeds.get(jk)):
            row["indeed_index_hardening_version"] = VERSION
            row["indeed_index_company_confirmed"] = bool(usable_company(row.get("company")))
            kept += 1
        else:
            revert_promotion(row)
            reverted += 1
    payload["candidate_indeed_index_hardening_version"] = VERSION
    payload["candidate_indeed_index_hardening_reviewed"] = reviewed
    payload["candidate_indeed_index_hardening_kept"] = kept
    payload["candidate_indeed_index_hardening_reverted"] = reverted
    refresh_source_counts(payload)
    return payload


def main() -> None:
    try:
        payload = json.loads(OUT.read_text(encoding="utf-8"))
    except Exception:
        return
    if not isinstance(payload, dict):
        return
    process(payload)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        "Indeed index hardening: "
        f"reviewed={payload.get('candidate_indeed_index_hardening_reviewed', 0)} "
        f"kept={payload.get('candidate_indeed_index_hardening_kept', 0)} "
        f"reverted={payload.get('candidate_indeed_index_hardening_reverted', 0)}"
    )


if __name__ == "__main__":
    main()
