#!/usr/bin/env python3
"""Additional production-quality gates for AI-substitutable remote jobs.

This module deliberately does not relax the generic scorer. It layers four
production rules on top of acquisition_remote:

1. Explicit partial/hybrid arrangements are rejected.
2. Jobs that still imply ongoing human coordination/attention are rejected.
3. REVIEW rows must clear a meaningful automation floor and human-risk ceiling.
4. Clearly equivalent async tasks (OCR verification, data extraction, metadata
   tagging, AI-response rating, etc.) are mapped to scorer vocabulary so good
   automation candidates are not missed merely because of wording differences.

Production also stops relying on Google's deprecated Work From Home filter for
quality scoring. Search queries themselves target explicit full-remote wording,
and the published job text must independently prove full remote.
"""
from __future__ import annotations

import json
import re

import acquisition
import acquisition_remote

QUALITY_POLICY_VERSION = 1
QUALITY_GATE = "async-ai-remote"
REVIEW_AUTOMATION_MIN = 55
REVIEW_HUMAN_RISK_MAX = 25

# Capture the generic primitives before acquisition_remote installs its legacy
# Work-From-Home-filter wrappers. Production quality reuses the provider budget
# and autonomy gates from acquisition_remote, but deliberately restores these
# two generic primitives so ltype/remote_api_filter cannot make a hybrid job look
# more remote than the actual job text proves.
GENERIC_SCORE_JOB = acquisition.legacy.score_job
GENERIC_SERPAPI_FETCH = acquisition.serpapi_fetch

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

PARTIAL_REMOTE_PHRASES = (
    "一部在宅",
    "一部リモート",
    "ハイブリッド勤務",
    "ハイブリッドワーク",
    "在宅あり",
    "リモートあり",
    "出社あり",
    "出社併用",
    "在宅併用",
    "リモート併用",
    "テレワーク併用",
    "慣れたら在宅",
    "慣れたらリモート",
    "慣れてから在宅",
    "慣れてからリモート",
)

REMOTE_NEGATIONS = (
    "ハイブリッド勤務は不可",
    "ハイブリッド勤務不可",
    "ハイブリッド不可",
    "一部在宅ではありません",
    "一部リモートではありません",
    "出社併用なし",
    "出社併用不要",
)

REMOTE_WEEKLY_PATTERNS = (
    re.compile(r"(?:在宅(?:勤務|ワーク)?|リモート(?:勤務|ワーク)?|テレワーク)\s*週\s*[1-6１-６一二三四五六]\s*(?:[～〜~\-－ー]\s*[1-6１-６一二三四五六])?\s*日", re.I),
    re.compile(r"週\s*[1-6１-６一二三四五六]\s*(?:[～〜~\-－ー]\s*[1-6１-６一二三四五六])?\s*日\s*(?:程度\s*)?(?:の)?\s*(?:在宅|リモート|テレワーク)", re.I),
    re.compile(r"(?:在宅|リモート|テレワーク)\s*(?:勤務)?\s*月\s*[1-9１-９]\s*回", re.I),
    re.compile(r"月\s*[1-9１-９]\s*回\s*(?:程度\s*)?(?:の)?\s*(?:在宅|リモート|テレワーク)", re.I),
)

# These are not necessarily real-time in every company, but they strongly imply
# that the core value of the role is human coordination rather than an async
# digital work product. Keep them out of the autonomous queue.
QUALITY_ATTENTION_BLOCKERS = (
    "調整業務",
    "連絡調整",
    "関係者との調整",
    "社内外関係者との調整",
    "関係部門との調整",
    "進捗管理",
    "進捗確認",
    "顧客とのやり取り",
    "クライアントとのやり取り",
    "関係者とのやり取り",
)

QUALITY_ATTENTION_NEGATIONS = (
    "調整業務なし",
    "調整業務不要",
    "連絡調整なし",
    "連絡調整不要",
    "進捗管理なし",
    "進捗管理不要",
)


def normalized_job_text(job: dict) -> str:
    return acquisition_remote.job_text(job)


def partial_remote_blockers(job: dict) -> list[str]:
    text = normalized_job_text(job)
    for phrase in acquisition.legacy.NEGATED_RISK_PHRASES:
        text = text.replace(phrase.lower(), " ")
    for phrase in REMOTE_NEGATIONS:
        text = text.replace(phrase.lower(), " ")

    found = [phrase for phrase in PARTIAL_REMOTE_PHRASES if phrase.lower() in text]
    for pattern in REMOTE_WEEKLY_PATTERNS:
        match = pattern.search(text)
        if match:
            found.append(match.group(0))
    return found[:6]


def quality_attention_blockers(job: dict) -> list[str]:
    text = normalized_job_text(job)
    for phrase in QUALITY_ATTENTION_NEGATIONS:
        text = text.replace(phrase.lower(), " ")
    return [phrase for phrase in QUALITY_ATTENTION_BLOCKERS if phrase.lower() in text][:6]


def augment_automation_text(text: str) -> str:
    lower = text.lower()
    additions: list[str] = []
    for phrase, equivalents in AUTOMATION_EQUIVALENTS:
        if phrase.lower() in lower:
            additions.append(equivalents)
    if not additions:
        return text
    return f"{text} {' '.join(additions)}"


def review_row_meets_quality(row: dict) -> bool:
    return bool(
        int(row.get("automation_confidence") or 0) >= REVIEW_AUTOMATION_MIN
        and int(row.get("human_dependency_risk") or 0) <= REVIEW_HUMAN_RISK_MAX
    )


def configure_quality_policy() -> None:
    if getattr(acquisition, "_production_quality_policy_configured", False):
        return
    acquisition._production_quality_policy_configured = True

    acquisition_remote.configure_production_policy()

    # Restore generic provider/search semantics after installing the remote
    # module's autonomy and budget protections. Production queries themselves
    # request explicit full remote, and the job text must prove it independently.
    acquisition.serpapi_fetch = GENERIC_SERPAPI_FETCH

    def quality_score_job(text, published, previous, *, remote_api_filter=False):
        return GENERIC_SCORE_JOB(
            augment_automation_text(text),
            published,
            previous,
            remote_api_filter=False,
        )

    acquisition.legacy.score_job = quality_score_job
    base_build_row = acquisition.build_row

    def quality_build_row(job, category, previous):
        if partial_remote_blockers(job) or quality_attention_blockers(job):
            return None

        row = base_build_row(job, category, previous)
        if not row:
            return None

        # REVIEW rows that only inherited a provider/search hint are not good
        # enough for this product. Require the listing text itself to prove full
        # remote; HIGH already has the same explicit evidence requirement.
        if row.get("remote_search_only") is True:
            return None

        if row.get("tier") == "review" and not review_row_meets_quality(row):
            return None

        row["quality_policy_version"] = QUALITY_POLICY_VERSION
        row["quality_gate"] = QUALITY_GATE
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
        payload["candidate_requires_explicit_full_remote"] = True
        payload["candidate_provider_wfh_filter_used"] = False
        acquisition.OUT.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass
