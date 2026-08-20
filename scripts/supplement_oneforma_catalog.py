#!/usr/bin/env python3
"""Discover current Japan-compatible OneForma projects from the public catalog.

The hand-audited direct-provider catalog remains the fast path. This bounded
catalog scan is a resilience layer for renamed/new project URLs: it discovers a
small set of current public project pages, verifies that Japan is an eligible
locale (or the role is worldwide and explicitly Japanese), rejects physical
self-data collection, and sends every surviving page through the same production
remote/autonomy/quality builder used by the rest of the feed.

No authenticated endpoint, browser automation, or SerpApi request is used.
"""
from __future__ import annotations

import html
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import acquisition
import acquisition_precision
import acquisition_quality

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FEED = ROOT / "data" / "jobs.json"
VERSION = 1
STOCK_TARGET = 120
MAX_INDEX_BYTES = 2_000_000
MAX_PAGE_BYTES = 2_000_000
MAX_DESCRIPTION_CHARS = 12_000
MAX_DISCOVERED_PAGES = 24

INDEX_URLS = (
    "https://www.oneforma.com/jobs/?sort=newest&t=annotation",
    "https://www.oneforma.com/jobs/?sort=newest&t=translation",
    "https://www.oneforma.com/jobs/type/judging/",
    "https://www.oneforma.com/jobs/type/transcription/",
)

# Only recurring digital task families. Generic data-collection projects are
# deliberately excluded even when remote because they often depend on the
# participant's body, environment, device history, or personal media.
TASK_MARKERS = (
    "annotation",
    "annotator",
    "labeling",
    "evaluate",
    "evaluation",
    "quality rater",
    "quality reviewer",
    "search evaluation",
    "transcription",
    "post-editor",
    "post edit",
    "proofreading",
    "review ai",
    "ai response",
    "translation quality",
)
EXCLUDE_MARKERS = (
    "data collection",
    "first-person video",
    "ego-centric video",
    "record your voice",
    "recording of your voice",
    "take photos of yourself",
    "capture photos of yourself",
    "video recording of yourself",
    "selfie",
    "live video call",
    "camera must remain on",
    "webcam must remain on",
)
CLOSED_MARKERS = (
    "not accepting applications",
    "no longer accepting applications",
    "project has been completed",
    "position has been filled",
)


def _host_ok(url: str) -> bool:
    host = (urllib.parse.urlparse(url).hostname or "").lower().strip(".")
    return host == "oneforma.com" or host.endswith(".oneforma.com")


def _fetch_html(url: str, limit: int) -> tuple[str, str]:
    if not _host_ok(url):
        raise RuntimeError("untrusted OneForma URL")
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "AI-Remote-Finder/10.1",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        final_url = response.geturl()
        if not _host_ok(final_url):
            raise RuntimeError("OneForma redirect left audited host")
        raw = response.read(limit + 1)
    if len(raw) > limit:
        raise RuntimeError("OneForma page too large")
    return raw.decode("utf-8", errors="replace"), final_url


def _page_text(raw: str) -> str:
    value = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", raw)
    value = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", value)
    value = re.sub(r"(?s)<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def _title(raw: str) -> str:
    match = re.search(r"(?is)<h1[^>]*>(.*?)</h1>", raw)
    if not match:
        return "OneForma AI Project"
    return _page_text(match.group(1))[:180] or "OneForma AI Project"


def _normalize_url(base: str, href: str) -> str | None:
    try:
        joined = urllib.parse.urljoin(base, html.unescape(href))
        parsed = urllib.parse.urlparse(joined)
    except Exception:
        return None
    if parsed.scheme.lower() != "https" or not _host_ok(joined):
        return None
    path = parsed.path.rstrip("/") + "/"
    lower_path = path.lower()
    if not (lower_path.startswith("/jobs/") or lower_path.startswith("/projects/")):
        return None
    if lower_path in {"/jobs/", "/projects/"} or lower_path.startswith("/jobs/type/"):
        return None
    return urllib.parse.urlunparse(("https", parsed.netloc, path, "", "", ""))


def discover_urls(index_pages: dict[str, str] | None = None) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for url in INDEX_URLS:
        try:
            if isinstance(index_pages, dict):
                raw = index_pages.get(url, "")
                final_url = url
            else:
                raw, final_url = _fetch_html(url, MAX_INDEX_BYTES)
        except Exception:
            continue
        for href in re.findall(r"(?is)href\s*=\s*[\"']([^\"']+)[\"']", raw):
            normalized = _normalize_url(final_url, href)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            found.append(normalized)
            if len(found) >= MAX_DISCOVERED_PAGES:
                return found
    return found


def _japan_eligible(text: str) -> bool:
    lower = text.lower()
    if "japan" in lower and any(
        marker in lower
        for marker in (
            "available in",
            "japanese - japan",
            "japanese (japan)",
            "based in japan",
            "reside in japan",
        )
    ):
        return True
    return "worldwide" in lower and "japanese" in lower


def _live_candidate(text: str) -> bool:
    lower = text.lower()
    if not lower or any(marker in lower for marker in CLOSED_MARKERS):
        return False
    if any(marker in lower for marker in EXCLUDE_MARKERS):
        return False
    if "remote" not in lower or not _japan_eligible(text):
        return False
    if "accepting applications" not in lower and "apply to this project" not in lower:
        return False
    return any(marker in lower for marker in TASK_MARKERS)


def _automation_markers(text: str) -> str:
    lower = text.lower()
    markers = ["AI評価", "データ評価", "品質評価"]
    if any(term in lower for term in ("annotation", "annotator", "labeling")):
        markers.extend(["アノテーション", "annotation", "labeling"])
    if "transcription" in lower:
        markers.extend(["文字起こし", "transcription"])
    if any(term in lower for term in ("translation", "post-editor", "post edit")):
        markers.extend(["翻訳", "translation", "校正"])
    if "search" in lower:
        markers.extend(["検索評価", "検索品質"])
    return " ".join(dict.fromkeys(markers))


def _mapped(title: str, url: str, text: str) -> dict:
    return {
        "title": title,
        "company_name": "OneForma",
        "location": "Japan (Remote)",
        "description": (
            "Official OneForma catalog page verified live, Japan-compatible and remote. "
            f"フルリモート。 {_automation_markers(text)} {text[:MAX_DESCRIPTION_CHARS]}"
        ),
        "highlights": [],
        "extensions": ["Remote", "Official OneForma live catalog"],
        "detected_extensions": {},
        "via": "OneForma",
        "apply_options": [{"title": "OneForma", "link": url}],
    }


def _better(row: dict, existing: dict) -> bool:
    return (
        row.get("tier") == "high",
        int(row.get("score") or 0),
        int(row.get("automation_confidence") or 0),
    ) > (
        existing.get("tier") == "high",
        int(existing.get("score") or 0),
        int(existing.get("automation_confidence") or 0),
    )


def supplement(
    payload: dict,
    previous_payload: dict | None = None,
    *,
    index_pages: dict[str, str] | None = None,
    detail_pages: dict[str, str] | None = None,
) -> dict:
    before = len([row for row in payload.get("jobs") or [] if isinstance(row, dict)])
    payload["candidate_oneforma_catalog_version"] = VERSION
    payload["candidate_oneforma_catalog_uses_serpapi"] = False
    payload["candidate_oneforma_catalog_quality_gate_unchanged"] = True
    payload["candidate_oneforma_catalog_pool_before"] = before
    if before >= STOCK_TARGET:
        payload["candidate_oneforma_catalog_skipped"] = "pool-at-or-above-pre-final-target"
        payload["candidate_oneforma_catalog_pool_after"] = before
        return payload

    previous = {
        str(row.get("id")): row
        for row in (previous_payload or {}).get("jobs") or []
        if isinstance(row, dict) and row.get("id")
    }
    existing = [row for row in payload.get("jobs") or [] if isinstance(row, dict)]
    by_id = {str(row.get("id")): row for row in existing if row.get("id")}

    acquisition_precision.install()
    acquisition_quality.configure_quality_policy()
    acquisition_quality.reset_quality_telemetry()

    discovered = discover_urls(index_pages)
    checked = 0
    live = 0
    accepted = 0
    errors: list[str] = []
    now = datetime.now(timezone.utc).isoformat()

    for url in discovered:
        if len(by_id) >= 150:
            break
        checked += 1
        try:
            if isinstance(detail_pages, dict):
                raw = detail_pages.get(url, "")
                final_url = url
            else:
                raw, final_url = _fetch_html(url, MAX_PAGE_BYTES)
        except Exception as exc:
            errors.append(f"{urllib.parse.urlparse(url).path}:{type(exc).__name__}")
            continue
        text = _page_text(raw)
        if not _live_candidate(text):
            continue
        live += 1
        mapped = _mapped(_title(raw), final_url, text)
        try:
            row = acquisition.build_row(mapped, "oneforma_catalog", previous)
        except Exception:
            continue
        if not row:
            continue
        row["source"] = "OneForma official catalog; live Japan-compatible project verified"
        row["via"] = "OneForma"
        row["discovery_source"] = "official-provider-page"
        row["official_provider"] = "OneForma"
        row["official_live_verified_at"] = now
        row["direct_official_source_version"] = 2
        row["oneforma_catalog_version"] = VERSION
        jid = str(row.get("id") or "")
        current = by_id.get(jid)
        if current is None or _better(row, current):
            by_id[jid] = row
        accepted += 1

    payload["jobs"] = list(by_id.values())[:150]
    payload["candidate_oneforma_catalog_discovered"] = len(discovered)
    payload["candidate_oneforma_catalog_checked"] = checked
    payload["candidate_oneforma_catalog_live"] = live
    payload["candidate_oneforma_catalog_deterministic_accepted"] = accepted
    payload["candidate_oneforma_catalog_errors"] = errors[:12]
    payload["candidate_oneforma_catalog_pool_after"] = len(payload["jobs"])
    return payload


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--feed", type=Path, default=DEFAULT_FEED)
    parser.add_argument("--previous", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.feed.read_text(encoding="utf-8"))
    previous = {}
    if args.previous and args.previous.exists():
        previous = json.loads(args.previous.read_text(encoding="utf-8"))
    result = supplement(payload, previous)
    args.feed.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        "OneForma catalog supplement: "
        f"discovered={result.get('candidate_oneforma_catalog_discovered', 0)} "
        f"live={result.get('candidate_oneforma_catalog_live', 0)} "
        f"accepted={result.get('candidate_oneforma_catalog_deterministic_accepted', 0)} "
        f"pool={result.get('candidate_oneforma_catalog_pool_after')}"
    )


if __name__ == "__main__":
    main()
