import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class RefreshTriggerSingletonTests(unittest.TestCase):
    def test_obsolete_post_merge_dispatcher_is_absent(self):
        self.assertFalse((ROOT / ".github/workflows/refresh-after-merge.yml").exists())

    def test_main_push_is_the_single_merge_refresh_path(self):
        workflow = (ROOT / ".github/workflows/update-jobs.yml").read_text(encoding="utf-8")
        self.assertIn("push:\n", workflow)
        self.assertIn('branches: ["main"]', workflow)
        self.assertIn("- 'scripts/**'", workflow)
        self.assertIn("- '.github/workflows/update-jobs.yml'", workflow)
        self.assertNotIn("pull_request:", workflow)
        self.assertNotIn("pull_request_target:", workflow)
        self.assertNotIn("gh workflow run update-jobs.yml", workflow)

    def test_refreshes_remain_serialized(self):
        workflow = (ROOT / ".github/workflows/update-jobs.yml").read_text(encoding="utf-8")
        self.assertIn("group: update-job-candidates", workflow)
        self.assertIn("cancel-in-progress: false", workflow)


if __name__ == "__main__":
    unittest.main()
