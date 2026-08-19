import importlib
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

mod = importlib.import_module("acquisition_quality")


def job(description: str) -> dict:
    return {
        "title": "データ処理スタッフ",
        "location": "日本",
        "description": description,
        "job_highlights": [],
        "extensions": [],
    }


class AcquisitionQualityTests(unittest.TestCase):
    def test_weekly_partial_remote_is_blocked(self):
        self.assertTrue(mod.partial_remote_blockers(job("慣れたら在宅勤務週1～2日。残りは出社です。")))

    def test_explicit_partial_remote_phrase_is_blocked(self):
        self.assertIn("在宅あり", mod.partial_remote_blockers(job("在宅ありのハイブリッド求人です")))

    def test_negated_hybrid_is_not_blocked(self):
        self.assertEqual(mod.partial_remote_blockers(job("完全在宅です。ハイブリッド勤務は不可、出社不要です。")), [])

    def test_coordination_core_work_is_attention_blocked(self):
        found = mod.quality_attention_blockers(job("社内外関係者との調整業務と進捗管理を担当します"))
        self.assertIn("調整業務", found)
        self.assertIn("進捗管理", found)

    def test_negated_coordination_is_not_attention_blocked(self):
        self.assertEqual(mod.quality_attention_blockers(job("データ入力中心。調整業務なし。")), [])

    def test_ocr_and_extraction_gain_equivalent_automation_signals(self):
        text = mod.augment_automation_text("OCR結果のデータ抽出と文字認識チェック")
        self.assertIn("文字起こし", text)
        self.assertIn("データ入力", text)
        self.assertIn("転記", text)

    def test_review_quality_floor_is_enforced(self):
        self.assertTrue(mod.review_row_meets_quality({"automation_confidence": 55, "human_dependency_risk": 25}))
        self.assertFalse(mod.review_row_meets_quality({"automation_confidence": 54, "human_dependency_risk": 0}))
        self.assertFalse(mod.review_row_meets_quality({"automation_confidence": 90, "human_dependency_risk": 26}))

    def test_provider_no_results_becomes_empty_success(self):
        with patch.object(mod, "GENERIC_SERPAPI_FETCH", return_value={"error": "Google hasn't returned any results for this query."}):
            got = mod.quality_serpapi_fetch("query", "secret")
        self.assertEqual(got, {"jobs_results": []})

    def test_real_provider_errors_remain_errors(self):
        with patch.object(mod, "GENERIC_SERPAPI_FETCH", return_value={"error": "Rate limit exceeded"}):
            with self.assertRaises(mod.acquisition_remote.SerpApiRateLimitError):
                mod.quality_serpapi_fetch("query", "secret")


if __name__ == "__main__":
    unittest.main()
