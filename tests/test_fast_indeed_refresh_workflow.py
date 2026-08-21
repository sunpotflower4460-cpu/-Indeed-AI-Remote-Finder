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

    def test_restore_happens_before_indeed_matching(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        restore = text.index("python scripts/postprocess_feed.py --previous /tmp/previous-jobs.json")
        match = text.index("python scripts/supplement_indeed_web_index.py --previous /tmp/previous-jobs.json")
        self.assertLess(restore, match)
        self.assertIn("python scripts/harden_indeed_index_matches.py", text)
        self.assertIn("candidate_final_indeed_apply_jobs", text)

    def test_fast_refresh_is_diagnosable_on_pr_without_publishing(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("pull_request:", text)
        self.assertIn("if: github.event_name != 'pull_request'", text)
        self.assertIn("group: fast-indeed-refresh-${{ github.event_name }}-${{ github.ref }}", text)
        self.assertIn("cancel-in-progress: true", text)

    def test_fast_refresh_triggers_on_its_own_main_change(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("branches: [\"main\"]", text)
        self.assertIn("'.github/workflows/fast-indeed-refresh.yml'", text)


if __name__ == "__main__":
    unittest.main()
