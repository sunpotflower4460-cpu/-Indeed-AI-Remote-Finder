#!/usr/bin/env python3
"""Production search-supply orchestrator.

The strict publication policy lives in acquisition_remote.py. This module only
changes *where* we look so quality is not relaxed to reach the stock target.

Instead of repeatedly querying the same small set and spending requests on page
2 (which Google Jobs often reports as exhausted), we rotate many narrowly
focused, asynchronous/AI-friendly first-page queries. The request budget shrinks
as the rolling pool grows:

- 0..19 candidates: 15 searches/run
- 20..49 candidates: 10 searches/run
- 50..99 candidates: 6 searches/run
- 100 candidates: 2 searches/run

The daily workflow plus 14-day carryover can therefore accumulate diverse valid
jobs while preserving SerpApi monthly/hourly guards.
"""
from __future__ import annotations

import json
import os

import acquisition
import acquisition_remote

DEEP_REQUESTS = 15
MID_REQUESTS = 10
TOPUP_REQUESTS = 6
STEADY_REQUESTS = 2

R = acquisition.REMOTE_QUERY

# Deliberately task-oriented rather than role-title-oriented. These searches aim
# at work that can often be completed asynchronously by an automated pipeline.
# Synchronous/contact-heavy rows are still rejected later by acquisition_remote.
PRODUCTION_QUERY_PROFILES: list[tuple[str, str]] = [
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


def supply_request_limit(pool_size: int) -> int:
    if pool_size < 20:
        return DEEP_REQUESTS
    if pool_size < 50:
        return MID_REQUESTS
    if pool_size < acquisition_remote.SERVER_POOL_TARGET:
        return TOPUP_REQUESTS
    return STEADY_REQUESTS


def configure_supply_rotation() -> None:
    # First install all strict remote/autonomy gates.
    acquisition_remote.configure_production_policy()

    # Then replace only the discovery surface and request cadence. The strict
    # build_row/review policy above remains authoritative.
    acquisition.QUERY_PROFILES = list(PRODUCTION_QUERY_PROFILES)
    acquisition.MAX_REQUESTS_PER_RUN = DEEP_REQUESTS
    acquisition.request_limit_for_pool = supply_request_limit


def stamp_supply_metadata() -> None:
    try:
        payload = acquisition.load_payload()
        if not payload:
            return
        payload["candidate_search_strategy"] = "rotating-async-first-pages"
        payload["candidate_search_profile_count"] = len(PRODUCTION_QUERY_PROFILES)
        payload["candidate_search_daily_deep_limit"] = DEEP_REQUESTS
        payload["candidate_search_pagination_expected"] = False
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
        print(
            "SerpApi provider usage guard has no safe request headroom; "
            "preserving last known-good feed."
        )
        return

    acquisition.main()
    acquisition_remote.stamp_policy_metadata()
    stamp_supply_metadata()


if __name__ == "__main__":
    main()
