import importlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

mod = importlib.import_module("acquisition_precision")


class TrustedApplyIntegrationTests(unittest.TestCase):
    def strong_remote_job(self, link):
        return {
            "title": "完全在宅 AIデータ評価・アノテーション",
            "company_name": "Example Co",
            "location": "日本",
            "description": (
                "完全在宅、フルリモート。AIモデルの回答評価、アノテーション、"
                "データ評価をオンラインで非同期に実施します。"
                "電話対応なし、会議参加なし、顧客対応なし。"
            ),
            "highlights": [],
            "extensions": ["1日前"],
            "detected_extensions": {"posted_at": "1日前"},
            "via": "Google Jobs",
            "apply_options": [{"title": "応募", "link": link}],
        }

    def test_trusted_non_indeed_job_can_reach_existing_row_builder(self):
        job = self.strong_remote_job("https://townwork.net/viewjob/job123456")
        self.assertIsNone(mod.policy_aware_prefilter(job))
        row = mod.trusted_source_build_row(job, "test_ai_eval", {})
        self.assertIsNotNone(row)
        self.assertEqual(row["apply_source"], "タウンワーク")
        self.assertEqual(row["apply_source_kind"], "trusted-job-board")
        self.assertEqual(row["trusted_apply_policy_version"], 2)
        self.assertEqual(row["url"], "https://townwork.net/viewjob/job123456")
        self.assertTrue(row["id"].startswith("apply-"))

    def test_trusted_ats_job_can_reach_existing_row_builder(self):
        job = self.strong_remote_job("https://jobs.lever.co/weloglobal/abc123")
        self.assertIsNone(mod.policy_aware_prefilter(job))
        row = mod.trusted_source_build_row(job, "test_search_eval", {})
        self.assertIsNotNone(row)
        self.assertEqual(row["apply_source"], "Lever")
        self.assertEqual(row["apply_source_kind"], "trusted-ats")
        self.assertEqual(row["trusted_apply_policy_version"], 2)

    def test_unknown_apply_host_is_rejected_before_quality_publication(self):
        job = self.strong_remote_job("https://unknown.invalid/viewjob/job123456")
        self.assertEqual(mod.policy_aware_prefilter(job), "no-trusted-apply")
        self.assertIsNone(mod.trusted_source_build_row(job, "test_ai_eval", {}))

    def test_install_raises_internal_cap_but_keeps_provider_guard_path(self):
        original = mod.acquisition.DEFAULT_MONTHLY_REQUEST_CAP
        try:
            mod.acquisition.DEFAULT_MONTHLY_REQUEST_CAP = 220
            mod.install()
            self.assertEqual(mod.acquisition.DEFAULT_MONTHLY_REQUEST_CAP, 245)
        finally:
            mod.acquisition.DEFAULT_MONTHLY_REQUEST_CAP = original


if __name__ == "__main__":
    unittest.main()
