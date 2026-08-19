#!/usr/bin/env python3
"""Additional production-quality gates for AI-substitutable remote jobs.

This module deliberately does not relax the generic scorer. It layers three
production rules on top of acquisition_remote:

1. Explicit partial/hybrid arrangements are rejected, even if Google Jobs put
   the listing in a Work From Home result set.
2. REVIEW rows must still clear a meaningful automation floor and a stricter
   human-dependency ceiling; the pool is never padded with weak work.
3. A small vocabulary bridge maps clearly equivalent asynchronous tasks such as
   OCR verification, data extraction, metadata tagging, and AI-response rating
   to automation signals the legacy scorer already understands. This fixes
   under-scoring without making vague office work look automatable.
"""
from __future__ import annotations

import re

import acquisition
import acquisition_remote

QUALITY_POLICY_VERSION = 1
REVIEW_AUTOMATION_MIN = 55
REVIEW_HUMAN_RISK_MAX = 25

# Actual task phrase -> semantically equivalent scorer vocabulary. These are
# only used to calculate the automation score; the original job text remains
# unchanged in the published feed.
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


def augment_automation_text(text: str) -> str:
    lower = text.lower()
    additions: list[str] = []
    for phrase, equivalents in AUTOMATION_EQUIVALENTS:
        if phrase.lower() in lower:
            additions.append(equivalents)
    if not additions:
        return text
    return f"{text} {' '.join(additions)}"


def configure_quality_policy() -> None:
    if getattr(acquisition, "_production_quality_policy_configured", False):
        return
    acquisition._production_quality_policy_configured = True

    acquisition_remote.configure_production_policy()

    base_score_job = acquisition.legacy.score_job

    def quality_score_job(text, published, previous, *, remote_api_filter=False):
        return base_score_job(
            augment_automation_text(text),
            published,
            previous,
            remote_api_filter=remote_api_filter,
        )

    acquisition.legacy.score_job = quality_score_job

    base_build_row = acquisition.build_row

    def quality_build_row(job, category, previous):
        if partial_remote_blockers(job):
            return None

        row = base_build_row(job, category, previous)
        if not row:
            return None

        if row.get("tier") == "review":
            if int(row.get("automation_confidence") or 0) < REVIEW_AUTOMATION_MIN:
                return None
            if int(row.get("human_dependency_risk") or 0) > REVIEW_HUMAN_RISK_MAX:
                return None

        row["quality_policy_version"] = QUALITY_POLICY_VERSION
        row["quality_gate"] = "async-ai-remote"
        return row

    acquisition.build_row = quality_build_row


def stamp_quality_metadata() -> None:
    try:
        payload = acquisition.load_payload()
        if not payload:
            return
        payload["candidate_quality_policy_version"] = QUALITY_POLICY_VERSION
        payload["candidate_review_automation_min"] = REVIEW_AUTOMATION_MIN
        payload["candidate_review_human_risk_max"] = REVIEW_HUMAN_RISK_MAX
        acquisition.OUT.write_text(
            __import__("json").dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass
