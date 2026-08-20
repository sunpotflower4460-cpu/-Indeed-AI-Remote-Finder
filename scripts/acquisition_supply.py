#!/usr/bin/env python3
"""Production search-supply orchestrator.

The strict publication policy lives in acquisition_remote.py plus the final
quality layer in acquisition_quality.py. This module changes only *where* we
look and the pool-based upper bound on first-page searches as rolling stock grows.

Discovery intentionally uses a broader remote vocabulary (在宅勤務 / 在宅ワーク /
リモートワーク / remote) so good jobs are not lost before scoring. Publication
remains strict: acquisition_quality requires unconditional explicit full-remote
evidence in the listing itself and rejects partial/hybrid or human-attention-heavy work.

The nominal deep ceiling is seven searches per run. Under a normal once-daily
cadence that is at most 217 requests in a 31-day month. The acquisition layer's
remaining-month pacing and provider guards may lower the effective request count
when extra refreshes have consumed allowance; they never increase this pool-based
limit or relax publication quality.

To avoid a nominal daily window landing entirely on niche themes that have no
Indeed apply option, short natural-language anchor searches are interleaved
through the rotating profile list. The anchors deliberately avoid large nested
OR expressions because broad, simple job-search phrases are more robust discovery
inputs. Every nominal seven-profile window contains at least two anchors while
the remaining requests continue to explore narrower task themes. Quantity never
changes the publication threshold.

Pool-based request ceilings before monthly/provider pacing:
- 0..19 candidates: 7 searches/run
- 20..49 candidates: 6 searches/run
- 50..149 candidates: 4 searches/run
- 150+ candidates: 2 searches/run
"""
from __future__ import annotations

import json
import os

import acquisition
import acquisition_quality
import acquisition_remote

DEEP_REQUESTS = 7
MID_REQUESTS = 6
TOPUP_REQUESTS = 4
STEADY_REQUESTS = 2

DISCOVERY_REMOTE_QUERY = (
    '("完全在宅" OR "フルリモート" OR "完全リモート" OR "100%リモート" '
    'OR "100％リモート" OR "在宅勤務" OR "在宅ワーク" OR "リモートワーク" '
    'OR "fully remote" OR "work from home" OR remote)'
)
R = DISCOVERY_REMOTE_QUERY

# Anchors are intentionally short and close to phrases people actually use in
# job search. They are only discovery inputs; every returned row must still pass
# the strict v2 full-remote/automation/autonomy gates before publication.
ANCHOR_QUERY_PROFILES: list[tuple[str, str]] = [
    ("anchor_data_entry", "完全在宅 データ入力"),
    ("anchor_fullhome_entry", "フル在宅 入力業務"),
    ("anchor_annotation", "フルリモート アノテーション"),
    ("anchor_ai_trainer", "完全在宅 AIトレーナー"),
    ("anchor_rater", "フルリモート rater AI評価"),
    ("anchor_language", "完全在宅 翻訳 校正 文字起こし"),
    ("anchor_content_ops", "完全在宅 商品登録 CMS データ更新"),
    ("anchor_research_qa", "フルリモート Webリサーチ データチェック QA"),
]

TASK_QUERY_PROFILES: list[tuple[str, str]] = [
    ("data_entry_basic", f'{R} ("データ入力" OR "入力業務" OR 転記)'),
    ("data_entry_excel", f'{R} (Excel OR スプレッドシート) ("データ入力" OR 転記 OR 集計)'),
    ("csv_ops", f'{R} (CSV OR "データ整形" OR "データ変換")'),
    ("data_cleanup", f'{R} ("データクレンジング" OR "データ整理" OR "データ整形")'),
    ("data_validation", f'{R} ("データ検証" OR "データチェック" OR "重複チェック")'),
    ("deduplication", f'{R} (重複 OR deduplication OR "名寄せ") (データ OR リスト)'),
    ("form_entry", f'{R} ("フォーム入力" OR "システム入力" OR "登録作業")'),
    ("document_digitize", f'{R} ("PDF入力" OR "文書データ化" OR "書類データ化")'),
    ("ocr_validation", f'{R} (OCR OR "文字認識") (確認 OR 校正 OR "データチェック")'),
    ("data_extraction", f'{R} ("データ抽出" OR "情報抽出" OR extraction)'),
    ("invoice_entry", f'{R} ("請求書入力" OR "請求データ" OR "伝票入力")'),
    ("receipt_entry", f'{R} (領収書 OR レシート) (入力 OR データ化 OR チェック)'),
    ("accounting_data", f'{R} ("会計データ" OR "仕訳入力" OR "経費入力")'),
    ("master_data", f'{R} ("マスタデータ" OR "マスター登録" OR "マスタ更新")'),
    ("catalog_data", f'{R} (カタログ OR "商品マスター" OR "商品データ") (登録 OR 更新)'),
    ("product_listing", f'{R} ("商品登録" OR "商品情報登録" OR "出品登録")'),
    ("product_description", f'{R} ("商品説明文" OR "商品説明") (作成 OR 校正 OR 登録)'),
    ("inventory_data", f'{R} ("在庫情報" OR "在庫データ") (更新 OR 入力 OR チェック)'),
    ("taxonomy", f'{R} ("カテゴリー設定" OR taxonomy OR "商品分類")'),
    ("ecommerce_qa", f'{R} (EC OR ecommerce OR Shopify) ("商品データ" OR "品質チェック" OR 登録)'),
    ("cms_entry", f'{R} (CMS OR WordPress) ("記事登録" OR 入稿 OR "ページ更新")'),
    ("content_upload", f'{R} ("コンテンツ入稿" OR "記事入稿" OR "原稿入稿")'),
    ("article_registration", f'{R} ("記事登録" OR "記事更新" OR "コンテンツ登録")'),
    ("metadata_tagging", f'{R} (メタデータ OR metadata OR "タグ付け")'),
    ("content_tagging", f'{R} ("コンテンツ分類" OR "タグ設定" OR "ラベル付け")'),
    ("document_classification", f'{R} ("文書分類" OR "書類分類" OR "ドキュメント分類")'),
    ("document_check", f'{R} ("書類チェック" OR "文書チェック" OR "記載内容確認")'),
    ("file_organization", f'{R} ("ファイル整理" OR "資料整理" OR "文書整理")'),
    ("transcription", f'{R} ("文字起こし" OR transcription OR "音声文字化")'),
    ("transcription_qa", f'{R} ("文字起こし") (校正 OR チェック OR 品質)'),
    ("subtitle_caption", f'{R} (字幕 OR caption OR "テロップ文字") (作成 OR 校正 OR チェック)'),
    ("proofreading", f'{R} (校正 OR proofreading OR "誤字脱字")'),
    ("text_review", f'{R} ("文章チェック" OR "原稿チェック" OR "テキストレビュー")'),
    ("translation", f'{R} (翻訳 OR translation) (テキスト OR 文書 OR コンテンツ)'),
    ("translation_review", f'{R} (翻訳) (レビュー OR 校正 OR チェック)'),
    ("localization_qa", f'{R} (localization OR ローカライズ OR LQA OR "言語QA")'),
    ("japanese_quality", f'{R} ("日本語評価" OR "日本語チェック" OR "日本語品質")'),
    ("language_evaluation", f'{R} ("言語評価" OR "文章評価" OR "応答評価")'),
    ("ai_annotation", f'{R} (アノテーション OR annotation OR labeling)'),
    ("text_annotation", f'{R} ("テキストアノテーション" OR "文章アノテーション" OR "テキスト分類")'),
    ("image_annotation", f'{R} ("画像アノテーション" OR "画像タグ" OR "画像分類")'),
    ("audio_annotation", f'{R} ("音声アノテーション" OR "音声分類" OR "音声ラベル")'),
    ("data_labeling", f'{R} ("データラベリング" OR "データラベル" OR labeling)'),
    ("ai_rater", f'{R} (rater OR "AI評価" OR "AIトレーナー")'),
    ("model_response_eval", f'{R} ("AI応答評価" OR "モデル評価" OR "回答評価")'),
    ("prompt_eval", f'{R} ("プロンプト評価" OR "生成AI評価" OR "AI品質評価")'),
    ("search_evaluator", f'{R} ("検索評価" OR "検索品質" OR "検索意図")'),
    ("search_relevance", f'{R} ("検索関連性" OR relevance OR "検索結果評価")'),
    ("internet_assessor", f'{R} ("インターネット評価" OR assessor OR "Web評価")'),
    ("ads_quality", f'{R} ("広告評価" OR "広告品質" OR ads rater)'),
    ("map_data", f'{R} ("地図データ" OR map data OR "位置情報データ") (評価 OR チェック OR 更新)'),
    ("content_qa", f'{R} ("コンテンツレビュー" OR "品質チェック" OR "品質評価")'),
    ("dataset_qa", f'{R} (dataset OR データセット) (QA OR 品質 OR チェック)'),
    ("fact_check", f'{R} ("ファクトチェック" OR fact-check OR "事実確認")'),
    ("web_research", f'{R} ("Webリサーチ" OR "ウェブリサーチ" OR "情報収集")'),
    ("market_research", f'{R} ("市場調査" OR "競合調査" OR "市場リサーチ")'),
    ("company_research", f'{R} ("企業調査" OR "企業リサーチ" OR "会社情報収集")'),
    ("list_building", f'{R} ("リスト作成" OR "一覧作成" OR "データ収集")'),
    ("data_enrichment", f'{R} ("データ補完" OR "データエンリッチ" OR enrichment)'),
    ("survey_data", f'{R} (アンケート OR survey) (集計 OR 入力 OR 分類)'),
    ("questionnaire_coding", f'{R} ("自由回答" OR "アンケート回答") (分類 OR コーディング OR 集計)'),
    ("software_testing", f'{R} ("動作確認" OR "ソフトウェアテスト" OR "テスト実行")'),
    ("app_testing", f'{R} ("アプリテスト" OR "アプリ動作確認" OR "検証作業")'),
    ("web_testing", f'{R} ("Webサイトテスト" OR "サイト動作確認" OR "表示チェック")'),
    ("data_migration_qa", f'{R} ("データ移行" OR migration) (検証 OR チェック OR 照合)'),
    ("record_matching", f'{R} (照合 OR matching OR "突合") (データ OR リスト OR 書類)'),
    ("content_moderation", f'{R} (moderation OR モデレーション) (分類 OR 判定 OR レビュー)'),
    ("image_review", f'{R} ("画像チェック" OR "画像レビュー" OR "画像品質")'),
    ("text_normalization", f'{R} ("テキスト整形" OR "表記統一" OR normalization)'),
    ("spreadsheet_aggregation", f'{R} (集計 OR "データ集計") (Excel OR スプレッドシート OR CSV)'),
    ("database_entry", f'{R} ("データベース入力" OR "DB入力" OR "データ登録")'),
    ("backoffice_data", f'{R} (バックオフィス OR 事務) ("データ入力" OR "書類チェック" OR 集計)'),
]


def interleave_anchor_profiles(tasks: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Ensure every short rotation window gets broad recall plus niche novelty."""
    combined: list[tuple[str, str]] = []
    anchor_index = 0
    for offset in range(0, len(tasks), 2):
        combined.extend(tasks[offset: offset + 2])
        anchor_name, anchor_query = ANCHOR_QUERY_PROFILES[
            anchor_index % len(ANCHOR_QUERY_PROFILES)
        ]
        combined.append((f"{anchor_name}_{anchor_index:02d}", anchor_query))
        anchor_index += 1
    return combined


PRODUCTION_QUERY_PROFILES = interleave_anchor_profiles(TASK_QUERY_PROFILES)


def supply_request_limit(pool_size: int) -> int:
    if pool_size < 20:
        return DEEP_REQUESTS
    if pool_size < 50:
        return MID_REQUESTS
    if pool_size < acquisition_remote.SERVER_POOL_TARGET:
        return TOPUP_REQUESTS
    return STEADY_REQUESTS


def configure_supply_rotation() -> None:
    acquisition_quality.configure_quality_policy()
    acquisition.QUERY_PROFILES = list(PRODUCTION_QUERY_PROFILES)
    acquisition.MAX_REQUESTS_PER_RUN = DEEP_REQUESTS
    acquisition.request_limit_for_pool = supply_request_limit


def stamp_supply_metadata() -> None:
    try:
        payload = acquisition.load_payload()
        if not payload:
            return
        payload["candidate_search_strategy"] = "simple-anchor-rotation-strict-full-remote-v2"
        payload["candidate_search_profile_count"] = len(PRODUCTION_QUERY_PROFILES)
        payload["candidate_search_anchor_templates"] = len(ANCHOR_QUERY_PROFILES)
        payload["candidate_search_daily_deep_limit"] = DEEP_REQUESTS
        payload["candidate_search_pagination_expected"] = False
        payload["candidate_search_budget_monthly_safe_at_31_days"] = DEEP_REQUESTS * 31 <= 220
        acquisition.OUT.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


def main() -> None:
    configure_supply_rotation()
    api_key = os.environ.get("SERPAPI_KEY", "").strip()
    if not api_key:
        print("SERPAPI_KEY is not configured; preserving the last known-good feed.")
        return
    provider_cap = acquisition_remote.configure_provider_budget(api_key)
    if provider_cap == 0:
        print("SerpApi provider usage guard has no safe request headroom; preserving last known-good feed.")
        return
    acquisition.main()
    acquisition_remote.stamp_policy_metadata()
    acquisition_quality.stamp_quality_metadata()
    stamp_supply_metadata()


if __name__ == "__main__":
    main()
