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
                "https://jobs.lever.co/example/123456",
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
                self.assertTrue(got.job_id.startswith("apply-"))

    def test_major_ats_hosts_are_allowed(self):
        cases = (
            ("https://jobs.lever.co/weloglobal/abc123", "Lever"),
            ("https://boards.greenhouse.io/example/jobs/123456", "Greenhouse"),
            ("https://job-boards.greenhouse.io/example/jobs/123456", "Greenhouse"),
            ("https://jobs.ashbyhq.com/example/abc123", "Ashby"),
            ("https://example.wd3.myworkdayjobs.com/en-US/jobs/job/Japan/abc", "Workday"),
            ("https://jobs.smartrecruiters.com/Example/123456-role", "SmartRecruiters"),
            ("https://apply.workable.com/example/j/ABC123/", "Workable"),
        )
        for url, source in cases:
            with self.subTest(source=source):
                got = mod.find_trusted_apply(self.job(url))
                self.assertIsNotNone(got)
                self.assertEqual(got.source, source)
                self.assertEqual(got.kind, "trusted-ats")

    def test_verified_provider_application_hosts_are_allowed(self):
        cases = (
            ("https://app.outlier.ai/login?job_post_id=4505556005", "Outlier"),
            ("https://outlier.ai/languages/ja-jp", "Outlier"),
            ("https://www.alignerr.com/jobs/example-role", "Alignerr"),
            ("https://www.oneforma.com/projects/example-project/", "OneForma"),
            ("https://my.oneforma.com/Account/register", "OneForma"),
            ("https://www.dataannotation.tech/japanese-jp", "DataAnnotation"),
            ("https://jobs.telusdigital.com/en_US/careers/PipelineDetail/abc/123", "TELUS Digital"),
        )
        for url, source in cases:
            with self.subTest(source=source):
                got = mod.find_trusted_apply(self.job(url))
                self.assertIsNotNone(got)
                self.assertEqual(got.source, source)
                self.assertEqual(got.kind, "trusted-provider")

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

    def test_non_indeed_job_id_is_stable_for_same_url(self):
        url = "https://jobs.lever.co/weloglobal/abc123?lever-source=googlejobs"
        first = mod.find_trusted_apply(self.job(url))
        second = mod.find_trusted_apply(self.job(url))
        self.assertEqual(first.job_id, second.job_id)
        self.assertTrue(first.job_id.startswith("apply-"))


if __name__ == "__main__":
    unittest.main()
