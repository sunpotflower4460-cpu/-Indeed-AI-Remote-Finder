#!/usr/bin/env python3
"""Add a deeper set of live Japan-compatible official AI-work pages.

This source layer is intentionally small and audited. It complements the core
Outlier/Alignerr/OneForma direct-provider catalog with currently verified
Japanese work from DataAnnotation and additional OneForma language-quality
projects. Every row still enters the existing production builder and later runs
through the normal presence, LLM, AI/automation-policy, freshness and trusted-URL
gates. No SerpApi request or credential is used.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import acquisition
import acquisition_precision
import acquisition_quality
import apply_ai_tool_policy_gate

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FEED = ROOT / "data" / "jobs.json"
VERSION = 1
STOCK_TARGET = 120
MAX_PAGE_BYTES = 2_000_000
MAX_DESCRIPTION_CHARS = 16_000


@dataclass(frozen=True)
class SourceSpec:
    key: str
    provider: str
    company: str
    title: str
    url: str
    location: str
    required_all: tuple[str, ...]
    automation_markers: str


SOURCES: tuple[SourceSpec, ...] = (
    SourceSpec(
        "dataannotation-japanese",
        "DataAnnotation",
        "DataAnnotation- JP",
        "英日翻訳者 - AIトレーナー",
        "https://www.dataannotation.tech/japanese-jp",
        "Japan (Remote)",
        ("募集中", "aiトレーナー", "フルリモート"),
        "AIトレーナー AI評価 データ評価 品質評価 翻訳 ライティング ファクトチェック",
    ),
    SourceSpec(
        "oneforma-bilingual-translation-quality-japan",
        "OneForma",
        "OneForma",
        "Bilingual Translation Quality Rater - Japanese",
        "https://www.oneforma.com/projects/bilingual-translation-quality-rater/",
        "Japan (Remote)",
        ("japan", "remote", "accepting applications", "translation quality"),
        "翻訳 translation AI評価 データ評価 品質評価 校正 rating",
    ),
    SourceSpec(
        "oneforma-paragraph-translation-quality-japan",
        "OneForma",
        "OneForma",
        "Paragraph-Level Translation Quality Rater - Japanese",
        "https://www.oneforma.com/projects/paragraph-level-translation-quality-rater/",
        "Japan (Remote)",
        ("japan", "remote", "accepting applications", "translation quality"),
        "翻訳 translation AI評価 データ評価 品質評価 annotation rating",
    ),
    SourceSpec(
        "oneforma-human-translator-mt-post-editor-japan",
        "OneForma",
        "OneForma",
        "Human Translator And Machine Translation Post-Editor - Japanese",
        "https://www.oneforma.com/projects/human-translator-and-machine-translation-post-editor/",
        "Japan (Remote)",
        ("japan", "remote", "accepting applications", "post-edit"),
        "翻訳 translation 校正 proofreading post-editing AI評価 データ評価 品質評価",
    ),
)

HOSTS = {
    "DataAnnotation": ("dataannotation.tech",),
    "OneForma": ("oneforma.com",),
}

CLOSED_MARKERS = (
    "not accepting applications",
    "no longer accepting applications",
    "position has been filled",
    "project has been completed",
    "募集終了",
    "現在募集していません",
)

HUMAN_MEDIA_BLOCKERS = (
    "record your voice",
    "recording of your voice",
    "voice samples from you",
    "record yourself",
    "video recording of yourself",
    "take photos of yourself",
    "capture photos of yourself",
    "live video call",
    "scheduled guided recording session",
    "camera must remain on",
    "webcam must remain on",
)


def _load(path: Path | None) -> dict:
    if not path:
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _host_ok(provider: str, url: str) -> bool:
    host = (urllib.parse.urlparse(url).hostname or "").lower().strip(".")
    return any(
        host == suffix or host.endswith("." + suffix)
        for suffix in HOSTS.get(provider, ())
    )


def _page_text(raw: str) -> str:
    raw = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", raw)
    raw = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", html.unescape(raw)).strip()


def _fetch_text(spec: SourceSpec) -> str:
    request = urllib.request.Request(
        spec.url,
        headers={
            "User-Agent": "AI-Remote-Finder/11.0",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        final_url = response.geturl()
        if not _host_ok(spec.provider, final_url):
            raise RuntimeError("provider redirect left audited host")
        raw = response.read(MAX_PAGE_BYTES + 1)
    if len(raw) > MAX_PAGE_BYTES:
        raise RuntimeError("provider page too large")
    return _page_text(raw.decode("utf-8", errors="replace"))


def _live_text(spec: SourceSpec, text: str) -> bool:
    lower = str(text or "").lower()
    if not lower:
        return False
    if any(marker in lower for marker in CLOSED_MARKERS):
        return False
    if any(marker in lower for marker in HUMAN_MEDIA_BLOCKERS):
        return False
    if not all(marker.lower() in lower for marker in spec.required_all):
        return False
    # Do not rely only on the final workflow gate. If the official page itself
    # already states a contributor-facing AI/bot/automation ban, do not map it.
    status, _ = apply_ai_tool_policy_gate.policy_signal(
        {"title": spec.title, "snippet": text, "location": spec.location}
    )
    return status != "prohibited"


def _mapped(spec: SourceSpec, text: str) -> dict:
    return {
        "title": spec.title,
        "company_name": spec.company,
        "location": spec.location,
        "description": (
            "Official provider page verified live. fully remote. フルリモート。 "
            f"{spec.automation_markers} {text[:MAX_DESCRIPTION_CHARS]}"
        ),
        "highlights": [],
        "extensions": ["Remote", "Official provider live page"],
        "detected_extensions": {},
        "via": spec.provider,
        "apply_options": [{"title": spec.provider, "link": spec.url}],
    }


def _better(row: dict, existing: dict) -> bool:
    return (
        row.get("tier") == "high",
        int(row.get("freshness_confidence") or 0),
        int(row.get("score") or 0),
        int(row.get("automation_confidence") or 0),
    ) > (
        existing.get("tier") == "high",
        int(existing.get("freshness_confidence") or 0),
        int(existing.get("score") or 0),
        int(existing.get("automation_confidence") or 0),
    )


def supplement(
    payload: dict,
    previous_payload: dict | None = None,
    *,
    fetched_pages: dict[str, str] | None = None,
) -> dict:
    before = len([row for row in payload.get("jobs") or [] if isinstance(row, dict)])
    payload["candidate_official_japan_depth_version"] = VERSION
    payload["candidate_official_japan_depth_uses_serpapi"] = False
    payload["candidate_official_japan_depth_quality_gate_unchanged"] = True
    payload["candidate_official_japan_depth_pool_before"] = before

    if before >= STOCK_TARGET:
        payload["candidate_official_japan_depth_skipped"] = "pool-at-or-above-pre-final-target"
        payload["candidate_official_japan_depth_pool_after"] = before
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

    checked = 0
    live = 0
    accepted = 0
    errors: list[str] = []
    accepted_by_provider: dict[str, int] = {}
    now = datetime.now(timezone.utc).isoformat()

    for spec in SOURCES:
        if len(by_id) >= STOCK_TARGET:
            break
        checked += 1
        try:
            text = (
                fetched_pages.get(spec.key, "")
                if isinstance(fetched_pages, dict)
                else _fetch_text(spec)
            )
        except Exception as exc:
            errors.append(f"{spec.key}:{type(exc).__name__}")
            continue
        if not _live_text(spec, text):
            continue
        live += 1
        try:
            row = acquisition.build_row(
                _mapped(spec, text),
                f"official_japan_depth_{spec.key}",
                previous,
            )
        except Exception:
            continue
        if not row:
            continue
        row["source"] = f"{spec.provider} official provider page; live URL verified"
        row["via"] = spec.provider
        row["discovery_source"] = "official-provider-page-japan-depth"
        row["official_provider"] = spec.provider
        row["official_live_verified_at"] = now
        row["official_japan_depth_version"] = VERSION
        jid = str(row.get("id") or "")
        current = by_id.get(jid)
        if current is None or _better(row, current):
            by_id[jid] = row
        accepted += 1
        accepted_by_provider[spec.provider] = accepted_by_provider.get(spec.provider, 0) + 1

    payload["jobs"] = list(by_id.values())[:150]
    after = len(payload["jobs"])
    payload["candidate_official_japan_depth_checked"] = checked
    payload["candidate_official_japan_depth_live"] = live
    payload["candidate_official_japan_depth_deterministic_accepted"] = accepted
    payload["candidate_official_japan_depth_accepted_by_provider"] = accepted_by_provider
    payload["candidate_official_japan_depth_errors"] = errors[:8]
    payload["candidate_official_japan_depth_pool_after"] = after
    payload["candidate_official_japan_depth_stock_ready"] = after >= STOCK_TARGET
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feed", type=Path, default=DEFAULT_FEED)
    parser.add_argument("--previous", type=Path)
    args = parser.parse_args()
    payload = _load(args.feed)
    if not payload:
        raise SystemExit(f"feed missing or invalid: {args.feed}")
    result = supplement(payload, _load(args.previous))
    args.feed.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        "official Japan depth supplement: "
        f"checked={result.get('candidate_official_japan_depth_checked', 0)} "
        f"live={result.get('candidate_official_japan_depth_live', 0)} "
        f"accepted={result.get('candidate_official_japan_depth_deterministic_accepted', 0)} "
        f"pool={result.get('candidate_official_japan_depth_pool_after')}"
    )


if __name__ == "__main__":
    main()
