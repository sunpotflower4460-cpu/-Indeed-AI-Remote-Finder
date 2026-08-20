import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class QualityLayerWiringTests(unittest.TestCase):
    def test_acquisition_wrapper_installs_explicit_ai_ban_prefilter(self):
        text = (ROOT / "scripts/acquisition_precision.py").read_text(encoding="utf-8")
        self.assertIn("import apply_ai_tool_policy_gate as ai_policy", text)
        self.assertIn('return "explicit-ai-tool-ban"', text)
        self.assertIn("acquisition_quality.prefilter_rejection_reason = policy_aware_prefilter", text)

    def test_final_ai_policy_gate_runs_after_llm_gate_before_validation(self):
        workflow = (ROOT / ".github/workflows/update-jobs.yml").read_text(encoding="utf-8")
        llm = workflow.index("python scripts/apply_llm_quality_gate.py")
        policy = workflow.index("python scripts/apply_ai_tool_policy_gate.py")
        validate = workflow.index("python scripts/validate_feed.py")
        self.assertLess(llm, policy)
        self.assertLess(policy, validate)

    def test_server_reserve_window_is_fourteen_days(self):
        post = (ROOT / "scripts/postprocess_feed.py").read_text(encoding="utf-8")
        self.assertIn("CARRYOVER_MAX = timedelta(days=14)", post)
        self.assertIn('row["verification_status"] = "reserve-not-rediscovered"', post)
        self.assertIn('row["verification_status"] = "live-search-hit"', post)
        self.assertIn("apply_ai_tool_policy_gate.policy_signal", post)


if __name__ == "__main__":
    unittest.main()
