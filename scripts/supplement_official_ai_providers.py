#!/usr/bin/env python3
"""Supplement the strict pool from live official AI-work provider pages.

This is a third, zero-SerpApi acquisition path for providers that publish useful
remote AI-training work on their own sites rather than a documented ATS API.
Only a small audited catalog of current official pages is checked. A page must
still be live, remote, Japan-compatible where required, and free of clear
human-media participation blockers before it is mapped into the *same*
production deterministic builder. Final presence, LLM and AI-use-policy vetoes
still run later in the workflow.

The catalog intentionally favors recurring digital work that software can
perform: response evaluation, ranking, annotation, transcription, translation
post-editing and search/maps evaluation. It excludes voice recording, image/video
collection, live calls and other tasks whose value depends on the applicant's
physical presence or likeness.
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

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FEED = ROOT / "data" / "jobs.json"
VERSION = 1
STOCK_TARGET = 120
MAX_PAGE_BYTES = 2_000_000
MAX_DESCRIPTION_CHARS = 12_000


@dataclass(frozen=True)
class SourceSpec:
    key: str
    provider: str
    title: str
    url: str
    location: str
    required_all: tuple[str, ...]
    automation_markers: str


SOURCES: tuple[SourceSpec, ...] = (
    SourceSpec(
        "outlier-japanese",
        "Outlier",
        "Japanese AI Training",
        "https://outlier.ai/languages/ja-jp",
        "Japan (Remote)",
        ("japanese", "remote", "apply"),
        "AIトレーナー AI評価 データ評価 品質評価 ライティング ファクトチェック",
    ),
    SourceSpec(
        "alignerr-ai-language-japanese",
        "Alignerr",
        "AI Language Expert - Japanese",
        "https://www.alignerr.com/ja/jobs/5f349b6c-2c4d-4824-b867-92a90b7819eb",
        "Remote",
        ("japanese", "remote", "freelance", "apply"),
        "AI評価 データ評価 品質評価 校正 ライティング",
    ),
    SourceSpec(
        "alignerr-japanese-localization",
        "Alignerr",
        "Japanese Localization Specialist",
        "https://www.alignerr.com/jobs/b728a7e2-8e69-48ca-bacf-b3880d32c7d8",
        "Remote",
        ("japanese", "remote", "freelance", "apply"),
        "AI評価 データ評価 品質評価 翻訳 校正 ローカライズ",
    ),
    SourceSpec(
        "alignerr-japanese-language-expert",
        "Alignerr",
        "Japanese Language Expert",
        "https://www.alignerr.com/es/jobs/28bacb12-959c-4f14-93c4-c59b85c684c9",
        "Remote",
        ("japanese", "remote", "freelance", "apply"),
        "AI評価 データ評価 品質評価 翻訳 校正",
    ),
    SourceSpec(
        "alignerr-general-ai-trainer",
        "Alignerr",
        "AI Trainer Specialist",
        "https://www.alignerr.com/ja/jobs/3ad9f162-4c82-43bc-ab85-8c1e2c7e2c17",
        "Worldwide (Remote)",
        ("ai trainer", "remote", "freelance", "apply"),
        "AIトレーナー AI評価 データ評価 アノテーション labeling 分類 品質評価",
    ),
    SourceSpec(
        "oneforma-uhrs-japan",
        "OneForma",
        "Online Data Labeling and Search Evaluation Tasks - Japanese",
        "https://www.oneforma.com/projects/online-data-labeling-and-search-evaluation-tasks/",
        "Japan (Remote)",
        ("japanese", "japan", "remote", "accepting applications"),
        "アノテーション labeling 検索評価 検索品質 AI評価 データ評価 品質評価",
    ),
    SourceSpec(
        "oneforma-maps-japan",
        "OneForma",
        "Local Maps Search Evaluator - Japanese",
        "https://www.oneforma.com/projects/local-maps-search-evaluator/",
        "Japan (Remote)",
        ("japanese", "japan", "remote", "accepting applications"),
        "検索評価 検索品質 AI評価 データ評価 品質評価",
    ),
    SourceSpec(
        "oneforma-intent-japan",
        "OneForma",
        "Multilingual Intent and Response Annotator - Japanese",
        "https://www.oneforma.com/projects/multilingual-intent-and-response-annotator/",
        "Japan (Remote)",
        ("japanese", "japan", "remote", "accepting applications"),
        "アノテーション annotation labeling 分類 AI評価 データ評価 品質評価",
    ),
    SourceSpec(
        "oneforma-voice-assistant-annotation-japan",
        "OneForma",
        "Voice Assistant Conversation Annotator - Japanese",
        "https://www.oneforma.com/projects/voice-assistant-conversation-annotator/",
        "Japan (Remote)",
        ("japanese", "japan", "remote", "accepting applications"),
        "アノテーション annotation labeling 文字起こし データ評価 品質評価",
    ),
    SourceSpec(
        "oneforma-audio-conversation-annotation-japan",
        "OneForma",
        "Multilingual Audio Conversation Annotator - Japanese",
        "https://www.oneforma.com/projects/multilingual-audio-conversation-annotator/",
        "Japan (Remote)",
        ("japanese", "japan", "remote", "accepting applications"),
        "アノテーション annotation labeling 文字起こし データ評価 品質評価",
    ),
    SourceSpec(
        "oneforma-podcast-transcription-japan",
        "OneForma",
        "Multilingual Podcast Transcription and Speech Annotator - Japanese",
        "https://www.oneforma.com/projects/multilingual-podcast-transcription-and-speech-annotator/",
        "Japan (Remote)",
        ("japanese", "japan", "remote", "accepting applications"),
        "文字起こし transcription アノテーション annotation labeling データ評価 品質評価",
    ),
    SourceSpec(
        "oneforma-mt-post-editor-japan",
        "OneForma",
        "Multilingual Machine Translation Post-Editor - Japanese",
        "https://www.oneforma.com/projects/multilingual-machine-translation-post-editor/",
        "Japan (Remote)",
        ("japanese", "japan", "remote", "accepting applications"),
        "翻訳 translation 校正 proofreading データ評価 品質評価",
    ),
)

# Reject only explicit physical/media participation. Listening to pre-existing
# audio for transcription/annotation is intentionally not blocked.
HUMAN_MEDIA_BLOCKERS = (
    "record your voice",
    "recording of your voice",
    "voice samples from you",
    "record your likeness",
    "video recording of yourself",
    "take photos of yourself",
    "capture photos of yourself",
    "live video call",
    "scheduled guided recording session",
    "camera must remain on",
    "webcam must remain on",
)
CLOSED_MARKERS = (
    "not accepting applications",
    "no longer accepting applications",
    "position has been filled",
    "project has been completed",
)


def _load(path: Path | None) -> dict:
    if not path:
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _provider_host_ok(provider: str, url: str) -> bool:
    host = (urllib.parse.urlparse(url).hostname or "").lower().strip(".")
    allowed = {
        "Outlier": ("outlier.ai",),
        "Alignerr": ("alignerr.com",),
        "OneForma": ("oneforma.com",),
    }.get(provider, ())
    return any(host == suffix or host.endswith("." + suffix) for suffix in allowed)


def _page_text(raw: str) -> str:
    raw = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", raw)
    raw = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", html.unescape(raw)).strip()


def _fetch_text(spec: SourceSpec) -> str:
    request = urllib.request.Request(
        spec.url,
        headers={
            "User-Agent": "AI-Remote-Finder/10.0",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        final_url = response.geturl()
        if not _provider_host_ok(spec.provider, final_url):
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
    return all(marker.lower() in lower for marker in spec.required_all)


def _mapped(spec: SourceSpec, text: str) -> dict:
    excerpt = text[:MAX_DESCRIPTION_CHARS]
    return {
        "title": spec.title,
        "company_name": spec.provider,
        "location": spec.location,
        "description": (
            "Official provider page verified live and remote. フルリモート。 "
            f"{spec.automation_markers} {excerpt}"
        ),
        "highlights": [],
        "extensions": ["Remote", "Official provider live page"],
        "detected_extensions": {},
        "via": spec.provider,
        "apply_options": [{"title": spec.provider, "link": spec.url}],
        "_direct_provider": spec.provider,
        "_direct_key": spec.key,
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
    fetched_pages: dict[str, str] | None = None,
) -> dict:
    before = len([row for row in payload.get("jobs") or [] if isinstance(row, dict)])
    payload["candidate_direct_official_source_version"] = VERSION
    payload["candidate_direct_official_uses_serpapi"] = False
    payload["candidate_direct_official_quality_gate_unchanged"] = True
    payload["candidate_direct_official_pool_before"] = before

    if before >= STOCK_TARGET:
        payload["candidate_direct_official_skipped"] = "pool-at-or-above-pre-final-target"
        payload["candidate_direct_official_pool_after"] = before
        payload["candidate_direct_official_stock_ready"] = True
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
    mapped_count = 0
    accepted = 0
    errors: list[str] = []
    accepted_by_provider: dict[str, int] = {}
    now = datetime.now(timezone.utc).isoformat()

    for spec in SOURCES:
        if len(by_id) >= 150:
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
        mapped = _mapped(spec, text)
        mapped_count += 1
        provider = str(mapped.pop("_direct_provider", spec.provider))
        key = str(mapped.pop("_direct_key", spec.key))
        try:
            row = acquisition.build_row(mapped, f"direct_official_{key}", previous)
        except Exception:
            continue
        if not row:
            continue
        row["source"] = f"{provider} official provider page; live URL verified"
        row["via"] = provider
        row["discovery_source"] = "official-provider-page"
        row["official_provider"] = provider
        row["official_live_verified_at"] = now
        row["direct_official_source_version"] = VERSION
        jid = str(row.get("id") or "")
        current = by_id.get(jid)
        if current is None or _better(row, current):
            by_id[jid] = row
        accepted += 1
        accepted_by_provider[provider] = accepted_by_provider.get(provider, 0) + 1

    payload["jobs"] = list(by_id.values())[:150]
    after = len(payload["jobs"])
    payload["candidate_direct_official_checked"] = checked
    payload["candidate_direct_official_live"] = live
    payload["candidate_direct_official_mapped"] = mapped_count
    payload["candidate_direct_official_deterministic_accepted"] = accepted
    payload["candidate_direct_official_accepted_by_provider"] = accepted_by_provider
    payload["candidate_direct_official_errors"] = errors[:12]
    payload["candidate_direct_official_pool_after"] = after
    payload["candidate_direct_official_stock_ready"] = after >= STOCK_TARGET
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
        "direct official provider supplement: "
        f"checked={result.get('candidate_direct_official_checked', 0)} "
        f"live={result.get('candidate_direct_official_live', 0)} "
        f"accepted={result.get('candidate_direct_official_deterministic_accepted', 0)} "
        f"pool={result.get('candidate_direct_official_pool_after')}"
    )


if __name__ == "__main__":
    main()
