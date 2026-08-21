import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/fast-indeed-refresh.yml"


class FastIndeedRefreshWorkflowTests(unittest.TestCase):
    def test_fast_refresh_is_manual_indeed_only_and_avoids_new_llm_calls(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("timeout-minutes: 10", text)
        self.assertIn("on:\n  workflow_dispatch:", text)
        self.assertNotIn("python scripts/acquisition_precision.py", text)
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

    def test_fast_refresh_does_not_auto_trigger_and_double_spend_provider_quota(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertNotIn("\n  pull_request:\n", text)
        self.assertNotIn("\n  push:\n    branches:", text)
        self.assertIn("group: fast-indeed-refresh", text)
        self.assertIn("cancel-in-progress: true", text)


if __name__ == "__main__":
    unittest.main()
