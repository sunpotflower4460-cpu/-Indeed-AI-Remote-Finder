import importlib
import json
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


def indeed_job(description: str) -> dict:
    row = job(description)
    row["apply_options"] = [
        {"title": "Indeed", "link": "https://jp.indeed.com/viewjob?jk=abc123def"}
    ]
    return row


class AcquisitionQualityTests(unittest.TestCase):
    def setUp(self):
        mod.reset_quality_telemetry()

    def test_policy_version_and_thresholds_are_strict(self):
        self.assertEqual(mod.QUALITY_POLICY_VERSION, 2)
        self.assertEqual(mod.QUALITY_GATE, "async-ai-remote-v2")
        self.assertEqual(mod.QUALITY_TELEMETRY_VERSION, 1)
        self.assertEqual(mod.REVIEW_AUTOMATION_MIN, 64)
        self.assertEqual(mod.REVIEW_HUMAN_RISK_MAX, 18)
        self.assertEqual(mod.REVIEW_AUTOMATION_SIGNAL_MIN, 2)

    def test_weekly_partial_remote_is_blocked(self):
        self.assertTrue(mod.partial_remote_blockers(job("慣れたら在宅勤務週1～2日。残りは出社です。")))

    def test_explicit_partial_remote_phrase_is_blocked(self):
        self.assertIn("在宅あり", mod.partial_remote_blockers(job("在宅ありのハイブリッド求人です")))

    def test_conditional_full_remote_is_blocked(self):
        self.assertIn("ほぼフルリモート", mod.partial_remote_blockers(job("ほぼフルリモートですが月1回出社です")))
        self.assertIn("フルリモート相談可", mod.partial_remote_blockers(job("フルリモート相談可の求人です")))

    def test_monthly_office_attendance_is_blocked(self):
        self.assertTrue(mod.partial_remote_blockers(job("フルリモート中心ですが月1回出社があります")))

    def test_negated_hybrid_is_not_blocked(self):
        self.assertEqual(mod.partial_remote_blockers(job("完全在宅です。ハイブリッド勤務は不可、出社不要です。")), [])

    def test_explicit_full_remote_must_exist_in_listing(self):
        self.assertTrue(mod.explicit_full_remote_evidence(job("完全在宅でデータ入力を行います")))
        self.assertFalse(mod.explicit_full_remote_evidence(job("在宅勤務可能なデータ入力です")))

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

    def test_review_quality_floor_requires_two_signals(self):
        good = {
            "automation_confidence": 64,
            "human_dependency_risk": 18,
            "automation_reasons": ["データ入力", "転記"],
        }
        self.assertTrue(mod.review_row_meets_quality(good))
        self.assertFalse(mod.review_row_meets_quality({**good, "automation_confidence": 63}))
        self.assertFalse(mod.review_row_meets_quality({**good, "human_dependency_risk": 19}))
        self.assertFalse(mod.review_row_meets_quality({**good, "automation_reasons": ["データ入力"]}))
        self.assertEqual(
            mod.review_row_quality_rejection({**good, "automation_confidence": 63}),
            "review-automation-below-floor",
        )
        self.assertEqual(
            mod.review_row_quality_rejection({**good, "human_dependency_risk": 19}),
            "review-human-risk-above-ceiling",
        )
        self.assertEqual(
            mod.review_row_quality_rejection({**good, "automation_reasons": ["データ入力"]}),
            "review-insufficient-automation-signals",
        )

    def test_rich_excerpt_keeps_more_context_for_llm(self):
        raw = job("完全在宅。" + ("データ入力と転記。" * 800))
        excerpt = mod.rich_listing_excerpt(raw)
        self.assertEqual(mod.RICH_SNIPPET_MAX, 6000)
        self.assertGreater(len(excerpt), 2400)
        self.assertLessEqual(len(excerpt), mod.RICH_SNIPPET_MAX)

    def test_presence_requirement_after_old_excerpt_boundary_is_still_blocked(self):
        prefix = "完全在宅。データ入力と転記を行います。" + ("定型処理。" * 600)
        raw = job(prefix + "勤務中はカメラ常時ONで本人の在席確認を行います。")
        self.assertGreater(len(mod.normalized_job_text(raw)), 2400)
        self.assertIsNotNone(mod.human_presence_blocker(raw))

    def test_automatable_always_on_system_is_not_presence_blocked(self):
        raw = job("完全在宅。自動監視システムを常時ログイン状態で稼働し、異常を自動記録します。")
        self.assertIsNone(mod.human_presence_blocker(raw))

    def test_prefilter_rejection_reasons_are_coarse_and_ordered(self):
        self.assertEqual(
            mod.prefilter_rejection_reason(job("完全在宅。データ入力と転記。")),
            "no-indeed-apply",
        )
        self.assertEqual(
            mod.prefilter_rejection_reason(indeed_job("在宅勤務可能。データ入力と転記。")),
            "missing-explicit-full-remote",
        )
        self.assertEqual(
            mod.prefilter_rejection_reason(indeed_job("完全在宅相談可。データ入力と転記。")),
            "partial-or-conditional-remote",
        )
        self.assertEqual(
            mod.prefilter_rejection_reason(indeed_job("完全在宅。顧客対応をリアルタイムで行います。")),
            "synchronous-human-attention",
        )
        self.assertIsNone(
            mod.prefilter_rejection_reason(indeed_job("完全在宅。データ入力と転記を行います。"))
        )

    def test_quality_telemetry_contains_counts_only(self):
        mod._record_quality_outcome("anchor_core_data_entry_00", "missing-explicit-full-remote")
        mod._record_quality_outcome("anchor_core_data_entry_00", None)
        mod._record_quality_outcome("translation", "ongoing-human-coordination")
        got = mod.quality_telemetry_snapshot()
        self.assertEqual(got["candidate_quality_gate_telemetry_version"], 1)
        self.assertEqual(got["candidate_quality_evaluated_jobs"], 3)
        self.assertEqual(got["candidate_quality_pre_llm_accepted"], 1)
        self.assertEqual(got["candidate_quality_rejected_jobs"], 2)
        self.assertEqual(got["candidate_quality_rejection_counts"]["missing-explicit-full-remote"], 1)
        self.assertEqual(got["candidate_quality_rejection_counts"]["ongoing-human-coordination"], 1)
        serialized = json.dumps(got, ensure_ascii=False)
        self.assertNotIn("title", serialized.lower())
        self.assertNotIn("company", serialized.lower())
        self.assertNotIn("https://", serialized.lower())

    def test_provider_no_results_becomes_empty_success(self):
        with patch.object(mod, "GENERIC_SERPAPI_FETCH", return_value={"error": "Google hasn't returned any results for this query."}):
            got = mod.quality_serpapi_fetch("query", "secret")
        self.assertEqual(got, {"jobs_results": [], "serpapi_pagination": {}})

    def test_real_provider_errors_remain_errors(self):
        with patch.object(mod, "GENERIC_SERPAPI_FETCH", return_value={"error": "Rate limit exceeded"}):
            with self.assertRaises(mod.acquisition_remote.SerpApiRateLimitError):
                mod.quality_serpapi_fetch("query", "secret")


if __name__ == "__main__":
    unittest.main()
