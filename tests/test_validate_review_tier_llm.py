import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

path = SCRIPTS / "validate_feed.py"
spec = importlib.util.spec_from_file_location("validate_feed_review_tier_test", path)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def strong_review():
    return {
        "verdict": "strong",
        "automatable_fraction": 96,
        "confidence": 92,
        "human_dependency": "low",
        "physical_presence_required": False,
        "synchronous_human_interaction": "none",
        "data_sensitivity_risk": "unknown",
        "automation_summary": "定型デジタル処理中心",
        "automation_plan": ["取得", "処理", "出力"],
        "blockers": [],
        "questions_to_confirm": ["AI利用可否"],
        "strict_pass": True,
    }


def review_row():
    return {
        "tier": "review",
        "automation_confidence": 80,
        "human_dependency_risk": 0,
        "automation_reasons": ["データ入力", "転記"],
        "quality_policy_version": 2,
        "quality_gate": "async-ai-remote-v2",
        "autonomy_attention_risk": "low",
        "remote_search_only": False,
        "full_listing_presence_screened": True,
        "presence_gate_version": 1,
        "continuous_presence_risk": "low",
        "llm_review": strong_review(),
        "llm_strict_pass": True,
        "llm_input_hash": "a" * 64,
        "llm_model": "gpt-5.6-luna",
    }


class ReviewTierStrictValidationTests(unittest.TestCase):
    def test_current_quality_gated_review_tier_can_hold_strict_llm_pass(self):
        row = review_row()
        errors = []
        mod.validate_llm(row, "jobs[0]", errors)
        self.assertEqual(errors, [])
        self.assertTrue(mod.review_tier_strict_context_valid(row))

    def test_review_tier_strict_pass_requires_current_quality_gate(self):
        row = review_row()
        row["quality_policy_version"] = 1
        errors = []
        mod.validate_llm(row, "jobs[0]", errors)
        self.assertTrue(any("lacks current deterministic quality/presence proof" in error for error in errors))
        self.assertFalse(mod.review_tier_strict_context_valid(row))

    def test_review_tier_strict_pass_requires_final_presence_proof(self):
        row = review_row()
        row["continuous_presence_risk"] = "unknown"
        errors = []
        mod.validate_llm(row, "jobs[0]", errors)
        self.assertTrue(any("lacks current deterministic quality/presence proof" in error for error in errors))

    def test_review_tier_strict_pass_requires_two_automation_signals(self):
        row = review_row()
        row["automation_reasons"] = ["データ入力"]
        errors = []
        mod.validate_llm(row, "jobs[0]", errors)
        self.assertTrue(any("lacks current deterministic quality/presence proof" in error for error in errors))

    def test_high_tier_strict_pass_remains_valid(self):
        row = review_row()
        row["tier"] = "high"
        errors = []
        mod.validate_llm(row, "jobs[0]", errors)
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
