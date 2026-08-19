import importlib.util
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "scripts" / "fetch_jobs.py"
spec = importlib.util.spec_from_file_location("finder", path)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def s(text, *, remote_filter=False, days_old=0):
    published = datetime.now(timezone.utc) - timedelta(days=days_old)
    return mod.score_job(text, published, None, remote_api_filter=remote_filter)


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

    def test_vague_remote_role_does_not_pass(self):
        r = s("完全在宅 一般スタッフ 未経験歓迎")
        self.assertNotEqual(r.tier, "high")

    def test_negated_onsite_phrase_does_not_block(self):
        r = s("完全在宅 出社不要 データ入力 転記 データ整理")
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
        got = mod.canonical_indeed_url("https://www.indeed.com/viewjob?jk=abc123&utm_source=google_jobs_apply")
        self.assertEqual(got, ("https://jp.indeed.com/viewjob?jk=abc123", "abc123"))

    def test_non_indeed_apply_rejected(self):
        self.assertIsNone(mod.canonical_indeed_url("https://example.com/jobs/1"))

    def test_build_row_requires_indeed_apply(self):
        job = {
            "title": "完全在宅 データ入力 転記",
            "description": "データ整理と転記を行います。完全在宅です。",
            "detected_extensions": {"posted_at": "1 day ago"},
            "apply_options": [{"title": "Company", "link": "https://example.com/apply"}],
        }
        self.assertIsNone(mod.build_row(job, "structured", {}))

    def test_build_row_accepts_indeed_apply(self):
        job = {
            "title": "完全在宅 データ入力 転記",
            "company_name": "Example",
            "location": "Anywhere",
            "description": "データ整理、転記、データ入力。フルリモート。",
            "detected_extensions": {"posted_at": "1 day ago"},
            "apply_options": [{"title": "Indeed", "link": "https://jp.indeed.com/viewjob?jk=job123&utm_source=x"}],
        }
        row = mod.build_row(job, "structured", {})
        self.assertIsNotNone(row)
        self.assertEqual(row["id"], "job123")
        self.assertEqual(row["url"], "https://jp.indeed.com/viewjob?jk=job123")
        self.assertEqual(row["tier"], "high")


if __name__ == "__main__":
    unittest.main()
