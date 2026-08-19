import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

path = Path(__file__).resolve().parents[1] / "scripts" / "llm_review.py"
spec = importlib.util.spec_from_file_location("llm_review", path)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def job(snippet="データ入力と転記を行う完全在宅業務"):
    return {
        "id": "abc123",
        "title": "完全在宅 データ入力",
        "company": "Example",
        "location": "日本 / フルリモート",
        "snippet": snippet,
        "tier": "high",
        "automation_confidence": 95,
        "remote_confidence": 100,
        "freshness_confidence": 90,
        "human_dependency_risk": 0,
        "automation_reasons": ["データ入力", "転記"],
        "risk_reasons": [],
        "tags": ["完全リモート", "データ"],
    }


class LlmReviewTests(unittest.TestCase):
    def test_default_paid_review_cap_is_eight(self):
        self.assertEqual(mod.DEFAULT_MAX_NEW_REVIEWS, 8)

    def test_input_hash_changes_with_material_text(self):
        a = mod.input_hash(job("データ入力と転記"))
        b = mod.input_hash(job("電話営業と顧客対応"))
        self.assertNotEqual(a, b)

    def test_extract_output_text_from_response_shape(self):
        payload = {
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": '{"verdict":"strong"}'}],
                }
            ]
        }
        self.assertEqual(mod.extract_output_text(payload), '{"verdict":"strong"}')

    def test_normalize_strict_pass(self):
        review = mod.normalize_review(
            {
                "verdict": "strong",
                "automatable_fraction": 97,
                "confidence": 92,
                "human_dependency": "low",
                "physical_presence_required": False,
                "synchronous_human_interaction": "none",
                "data_sensitivity_risk": "unknown",
                "automation_summary": "定型デジタル処理中心",
                "automation_plan": ["入力を取得", "AIで処理", "結果を出力"],
                "blockers": [],
                "questions_to_confirm": ["生成AI利用が許可されるか"],
            }
        )
        self.assertTrue(review["strict_pass"])

    def test_strict_pass_rejects_occasional_sync(self):
        review = mod.normalize_review(
            {
                "verdict": "strong",
                "automatable_fraction": 98,
                "confidence": 95,
                "human_dependency": "low",
                "physical_presence_required": False,
                "synchronous_human_interaction": "occasional",
                "data_sensitivity_risk": "unknown",
                "automation_summary": "mostly digital",
                "automation_plan": [],
                "blockers": [],
                "questions_to_confirm": [],
            }
        )
        self.assertFalse(review["strict_pass"])

    def test_reuses_same_hash_without_api(self):
        row = job()
        digest = mod.input_hash(row)
        previous_row = dict(row)
        previous_row.update(
            {
                "llm_input_hash": digest,
                "llm_model": "test-model",
                "llm_review": {
                    "verdict": "strong",
                    "automatable_fraction": 95,
                    "confidence": 90,
                    "human_dependency": "low",
                    "physical_presence_required": False,
                    "synchronous_human_interaction": "none",
                    "data_sensitivity_risk": "unknown",
                    "automation_summary": "test",
                    "automation_plan": ["a"],
                    "blockers": [],
                    "questions_to_confirm": ["b"],
                    "strict_pass": True,
                },
            }
        )
        payload = {"jobs": [dict(row)]}
        previous = {"jobs": [previous_row]}
        got = mod.enrich(payload, previous, api_key="", model="test-model")
        self.assertEqual(got["llm_reviewed_jobs"], 1)
        self.assertEqual(got["llm_reused_reviews"], 1)
        self.assertTrue(got["jobs"][0]["llm_strict_pass"])

    def test_review_tier_never_spends_on_new_llm_call(self):
        row = job()
        row["tier"] = "review"
        with patch.object(mod, "call_openai", side_effect=AssertionError("should not call OpenAI")):
            got = mod.enrich({"jobs": [row]}, {}, api_key="fake-key", model="test-model")
        self.assertEqual(got["llm_new_reviews"], 0)
        self.assertEqual(got["llm_skipped_non_high"], 1)
        self.assertNotIn("llm_review", got["jobs"][0])


if __name__ == "__main__":
    unittest.main()
