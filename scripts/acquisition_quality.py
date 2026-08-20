#!/usr/bin/env python3
"""Production-quality gates for AI-substitutable remote jobs.

Discovery is intentionally broader than publication. Search queries may use
ordinary 在宅/リモート wording to improve recall, but a published candidate must
still prove full remote in the listing text itself and pass the autonomous-work
quality gates below.

Rules:
1. Explicit, conditional, partial, or hybrid arrangements are rejected.
2. Jobs that imply ongoing human coordination/attention are rejected.
3. Explicit human-attendance requirements are checked against the full listing
   text before any UI/LLM excerpt truncation.
4. REVIEW rows must clear an automation floor, a human-risk ceiling, and at
   least two concrete automation signals.
5. Equivalent async tasks (OCR verification, extraction, metadata tagging,
   AI-response rating, etc.) are mapped to scorer vocabulary to avoid false
   negatives without padding the pool with weak work.
6. Google's deprecated Work From Home filter never contributes to scoring.
7. A richer listing excerpt is retained for LLM review while the UI still
   visually clamps the card text.
8. Safe aggregate rejection telemetry records which gate rejects candidates,
   without persisting titles, companies, descriptions, URLs, or secrets.
"""
from __future__ import annotations

from collections import Counter
import json
import re

import acquisition
import acquisition_remote
import apply_llm_quality_gate

QUALITY_POLICY_VERSION = 2
QUALITY_GATE = "async-ai-remote-v2"
QUALITY_TELEMETRY_VERSION = 1
REVIEW_AUTOMATION_MIN = 64
REVIEW_HUMAN_RISK_MAX = 18
REVIEW_AUTOMATION_SIGNAL_MIN = 2
RICH_SNIPPET_MAX = 6000

# Capture generic primitives before acquisition_remote installs provider-filter
# wrappers. We keep its autonomy and budget protections, but scoring/publication
# never trusts provider WFH classification as proof of full remote.
GENERIC_SCORE_JOB = acquisition.legacy.score_job
GENERIC_SERPAPI_FETCH = acquisition.serpapi_fetch

_QUALITY_REJECTION_COUNTS: Counter[str] = Counter()
_QUALITY_PROFILE_EVALUATED: Counter[str] = Counter()
_QUALITY_PROFILE_ACCEPTED: Counter[str] = Counter()
_QUALITY_PROFILE_REJECTIONS: dict[str, Counter[str]] = {}
_QUALITY_EVALUATED = 0
_QUALITY_ACCEPTED = 0

AUTOMATION_EQUIVALENTS: tuple[tuple[str, str], ...] = (
    ("データ抽出", "データ入力 転記"),
    ("情報抽出", "データ入力 転記"),
    ("データクレンジング", "データ整理 データチェック"),
    ("データ整形", "データ整理 データチェック"),
    ("データ検証", "データチェック データ整理"),
    ("重複チェック", "データチェック データ整理"),
    ("名寄せ", "データチェック データ整理"),
    ("突合", "データチェック データ整理"),
    ("照合", "データチェック データ整理"),
    ("ocr", "文字起こし データ入力"),
    ("文字認識", "文字起こし データ入力"),
    ("メタデータ", "タグ付け データ整理"),
    ("ラベル付け", "タグ付け 分類"),
    ("マスタデータ", "データ整理 データチェック"),
    ("マスター登録", "データ整理 入力業務"),
    ("マスタ更新", "データ整理 データチェック"),
    ("商品マスター", "商品登録 データ整理"),
    ("記事登録", "入力業務 データ整理"),
    ("記事入稿", "入力業務 データ整理"),
    ("コンテンツ入稿", "入力業務 データ整理"),
    ("pdf入力", "データ入力 転記"),
    ("文書分類", "分類 タグ付け"),
    ("書類分類", "分類 タグ付け"),
    ("書類チェック", "データチェック 分類"),
    ("表記統一", "校正 データチェック"),
    ("字幕", "文字起こし 校正"),
    ("テロップ", "文字起こし 校正"),
    ("ai応答評価", "ai評価 データ評価"),
    ("モデル評価", "ai評価 データ評価"),
    ("回答評価", "ai評価 データ評価"),
    ("プロンプト評価", "ai評価 データ評価"),
    ("生成ai評価", "ai評価 データ評価"),
    ("検索評価", "ai評価 データ評価"),
    ("検索関連性", "ai評価 データ評価"),
    ("検索結果評価", "ai評価 データ評価"),
    ("広告評価", "ai評価 データ評価"),
    ("画像チェック", "データチェック タグ付け"),
    ("画像レビュー", "データチェック タグ付け"),
    ("データベース入力", "データ入力 転記"),
    ("db入力", "データ入力 転記"),
    ("アプリテスト", "品質チェック データチェック"),
    ("ソフトウェアテスト", "品質チェック データチェック"),
    ("動作確認", "品質チェック データチェック"),
)

# These phrases mean the role is not guaranteed to be zero-office. This is
# intentionally conservative: a role can re-enter if a fresh listing clearly
# states an unconditional full-remote arrangement.
PARTIAL_REMOTE_PHRASES = (
    "一部在宅", "一部リモート", "ハイブリッド勤務", "ハイブリッドワーク",
    "在宅あり", "リモートあり", "出社あり", "出社併用", "在宅併用",
    "リモート併用", "テレワーク併用", "慣れたら在宅", "慣れたらリモート",
    "慣れてから在宅", "慣れてからリモート", "原則在宅", "基本在宅",
    "原則リモート", "基本リモート", "原則フルリモート", "基本フルリモート",
    "ほぼフルリモート", "フルリモート応相談", "完全在宅応相談",
    "フルリモート相談可", "完全在宅相談可", "必要に応じて出社",
    "必要に応じ出社", "場合により出社", "場合によって出社",
    "研修期間は出社", "研修中は出社", "初日のみ出社", "初日は出社",
    "将来的にフルリモート", "将来的に完全在宅",
)

REMOTE_NEGATIONS = (
    "ハイブリッド勤務は不可", "ハイブリッド勤務不可", "ハイブリッド不可",
    "一部在宅ではありません", "一部リモートではありません",
    "出社併用なし", "出社併用不要", "出社の可能性なし",
)

REMOTE_PARTIAL_PATTERNS = (
    re.compile(r"(?:在宅(?:勤務|ワーク)?|リモート(?:勤務|ワーク)?|テレワーク)\s*週\s*[1-6１-６一二三四五六]\s*(?:[～〜~\-－ー]\s*[1-6１-６一二三四五六])?\s*日", re.I),
    re.compile(r"週\s*[1-6１-６一二三四五六]\s*(?:[～〜~\-－ー]\s*[1-6１-６一二三四五六])?\s*日\s*(?:程度\s*)?(?:の)?\s*(?:在宅|リモート|テレワーク)", re.I),
    re.compile(r"(?:在宅|リモート|テレワーク)\s*(?:勤務)?\s*月\s*[1-9１-９]\s*回", re.I),
    re.compile(r"月\s*[1-9１-９]\s*回\s*(?:程度\s*)?(?:の)?\s*(?:在宅|リモート|テレワーク)", re.I),
    re.compile(r"(?:週|月)\s*[1-9１-９]\s*回(?:程度)?\s*(?:の)?\s*出社", re.I),
    re.compile(r"出社\s*(?:は)?\s*(?:週|月)\s*[1-9１-９]\s*回", re.I),
    re.compile(r"(?:研修|オンボーディング)[^。\n]{0,30}出社", re.I),
)

QUALITY_ATTENTION_BLOCKERS = (
    "調整業務", "連絡調整", "関係者との調整", "社内外関係者との調整",
    "関係部門との調整", "進捗管理", "進捗確認", "顧客とのやり取り",
    "クライアントとのやり取り", "関係者とのやり取り", "顧客窓口",
    "問い合わせ窓口", "エスカレーション対応", "ファシリテーション",
)
QUALITY_ATTENTION_NEGATIONS = (
    "調整業務なし", "調整業務不要", "連絡調整なし", "連絡調整不要",
    "進捗管理なし", "進捗管理不要", "顧客対応なし", "顧客対応不要",
)


def reset_quality_telemetry() -> None:
    global _QUALITY_EVALUATED, _QUALITY_ACCEPTED
    _QUALITY_REJECTION_COUNTS.clear()
    _QUALITY_PROFILE_EVALUATED.clear()
    _QUALITY_PROFILE_ACCEPTED.clear()
    _QUALITY_PROFILE_REJECTIONS.clear()
    _QUALITY_EVALUATED = 0
    _QUALITY_ACCEPTED = 0


def _profile_name(category: object) -> str:
    return str(category or "unknown")[:80]


def _record_quality_outcome(category: object, reason: str | None) -> None:
    global _QUALITY_EVALUATED, _QUALITY_ACCEPTED
    profile = _profile_name(category)
    _QUALITY_EVALUATED += 1
    _QUALITY_PROFILE_EVALUATED[profile] += 1
    if reason is None:
        _QUALITY_ACCEPTED += 1
        _QUALITY_PROFILE_ACCEPTED[profile] += 1
        return
    _QUALITY_REJECTION_COUNTS[reason] += 1
    _QUALITY_PROFILE_REJECTIONS.setdefault(profile, Counter())[reason] += 1


def quality_telemetry_snapshot() -> dict:
    profiles = []
    for profile, evaluated in _QUALITY_PROFILE_EVALUATED.items():
        accepted = int(_QUALITY_PROFILE_ACCEPTED.get(profile, 0))
        reasons = _QUALITY_PROFILE_REJECTIONS.get(profile, Counter())
        profiles.append(
            {
                "profile": profile,
                "evaluated": int(evaluated),
                "accepted": accepted,
                "rejected": int(evaluated) - accepted,
                "reasons": dict(reasons.most_common(6)),
            }
        )
    profiles.sort(
        key=lambda item: (
            -int(item["accepted"]),
            -int(item["evaluated"]),
            str(item["profile"]),
        )
    )
    return {
        "candidate_quality_gate_telemetry_version": QUALITY_TELEMETRY_VERSION,
        "candidate_quality_evaluated_jobs": _QUALITY_EVALUATED,
        "candidate_quality_pre_llm_accepted": _QUALITY_ACCEPTED,
        "candidate_quality_rejected_jobs": max(0, _QUALITY_EVALUATED - _QUALITY_ACCEPTED),
        "candidate_quality_rejection_counts": dict(_QUALITY_REJECTION_COUNTS.most_common()),
        "candidate_quality_rejection_by_profile": profiles[:12],
    }


def normalized_job_text(job: dict) -> str:
    return acquisition_remote.job_text(job)


def partial_remote_blockers(job: dict) -> list[str]:
    text = normalized_job_text(job)
    for phrase in acquisition.legacy.NEGATED_RISK_PHRASES:
        text = text.replace(phrase.lower(), " ")
    for phrase in REMOTE_NEGATIONS:
        text = text.replace(phrase.lower(), " ")
    found = [phrase for phrase in PARTIAL_REMOTE_PHRASES if phrase.lower() in text]
    for pattern in REMOTE_PARTIAL_PATTERNS:
        match = pattern.search(text)
        if match:
            found.append(match.group(0))
    return list(dict.fromkeys(found))[:8]


def quality_attention_blockers(job: dict) -> list[str]:
    text = normalized_job_text(job)
    for phrase in QUALITY_ATTENTION_NEGATIONS:
        text = text.replace(phrase.lower(), " ")
    return [phrase for phrase in QUALITY_ATTENTION_BLOCKERS if phrase.lower() in text][:8]


def human_presence_blocker(job: dict) -> str | None:
    """Check human-attendance requirements against the full structured listing."""
    return apply_llm_quality_gate.presence_requirement_signal(
        {"snippet": normalized_job_text(job)}
    )


def explicit_full_remote_evidence(job: dict) -> bool:
    text = normalized_job_text(job)
    return any(phrase.lower() in text for phrase in acquisition.legacy.REMOTE_EXPLICIT_FULL)


def augment_automation_text(text: str) -> str:
    lower = text.lower()
    additions: list[str] = []
    for phrase, equivalents in AUTOMATION_EQUIVALENTS:
        if phrase.lower() in lower:
            additions.append(equivalents)
    return f"{text} {' '.join(additions)}" if additions else text


def rich_listing_excerpt(job: dict) -> str:
    if not isinstance(job, dict):
        return ""
    description = acquisition.legacy.clean(str(job.get("description") or ""))
    highlights = acquisition.legacy.flatten_highlights(job)
    parts = [part for part in (description, highlights) if part]
    text = " ".join(parts).strip()
    if len(text) > RICH_SNIPPET_MAX:
        text = text[: RICH_SNIPPET_MAX - 3].rstrip() + "..."
    return text


def review_row_quality_rejection(row: dict) -> str | None:
    if int(row.get("automation_confidence") or 0) < REVIEW_AUTOMATION_MIN:
        return "review-automation-below-floor"
    if int(row.get("human_dependency_risk") or 0) > REVIEW_HUMAN_RISK_MAX:
        return "review-human-risk-above-ceiling"
    reasons = {
        str(value or "").strip().lower()
        for value in row.get("automation_reasons") or []
        if str(value or "").strip()
    }
    if len(reasons) < REVIEW_AUTOMATION_SIGNAL_MIN:
        return "review-insufficient-automation-signals"
    return None


def review_row_meets_quality(row: dict) -> bool:
    return review_row_quality_rejection(row) is None


def prefilter_rejection_reason(job: dict) -> str | None:
    # Track the acquisition funnel in the same order users care about it:
    # first there must be an Indeed destination, then the work must satisfy the
    # strict remote/autonomy policy. Only coarse reason labels are persisted.
    if not acquisition.legacy.find_indeed_apply(job):
        return "no-indeed-apply"
    if acquisition_remote.autonomy_blockers(job):
        return "synchronous-human-attention"
    if partial_remote_blockers(job):
        return "partial-or-conditional-remote"
    if quality_attention_blockers(job):
        return "ongoing-human-coordination"
    if human_presence_blocker(job):
        return "continuous-human-presence"
    if not explicit_full_remote_evidence(job):
        return "missing-explicit-full-remote"
    return None


def quality_serpapi_fetch(query: str, api_key: str, next_page_token: str | None = None) -> dict:
    """Use generic Google Jobs search and treat benign no-results as empty success."""
    payload = GENERIC_SERPAPI_FETCH(query, api_key, next_page_token=next_page_token)
    if not isinstance(payload, dict):
        raise RuntimeError("SerpApi response is not an object")
    try:
        acquisition_remote.raise_classified_provider_error(payload)
    except acquisition_remote.SerpApiNoResultsError:
        return {"jobs_results": [], "serpapi_pagination": {}}
    return payload


def configure_quality_policy() -> None:
    if getattr(acquisition, "_production_quality_policy_configured", False):
        return
    acquisition._production_quality_policy_configured = True
    acquisition_remote.configure_production_policy()

    # Broaden discovery, not publication. No ltype is used and WFH provider
    # classification never contributes to the remote score.
    acquisition.serpapi_fetch = quality_serpapi_fetch

    def quality_score_job(text, published, previous, *, remote_api_filter=False):
        return GENERIC_SCORE_JOB(
            augment_automation_text(text), published, previous, remote_api_filter=False
        )

    acquisition.legacy.score_job = quality_score_job
    base_build_row = acquisition.build_row

    def quality_build_row(job, category, previous):
        reason = prefilter_rejection_reason(job)
        if reason:
            _record_quality_outcome(category, reason)
            return None

        row = base_build_row(job, category, previous)
        if not row:
            _record_quality_outcome(category, "score-below-candidate-floor")
            return None
        # Redundant with explicit_full_remote_evidence, but retain the legacy
        # marker as a defense against future build_row changes.
        if row.get("remote_search_only") is True:
            _record_quality_outcome(category, "remote-search-only")
            return None
        if row.get("tier") == "review":
            reason = review_row_quality_rejection(row)
            if reason:
                _record_quality_outcome(category, reason)
                return None

        richer = rich_listing_excerpt(job)
        if richer:
            row["snippet"] = richer
            row["quality_listing_chars"] = len(richer)
        row["quality_policy_version"] = QUALITY_POLICY_VERSION
        row["quality_gate"] = QUALITY_GATE
        row["full_listing_presence_screened"] = True
        _record_quality_outcome(category, None)
        return row

    acquisition.build_row = quality_build_row


def stamp_quality_metadata() -> None:
    try:
        payload = acquisition.load_payload()
        if not payload:
            return
        payload["candidate_quality_policy_version"] = QUALITY_POLICY_VERSION
        payload["candidate_quality_gate"] = QUALITY_GATE
        payload["candidate_review_automation_min"] = REVIEW_AUTOMATION_MIN
        payload["candidate_review_human_risk_max"] = REVIEW_HUMAN_RISK_MAX
        payload["candidate_review_automation_signal_min"] = REVIEW_AUTOMATION_SIGNAL_MIN
        payload["candidate_requires_explicit_full_remote"] = True
        payload["candidate_provider_wfh_filter_used"] = False
        payload["candidate_discovery_can_use_broad_remote_terms"] = True
        payload["candidate_rich_listing_excerpt_max"] = RICH_SNIPPET_MAX
        payload["candidate_full_listing_presence_screened"] = True
        payload.update(quality_telemetry_snapshot())
        acquisition.OUT.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass
