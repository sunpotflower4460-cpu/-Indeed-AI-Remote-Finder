import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/fast-indeed-refresh.yml"


class FastIndeedRefreshWorkflowTests(unittest.TestCase):
    def test_fast_refresh_publishes_before_new_llm_calls(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("timeout-minutes: 10", text)
        self.assertIn("python scripts/acquisition_precision.py", text)
        self.assertIn("python scripts/supplement_indeed_web_index.py --previous /tmp/previous-jobs.json", text)
        self.assertIn("python scripts/validate_indeed_discovery_runtime.py", text)
        self.assertIn("python scripts/apply_llm_quality_gate.py", text)
        self.assertNotIn("python scripts/llm_review.py", text)
        self.assertNotIn("python scripts/llm_review_quality.py", text)
        self.assertIn('git commit -m "chore: refresh Indeed-first job feed"', text)

    def test_fast_refresh_uses_same_candidate_concurrency_group(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("group: update-job-candidates", text)
        self.assertIn("cancel-in-progress: true", text)

    def test_fast_refresh_triggers_on_its_own_main_addition(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("branches: [\"main\"]", text)
        self.assertIn("'.github/workflows/fast-indeed-refresh.yml'", text)


if __name__ == "__main__":
    unittest.main()
