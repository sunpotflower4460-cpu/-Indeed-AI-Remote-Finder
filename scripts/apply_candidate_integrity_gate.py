#!/usr/bin/env python3
"""Final Japan-compatibility, identity-dependency, and semantic-duplicate gate.

The product is intended for a person living in Japan who wants remote work whose
recurring digital execution can be delegated heavily to software/AI. Existing
remote/automation gates are necessary but not sufficient: a listing can be
fully remote yet restricted to another country, or require the applicant's own
voice, face, personal activity history, or account history.

This gate runs after rolling-pool postprocessing and before paid LLM review so
those candidates are removed early. It also collapses safe same-company title
variants such as location-specific copies of the same AI-training role.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FEED = ROOT / "data" / "jobs.json"
INTEGRITY_GATE_VERSION = 1
SEMANTIC_DEDUPE_VERSION = 1

FOREIGN_MARKETS = (
    "united states", "u.s.", "u.s.a.", "usa", "canada", "australia",
    "hong kong", "singapore", "united kingdom", "uk", "india", "germany",
    "france", "spain", "italy", "brazil", "mexico", "new zealand",
    "ireland", "netherlands", "switzerland", "poland", "philippines",
)

# Strong foreign-market evidence. We intentionally do not reject a description
# merely because it mentions a foreign country; it must describe the worker's
# required residence/work eligibility or the role itself as foreign-market-only.
FOREIGN_RESTRICTION_PATTERNS = (
    re.compile(
        r"\b(?:must|required\s+to|need\s+to|currently)\s+(?:be\s+)?"
        r"(?:based|located|residing|living)\s+in\s+(?:the\s+)?"
        r"(united states|u\.s\.?|u\.s\.a\.?|usa|canada|australia|hong kong|"
        r"singapore|united kingdom|uk|india|germany|france|spain|italy|brazil|"
        r"mexico|new zealand|ireland|netherlands|switzerland|poland|philippines)\b",
        re.I,
    ),
    re.compile(
        r"\b(?:right|authorization|authorisation|permission)\s+to\s+work\s+in\s+"
        r"(?:the\s+)?(united states|u\.s\.?|u\.s\.a\.?|usa|canada|australia|"
        r"hong kong|singapore|united kingdom|uk|india|germany|france|spain|italy|"
        r"brazil|mexico|new zealand|ireland|netherlands|switzerland|poland|philippines)\b",
        re.I,
    ),
)

FOREIGN_BASED_TITLE = re.compile(
    r"\b(?:us|u\.s\.|usa|united states|canada|australia|hong kong|singapore|"
    r"uk|united kingdom|india|germany|france|spain|italy|brazil|mexico|"
    r"new zealand)[ -]based\b",
    re.I,
)

IDENTITY_DEPENDENCY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("own-voice", re.compile(r"(?:record(?:ing)?|provide|submit)[^.\n]{0,45}(?:your|own)\s+voice|record\s+yourself\s+speaking", re.I)),
    ("own-likeness", re.compile(r"(?:your|own)\s+(?:likeness|face|selfie)|(?:photo|video)\s+(?:of\s+)?yourself", re.I)),
    ("own-media", re.compile(r"recordings?\s+of\s+your\s+voice\s+and\s+likeness|submit\s+content\s+featuring\s+only\s+yourself", re.I)),
    ("personal-activity-history", re.compile(r"(?:your|personalized\s+based\s+on\s+your)\s+activity\s+history|places\s+you(?:'|’)ve\s+previously\s+visited", re.I)),
    ("personal-account-history", re.compile(r"existing[^.\n]{0,40}(?:gmail|google)\s+account[^.\n]{0,80}(?:prior|usage|history)", re.I)),
    ("personal-history-consent", re.compile(r"consent[- ]based\s+access[^.\n]{0,100}(?:your|activity)\s+history", re.I)),
    ("live-camera", re.compile(r"(?:camera|webcam)[^.\n]{0,30}(?:remain|stay|keep)[^.\n]{0,20}(?:on|enabled)|live\s+video\s+call", re.I)),
)

# A few platforms explicitly require a continuous human session even though the
# role is remote. This is stronger evidence than a generic weekly-hour target.
CONTINUOUS_ATTENTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("uninterrupted-human-session", re.compile(r"(?:require|requires|required|must be prepared)[^.\n]{0,60}\bone\s+hour\s+of\s+uninterrupted\s+work\b", re.I)),
)

GEO_SUFFIX = re.compile(
    r"\s*(?:-|–|—)\s*(?:[a-z .'-]+,\s*)?japan\s*$",
    re.I,
)
REMOTE_PAREN = re.compile(r"\s*\([^)]*\b(?:fully\s+remote|remote)\b[^)]*\)\s*$", re.I)
REMOTE_SUFFIX = re.compile(r"\s*(?:-|–|—)\s*(?:fully\s+)?remote\s*$", re.I)


def _text(row: dict) -> str:
    return " ".join(str(row.get(key) or "") for key in ("title", "location", "snippet")).strip()


def _normalized(value: object) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).lower()


def japan_eligibility_rejection(row: dict) -> str | None:
    title = _normalized(row.get("title"))
    location = _normalized(row.get("location"))
    text = _normalized(_text(row))

    if FOREIGN_BASED_TITLE.search(title):
        return "foreign-market-title"

    for pattern in FOREIGN_RESTRICTION_PATTERNS:
        match = pattern.search(text)
        if match:
            return f"foreign-residence-or-work-rights:{match.group(1).lower()}"

    # Location fields like "USA (Remote)" or "Canada - Remote" are explicit
    # enough to reject when they are not qualified as worldwide/global/Japan.
    global_hint = any(value in location for value in ("worldwide", "world wide", "global", "anywhere"))
    japan_hint = bool(re.search(r"\bjapan\b", location)) or "日本" in location
    if not global_hint and not japan_hint:
        for market in FOREIGN_MARKETS:
            if market in location and "remote" in location:
                return f"foreign-remote-location:{market}"
    return None


def identity_dependency_rejection(row: dict) -> str | None:
    text = _text(row)
    for reason, pattern in IDENTITY_DEPENDENCY_PATTERNS:
        if pattern.search(text):
            return reason
    for reason, pattern in CONTINUOUS_ATTENTION_PATTERNS:
        if pattern.search(text):
            return reason
    return None


def japan_eligibility_status(row: dict) -> str:
    text = _normalized(_text(row))
    if re.search(r"\bjapan\b", text) or "日本" in text:
        return "japan-explicit"
    if any(value in text for value in ("worldwide", "world wide", "global", "anywhere")):
        return "worldwide-explicit"
    return "no-foreign-restriction-detected"


def _canonical_title(row: dict) -> str:
    title = unicodedata.normalize("NFKC", str(row.get("title") or "")).strip()
    company = _normalized(row.get("company"))
    lower = title.lower()

    # Known boards frequently clone exactly the same role for multiple cities.
    if "prolific" in company:
        if lower.startswith("ai trainer - advanced japanese fluency"):
            return "ai trainer - advanced japanese fluency"
        if lower.startswith("japanese - fluent speakers - ai training"):
            return "japanese - fluent speakers - ai training - japan"

    title = REMOTE_PAREN.sub("", title)
    title = GEO_SUFFIX.sub("", title)
    title = REMOTE_SUFFIX.sub("", title)
    title = re.sub(r"\s+", " ", title).strip(" -–—")
    return title.lower()


def semantic_fingerprint(row: dict) -> str:
    company = re.sub(r"[^\w一-龯ぁ-んァ-ヶ]+", "", _normalized(row.get("company")))
    title = re.sub(r"[^\w一-龯ぁ-んァ-ヶ]+", "", _normalized(_canonical_title(row)))
    if not company or not title:
        return f"id:{row.get('id') or ''}"
    return f"{company}|{title}"


def _rank(row: dict) -> tuple[int, int, int, int, int]:
    return (
        1 if row.get("tier") == "high" else 0,
        1 if row.get("llm_strict_pass") is True else 0,
        int(row.get("automation_confidence") or 0),
        int(row.get("remote_confidence") or 0),
        int(row.get("freshness_confidence") or 0),
    )


def semantic_dedupe(rows: list[dict]) -> tuple[list[dict], int]:
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(semantic_fingerprint(row), []).append(row)

    kept: list[dict] = []
    removed = 0
    for group in groups.values():
        group.sort(key=_rank, reverse=True)
        best = copy.deepcopy(group[0])
        total = sum(max(1, int(item.get("duplicate_count") or 1)) for item in group)
        locations: list[str] = []
        for item in group:
            for value in [item.get("location"), *(item.get("alternate_locations") or [])]:
                loc = str(value or "").strip()
                if loc and loc not in locations:
                    locations.append(loc)
        if len(group) > 1:
            removed += len(group) - 1
        best["duplicate_count"] = total
        if len(locations) > 1:
            best["alternate_locations"] = locations[:12]
        best["semantic_role_family"] = _canonical_title(best)
        kept.append(best)
    return kept, removed


def apply(payload: dict) -> dict:
    rows = [row for row in payload.get("jobs") or [] if isinstance(row, dict)]
    kept: list[dict] = []
    drops: dict[str, int] = {}

    for row in rows:
        geo_reason = japan_eligibility_rejection(row)
        if geo_reason:
            drops[geo_reason] = drops.get(geo_reason, 0) + 1
            continue
        identity_reason = identity_dependency_rejection(row)
        if identity_reason:
            drops[identity_reason] = drops.get(identity_reason, 0) + 1
            continue
        copy_row = copy.deepcopy(row)
        copy_row["candidate_integrity_gate_version"] = INTEGRITY_GATE_VERSION
        copy_row["japan_eligibility_status"] = japan_eligibility_status(copy_row)
        copy_row["human_identity_dependency"] = "none-detected"
        kept.append(copy_row)

    kept, semantic_removed = semantic_dedupe(kept)
    payload["jobs"] = kept
    payload["candidate_pool_size"] = len(kept)
    payload["candidate_integrity_gate_version"] = INTEGRITY_GATE_VERSION
    payload["candidate_semantic_dedupe_version"] = SEMANTIC_DEDUPE_VERSION
    payload["candidate_requires_japan_compatible"] = True
    payload["candidate_rejects_personal_identity_tasks"] = True
    payload["candidate_integrity_checked"] = len(rows)
    payload["candidate_integrity_dropped"] = len(rows) - len(kept) - semantic_removed
    payload["candidate_integrity_drop_reasons"] = drops
    payload["candidate_semantic_duplicates_dropped"] = semantic_removed
    return payload


def validate_active_payload(payload: dict) -> list[str]:
    if int(payload.get("candidate_integrity_gate_version") or 0) < INTEGRITY_GATE_VERSION:
        return []
    errors: list[str] = []
    seen: set[str] = set()
    for index, row in enumerate(payload.get("jobs") or []):
        if not isinstance(row, dict):
            continue
        prefix = f"jobs[{index}]"
        reason = japan_eligibility_rejection(row)
        if reason:
            errors.append(f"{prefix} is not Japan-compatible: {reason}")
        reason = identity_dependency_rejection(row)
        if reason:
            errors.append(f"{prefix} requires personal identity/presence: {reason}")
        if int(row.get("candidate_integrity_gate_version") or 0) < INTEGRITY_GATE_VERSION:
            errors.append(f"{prefix} missing integrity-gate stamp")
        fp = semantic_fingerprint(row)
        if fp in seen:
            errors.append(f"{prefix} duplicates a semantic role family")
        seen.add(fp)
    return errors


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("feed must be an object")
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feed", type=Path, default=DEFAULT_FEED)
    args = parser.parse_args()
    payload = apply(_load(args.feed))
    args.feed.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        "candidate integrity gate kept "
        f"{len(payload.get('jobs') or [])} jobs; "
        f"eligibility/identity dropped={payload.get('candidate_integrity_dropped', 0)}; "
        f"semantic duplicates={payload.get('candidate_semantic_duplicates_dropped', 0)}"
    )


if __name__ == "__main__":
    main()
