import importlib.util
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

path = Path(__file__).resolve().parents[1] / "scripts" / "fetch_jobs.py"
spec = importlib.util.spec_from_file_location("finder", path)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def s(text, *, remote_filter=False, days_old=0):
    published = datetime.now(timezone.utc) - timedelta(days=days_old)
    return mod.score_job(text, published, None, remote_api_filter=remote_filter)


def provider_job(jid="job123"):
    return {
        "title": "完全在宅 データ入力 転記",
        "company_name": "Example",
        "location": "Anywhere",
        "description": "データ整理、転記、データ入力。フルリモート。",
        "detected_extensions": {"posted_at": "1 day ago"},
        "apply_options": [
            {
                "title": "Indeed",
                "link": f"https://jp.indeed.com/viewjob?jk={jid}&utm_source=x",
            }
        ],
    }


class ScoringGuardTests(unittest.TestCase):
    def test_high_confidence_structured_remote_work(self):
        r = s("完全在宅 フルリモート データ入力 転記 データ整理 スプレッドシート")
        self.assertEqual(r.tier, "high")
        self.assertGreaterEqual(r.remote, 82)
        self.assertGreaterEqual(r.automation, 82)

    def test_sales_is_not_high_confidence(self):
        r = s("完全在宅 データ入力 転記 法人営業 電話営業 テレアポ")
        self.assertEqual(r.tier, "hidden")

    def test_hybrid_is_not_high_confidence(self):
        r = s("在宅勤務 データ入力 転記 週2出社 ハイブリッド")
        self.assertNotEqual(r.tier, "high")

    def test_annotation_remote_is_high(self):
        r = s("フルリモート アノテーション AI評価 タグ付け データチェック")
        self.assertEqual(r.tier, "high")

    def test_fullwidth_percent_remote_is_explicit(self):
        r = s("100％リモート アノテーション AI評価 タグ付け データチェック")
        self.assertEqual(r.tier, "high")

    def test_ambiguous_free_location_is_not_enough_for_high(self):
        r = s("勤務地自由 データ入力 転記 データ整理", remote_filter=True)
        self.assertNotEqual(r.tier, "high")
        self.assertNotIn("完全リモート", mod.tags_for("勤務地自由 データ入力 転記"))

    def test_vague_remote_role_does_not_pass(self):
        r = s("完全在宅 一般スタッフ 未経験歓迎")
        self.assertNotEqual(r.tier, "high")

    def test_negated_onsite_phrase_does_not_block(self):
        r = s("完全在宅 出社不要 データ入力 転記 データ整理")
        self.assertEqual(r.tier, "high")
        self.assertNotIn("出社", r.risk_reasons)

    def test_natural_negated_onsite_phrase_does_not_block(self):
        r = s("完全在宅 出社の必要はありません データ入力 転記 データ整理")
        self.assertEqual(r.tier, "high")
        self.assertNotIn("出社", r.risk_reasons)

    def test_negated_phone_phrase_does_not_add_risk(self):
        r = s("完全在宅 電話対応なし アノテーション AI評価 タグ付け")
        self.assertEqual(r.tier, "high")
        self.assertNotIn("電話対応", r.risk_reasons)

    def test_api_remote_filter_only_is_review_not_high(self):
        r = s("データ入力 転記 データ整理", remote_filter=True)
        self.assertEqual(r.tier, "review")

    def test_old_listing_is_not_high(self):
        r = s("完全在宅 データ入力 転記 データ整理", days_old=20)
        self.assertEqual(r.tier, "review")

    def test_very_old_listing_is_hidden(self):
        r = s("完全在宅 データ入力 転記 データ整理", days_old=45)
        self.assertEqual(r.tier, "hidden")

    def test_customer_support_stays_out_of_high_feed(self):
        r = s("完全在宅 データ入力 転記 カスタマーサポート")
        self.assertNotEqual(r.tier, "high")

    def test_physical_task_is_hidden(self):
        r = s("完全在宅 商品登録 データ入力 梱包 商品撮影")
        self.assertEqual(r.tier, "hidden")

    def test_relative_japanese_date(self):
        now = datetime(2026, 8, 19, tzinfo=timezone.utc)
        got = mod.parse_relative_posted_at("8日前", now)
        self.assertEqual(got, now - timedelta(days=8))

    def test_relative_english_date(self):
        now = datetime(2026, 8, 19, tzinfo=timezone.utc)
        got = mod.parse_relative_posted_at("3 days ago", now)
        self.assertEqual(got, now - timedelta(days=3))

    def test_30_plus_is_stale(self):
        now = datetime(2026, 8, 19, tzinfo=timezone.utc)
        got = mod.parse_relative_posted_at("30+ days ago", now)
        self.assertLessEqual(got, now - timedelta(days=31))

    def test_canonical_indeed_apply(self):
        got = mod.canonical_indeed_url(
            "https://www.indeed.com/viewjob?jk=abc123&utm_source=google_jobs_apply"
        )
        self.assertEqual(got, ("https://jp.indeed.com/viewjob?jk=abc123", "abc123"))

    def test_invalid_indeed_job_id_rejected(self):
        self.assertIsNone(
            mod.canonical_indeed_url("https://jp.indeed.com/viewjob?jk=../../bad")
        )

    def test_non_indeed_apply_rejected(self):
        self.assertIsNone(mod.canonical_indeed_url("https://example.com/jobs/1"))

    def test_malformed_apply_options_are_ignored(self):
        self.assertIsNone(mod.find_indeed_apply({"apply_options": [None, "bad"]}))
        self.assertIsNone(mod.find_indeed_apply({"apply_options": {"title": "Indeed"}}))

    def test_build_row_requires_indeed_apply(self):
        job = {
            "title": "完全在宅 データ入力 転記",
            "description": "データ整理と転記を行います。完全在宅です。",
            "detected_extensions": {"posted_at": "1 day ago"},
            "apply_options": [{"title": "Company", "link": "https://example.com/apply"}],
        }
        self.assertIsNone(mod.build_row(job, "structured", {}))

    def test_build_row_accepts_indeed_apply(self):
        row = mod.build_row(provider_job(), "structured", {})
        self.assertIsNotNone(row)
        self.assertEqual(row["id"], "job123")
        self.assertEqual(row["url"], "https://jp.indeed.com/viewjob?jk=job123")
        self.assertEqual(row["tier"], "high")

    def test_one_malformed_provider_row_does_not_abort_remaining_rows(self):
        payload = {"jobs_results": [None, provider_job("good123")]}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "jobs.json"
            with (
                patch.object(mod, "OUT", out),
                patch.object(mod, "QUERIES", [("structured", "query")]),
                patch.object(mod, "serpapi_fetch", return_value=payload),
                patch.dict(os.environ, {"SERPAPI_KEY": "fake"}),
            ):
                mod.main()
            data = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(data["query_success"], 1)
        self.assertEqual(data["malformed_jobs"], 1)
        self.assertEqual([row["id"] for row in data["jobs"]], ["good123"])

    def test_malformed_jobs_results_marks_query_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "jobs.json"
            with (
                patch.object(mod, "OUT", out),
                patch.object(mod, "QUERIES", [("structured", "query")]),
                patch.object(mod, "serpapi_fetch", return_value={"jobs_results": {"bad": True}}),
                patch.dict(os.environ, {"SERPAPI_KEY": "fake"}),
            ):
                with self.assertRaises(SystemExit):
                    mod.main()
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
