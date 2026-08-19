import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class RefreshAfterMergeDispatchTests(unittest.TestCase):
    def test_dispatcher_runs_only_after_a_merged_pr(self):
        workflow = (ROOT / ".github/workflows/refresh-after-merge.yml").read_text(encoding="utf-8")
        self.assertIn("pull_request_target:", workflow)
        self.assertIn("types: [closed]", workflow)
        self.assertIn("if: github.event.pull_request.merged == true", workflow)

    def test_dispatcher_does_not_checkout_or_execute_pr_code(self):
        workflow = (ROOT / ".github/workflows/refresh-after-merge.yml").read_text(encoding="utf-8")
        self.assertNotIn("actions/checkout", workflow)
        self.assertNotIn("head.sha", workflow)
        self.assertNotIn("pull_request.head", workflow)
        self.assertNotIn("SERPAPI_KEY", workflow)
        self.assertNotIn("OPENAI_API_KEY", workflow)

    def test_dispatcher_can_only_start_existing_main_refresh(self):
        workflow = (ROOT / ".github/workflows/refresh-after-merge.yml").read_text(encoding="utf-8")
        self.assertIn("actions: write", workflow)
        self.assertIn("contents: read", workflow)
        self.assertIn("GH_TOKEN: ${{ github.token }}", workflow)
        self.assertIn('gh workflow run update-jobs.yml --repo "$GITHUB_REPOSITORY" --ref main', workflow)
        self.assertNotIn("contents: write", workflow)


if __name__ == "__main__":
    unittest.main()
