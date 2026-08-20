import importlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

mod = importlib.import_module("apply_sources")


class ApplySourceTests(unittest.TestCase):
    def job(self, *links):
        return {
            "apply_options": [
                {"title": f"source-{index}", "link": link}
                for index, link in enumerate(links)
            ]
        }

    def test_indeed_remains_first_choice(self):
        got = mod.find_trusted_apply(
            self.job(
                "https://next.rikunabi.com/viewjob/jk123456",
                "https://jp.indeed.com/viewjob?jk=abc123456",
            )
        )
        self.assertIsNotNone(got)
        self.assertEqual(got.source, "Indeed")
        self.assertEqual(got.kind, "indeed")
        self.assertEqual(got.job_id, "abc123456")
        self.assertEqual(got.url, "https://jp.indeed.com/viewjob?jk=abc123456")

    def test_audited_major_boards_are_allowed_without_indeed(self):
        cases = (
            ("https://next.rikunabi.com/viewjob/jk123456", "リクナビNEXT"),
            ("https://townwork.net/viewjob/job123456", "タウンワーク"),
            ("https://www.froma.com/viewjob/job123456", "フロム・エー ナビ"),
            ("https://www.hatalike.jp/viewjob/job123456", "はたらいく"),
            ("https://toranet.jp/viewjob/job123456", "とらばーゆ"),
        )
        for url, source in cases:
            with self.subTest(source=source):
                got = mod.find_trusted_apply(self.job(url))
                self.assertIsNotNone(got)
                self.assertEqual(got.source, source)
                self.assertEqual(got.kind, "trusted-job-board")
                self.assertTrue(got.job_id.startswith("board-"))

    def test_unknown_aggregator_is_not_allowed(self):
        self.assertIsNone(
            mod.find_trusted_apply(
                self.job("https://example.invalid/jobs/abc123")
            )
        )

    def test_insecure_or_homepage_links_are_not_application_targets(self):
        self.assertIsNone(
            mod.find_trusted_apply(self.job("http://townwork.net/viewjob/abc123"))
        )
        self.assertIsNone(
            mod.find_trusted_apply(self.job("https://townwork.net/"))
        )

    def test_board_job_id_is_stable_for_same_url(self):
        url = "https://townwork.net/viewjob/abc123?from=googlejobs"
        first = mod.find_trusted_apply(self.job(url))
        second = mod.find_trusted_apply(self.job(url))
        self.assertEqual(first.job_id, second.job_id)


if __name__ == "__main__":
    unittest.main()
