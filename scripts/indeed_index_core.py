#!/usr/bin/env python3
"""Pure helpers shared by Indeed public-index discovery revisions."""
from __future__ import annotations

import difflib
import json
import re
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "jobs.json"
NOW = datetime.now(timezone.utc)
SEED_TTL_DAYS = 14
MAX_SEEDS = 100
MATCH_THRESHOLD = 0.78
BASELINE_REQUESTS_PER_DAY = 1
SEED_VERIFICATION_LEVEL = "exact-url-public-index"
PROMOTED_VERIFICATION_LEVEL = "exact-url-title-company-index-match"

GENERIC_TITLE_TERMS = {
    "indeed", "job", "jobs", "remote", "japan", "japanese", "求人", "完全在宅",
    "フルリモート", "在宅", "募集", "採用", "スタッフ", "仕事", "業務", "the", "and",
}


def load_json(path: Path | None) -> dict:
    if path is None:
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def write_payload(payload: dict, path: Path = OUT) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_iso(value: object) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _valid_job_key(value: object) -> str:
    key = str(value or "").strip()
    return key if re.fullmatch(r"[A-Za-z0-9_-]{6,128}", key) else ""


def _indeed_parsed(value: object) -> urllib.parse.ParseResult | None:
    try:
        parsed = urllib.parse.urlparse(str(value or ""))
    except Exception:
        return None
    host = (parsed.hostname or "").lower().strip(".")
    if parsed.scheme.lower() != "https" or not (
        host == "indeed.com" or host.endswith(".indeed.com")
    ):
        return None
    return parsed


def canonical_indeed_url(value: object) -> tuple[str, str] | None:
    """Accept only an explicit Indeed /viewjob?jk= URL."""
    parsed = _indeed_parsed(value)
    if not parsed or parsed.path.lower() != "/viewjob":
        return None
    params = urllib.parse.parse_qs(parsed.query)
    jk = _valid_job_key((params.get("jk") or [""])[0])
    if not jk:
        return None
    return (
        f"https://jp.indeed.com/viewjob?jk={urllib.parse.quote(jk, safe='')}",
        jk,
    )


def indexed_indeed_reference(value: object) -> tuple[str, str, str] | None:
    """Extract a concrete Indeed job key from a public-index URL.

    Google may index either the direct `/viewjob?jk=...` page or an Indeed search
    page with `?vjk=...`. A vjk is a concrete viewed-job key, but because the
    backend does not contact Indeed to verify the derived direct URL, it remains
    discovery-only evidence and cannot promote a screened candidate by itself.
    """
    canonical = canonical_indeed_url(value)
    if canonical:
        url, jk = canonical
        return url, jk, "viewjob-jk"
    parsed = _indeed_parsed(value)
    if not parsed:
        return None
    params = urllib.parse.parse_qs(parsed.query)
    vjk = _valid_job_key((params.get("vjk") or [""])[0])
    if not vjk:
        return None
    return (
        f"https://jp.indeed.com/viewjob?jk={urllib.parse.quote(vjk, safe='')}",
        vjk,
        "search-vjk",
    )


def clean_title(value: object) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = re.sub(
        r"\s*[-|–—]\s*(job post\s*[-|–—]\s*)?Indeed(?:\.com)?\s*$",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(r"\s*[-|–—]\s*(求人|採用情報)\s*$", "", text)
    return text.strip(" -|–—")


def normalized(value: object) -> str:
    text = clean_title(value).lower()
    text = re.sub(r"[^0-9a-zぁ-んァ-ヶ一-龯]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokens(value: object) -> set[str]:
    return {
        token
        for token in normalized(value).split()
        if len(token) >= 2 and token not in GENERIC_TITLE_TERMS
    }


def title_similarity(seed_title: str, row_title: str) -> float:
    a, b = normalized(seed_title), normalized(row_title)
    if not a or not b:
        return 0.0
    seq = difflib.SequenceMatcher(a=a, b=b).ratio()
    ta, tb = tokens(a), tokens(b)
    overlap = len(ta & tb) / max(1, len(ta | tb))
    containment = 1.0 if (a in b or b in a) and min(len(a), len(b)) >= 8 else 0.0
    return max(seq * 0.72 + overlap * 0.28, 0.90 * containment)


def match_score(seed: dict, row: dict) -> float:
    score = title_similarity(
        str(seed.get("title") or ""), str(row.get("title") or "")
    )
    company = normalized(row.get("company"))
    indexed_text = normalized(f"{seed.get('title', '')} {seed.get('snippet', '')}")
    if company and len(company) >= 3 and company in indexed_text:
        score = min(1.0, score + 0.12)
    return score


def _stamp_seed_truth(seed: dict) -> dict:
    seed = dict(seed)
    kind = str(seed.get("indeed_index_link_kind") or "viewjob-jk")
    direct = kind == "viewjob-jk"
    seed["indeed_index_link_kind"] = kind
    seed["indeed_job_key_verified"] = True
    seed["indeed_verification_level"] = (
        SEED_VERIFICATION_LEVEL if direct else "job-key-public-index"
    )
    seed["indeed_exact_url_verified"] = direct
    seed["indeed_canonical_url_derived_from_vjk"] = not direct
    seed["indeed_page_body_verified"] = False
    seed["indeed_page_body_access_method"] = "not-accessed-without-partner-permission"
    seed["indeed_evidence_source"] = (
        "google-public-index" if direct else "google-public-index-indeed-search-vjk"
    )
    seed["indeed_promotion_eligible"] = direct
    return seed


def extract_seeds(payload: dict, profile: str) -> list[dict]:
    rows = payload.get("organic_results") or []
    if not isinstance(rows, list):
        return []
    found: dict[str, dict] = {}
    for item in rows:
        if not isinstance(item, dict):
            continue
        reference = indexed_indeed_reference(item.get("link"))
        if not reference:
            continue
        url, jk, link_kind = reference
        indexed_title = clean_title(item.get("title"))
        if link_kind == "viewjob-jk":
            title = indexed_title
            if not title:
                continue
        else:
            # Search-page titles describe the query, not necessarily the selected
            # vjk job. Never pretend that generic title is the job title.
            title = f"Indeed求人ID確認（{profile}）"
        found[jk] = _stamp_seed_truth({
            "jk": jk,
            "url": url,
            "title": title[:240],
            "indexed_page_title": indexed_title[:240],
            "snippet": re.sub(r"\s+", " ", str(item.get("snippet") or "")).strip()[:420],
            "profile": profile,
            "last_seen": NOW.isoformat(),
            "indeed_index_link_kind": link_kind,
        })
    return list(found.values())


def merge_seeds(previous: list[dict], fresh: list[dict]) -> list[dict]:
    cutoff = NOW - timedelta(days=SEED_TTL_DAYS)
    merged: dict[str, dict] = {}
    for item in previous:
        if not isinstance(item, dict):
            continue
        reference = indexed_indeed_reference(item.get("url"))
        seen = parse_iso(item.get("last_seen"))
        if not reference or not seen or seen < cutoff:
            continue
        _, jk, _ = reference
        copied = _stamp_seed_truth(item)
        copied["jk"] = jk
        merged[jk] = copied
    for item in fresh:
        jk = str(item.get("jk") or "")
        if not jk:
            continue
        old = merged.get(jk) or {}
        item = _stamp_seed_truth(item)
        item["first_seen"] = old.get("first_seen") or NOW.isoformat()
        # Prefer stronger direct-viewjob evidence over search-vjk evidence for the
        # same job key, while retaining the freshest seen timestamp.
        if old and old.get("indeed_index_link_kind") == "viewjob-jk" and item.get("indeed_index_link_kind") != "viewjob-jk":
            old = dict(old)
            old["last_seen"] = item.get("last_seen") or old.get("last_seen")
            old["profiles_seen"] = sorted(set((old.get("profiles_seen") or []) + [str(item.get("profile") or "")]) - {""})
            merged[jk] = _stamp_seed_truth(old)
        else:
            prior_profiles = old.get("profiles_seen") or []
            item["profiles_seen"] = sorted(set(prior_profiles + [str(item.get("profile") or "")]) - {""})
            merged[jk] = item
    values = sorted(
        merged.values(),
        key=lambda item: parse_iso(item.get("last_seen"))
        or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return values[:MAX_SEEDS]


def promote_matches(payload: dict, seeds: list[dict]) -> int:
    promoted = 0
    used_jk: set[str] = set()
    jobs = payload.get("jobs") or []
    if not isinstance(jobs, list):
        return 0
    eligible_seeds = [
        seed for seed in seeds
        if isinstance(seed, dict) and seed.get("indeed_promotion_eligible") is True
    ]
    for row in jobs:
        if not isinstance(row, dict):
            continue
        if canonical_indeed_url(row.get("url")) and str(
            row.get("apply_source_kind") or ""
        ).lower() == "indeed":
            continue
        ranked = sorted(
            (
                (match_score(seed, row), seed)
                for seed in eligible_seeds
                if str(seed.get("jk") or "") not in used_jk
            ),
            key=lambda pair: pair[0],
            reverse=True,
        )
        if not ranked or ranked[0][0] < MATCH_THRESHOLD:
            continue
        score, seed = ranked[0]
        canonical = canonical_indeed_url(seed.get("url"))
        if not canonical:
            continue
        url, jk = canonical
        row["original_candidate_id"] = row.get("original_candidate_id") or row.get("id")
        row["original_apply_url"] = row.get("original_apply_url") or row.get("url")
        row["original_apply_source"] = row.get("original_apply_source") or row.get(
            "apply_source"
        )
        row["original_apply_source_kind"] = row.get(
            "original_apply_source_kind"
        ) or row.get("apply_source_kind")
        row["id"] = jk
        row["url"] = url
        row["apply_source"] = "Indeed"
        row["apply_source_kind"] = "indeed"
        row["source"] = (
            "Google public index exact Indeed URL matched to an already screened "
            "candidate from a separate source"
        )
        row["indeed_index_match_version"] = 4
        row["indeed_index_match_score"] = round(score, 3)
        row["indeed_index_jk"] = jk
        row["indeed_index_verified_at"] = NOW.isoformat()
        row["indeed_index_seed_last_seen"] = seed.get("last_seen")
        row["indeed_verification_level"] = PROMOTED_VERIFICATION_LEVEL
        row["indeed_exact_url_verified"] = True
        row["indeed_page_body_verified"] = False
        row["indeed_page_body_access_method"] = "not-accessed-without-partner-permission"
        row["indeed_evidence_source"] = "google-public-index"
        row["indeed_content_screening_basis"] = "separate-screened-source"
        used_jk.add(jk)
        promoted += 1
    return promoted


def monthly_headroom(payload: dict) -> tuple[int, int, int]:
    try:
        used = max(0, int(payload.get("serpapi_requests_month") or 0))
    except Exception:
        used = 0
    try:
        cap = max(1, int(payload.get("serpapi_monthly_request_cap") or 245))
    except Exception:
        cap = 245
    try:
        days = max(1, int(payload.get("serpapi_month_days_remaining") or 1))
    except Exception:
        days = 1
    return used, cap, days
