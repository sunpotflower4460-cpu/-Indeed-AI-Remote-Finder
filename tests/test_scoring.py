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


if __name__ == "__main__":
    unittest.main()
