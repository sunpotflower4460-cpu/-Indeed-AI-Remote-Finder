import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "scripts" / "fetch_jobs.py"
spec = importlib.util.spec_from_file_location("finder", path)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def s(text):
    return mod.score_job(text, datetime.now(timezone.utc), None)


class ScoringGuardTests(unittest.TestCase):
    def test_high_confidence_structured_remote_work(self):
        r = s("完全在宅 フルリモート データ入力 転記 データ整理 スプレッドシート")
        self.assertEqual(r.tier, "high")
        self.assertGreaterEqual(r.remote, 82)
        self.assertGreaterEqual(r.automation, 82)

    def test_sales_is_not_high_confidence(self):
        r = s("完全在宅 データ入力 法人営業 電話営業 テレアポ")
        self.assertEqual(r.tier, "hidden")

    def test_hybrid_is_not_high_confidence(self):
        r = s("在宅勤務 データ入力 週2出社 ハイブリッド")
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

    def test_unknown_date_stays_review_on_first_sighting(self):
        r = mod.score_job("完全在宅 データ入力 転記 データ整理", None, None)
        self.assertEqual(r.tier, "review")

    def test_unknown_date_can_gain_confidence_after_repeat_sightings(self):
        prev = {"seen_count": 8, "last_seen": datetime.now(timezone.utc).isoformat()}
        r = mod.score_job("完全在宅 データ入力 転記 データ整理", None, prev)
        self.assertEqual(r.tier, "high")

    def test_known_stale_listing_is_hidden(self):
        from datetime import timedelta
        old = datetime.now(timezone.utc) - timedelta(days=75)
        r = mod.score_job("完全在宅 データ入力 転記 データ整理", old, None)
        self.assertEqual(r.tier, "hidden")

    def test_negated_onsite_phrase_does_not_false_reject(self):
        r = s("完全在宅 出社不要 データ入力 転記 データ整理")
        self.assertEqual(r.tier, "high")

    def test_customer_support_stays_out_of_high_feed(self):
        r = s("完全在宅 データ入力 転記 カスタマーサポート")
        self.assertNotEqual(r.tier, "high")


if __name__ == "__main__":
    unittest.main()
