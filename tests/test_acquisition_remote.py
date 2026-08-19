import importlib
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


class ProductionRemoteAdapterTests(unittest.TestCase):
    def fresh_modules(self):
        for name in ("acquisition_remote", "acquisition"):
            sys.modules.pop(name, None)
        acquisition = importlib.import_module("acquisition")
        remote = importlib.import_module("acquisition_remote")
        return acquisition, remote

    def test_production_sweeps_every_profile_when_pool_is_shallow(self):
        acquisition, remote = self.fresh_modules()
        remote.configure_production_policy()
        self.assertEqual(acquisition.MAX_REQUESTS_PER_RUN, len(acquisition.QUERY_PROFILES))
        self.assertEqual(acquisition.request_limit_for_pool(0), len(acquisition.QUERY_PROFILES))

    def test_work_from_home_filter_is_only_review_evidence(self):
        acquisition, remote = self.fresh_modules()
        remote.configure_production_policy()
        job = {
            "title": "データ整理スタッフ",
            "company_name": "Example",
            "location": "日本",
            "description": "データ整理とリサーチを行います。",
            "detected_extensions": {"posted_at": "1 day ago", "work_from_home": True},
            "apply_options": [{"title": "Indeed", "link": "https://jp.indeed.com/viewjob?jk=remote123"}],
        }
        base_scores = acquisition.legacy.Scores(
            remote=68,
            automation=55,
            freshness=98,
            risk=0,
            overall=70,
            tier="review",
            remote_reasons=["Google Jobs:在宅勤務フィルタ"],
            automation_reasons=["データ整理", "リサーチ"],
            risk_reasons=[],
        )
        with patch.object(acquisition.legacy, "score_job", return_value=base_scores):
            row = acquisition.build_row(job, "structured_data", {})
        self.assertIsNotNone(row)
        self.assertEqual(row["tier"], "review")
        self.assertTrue(row["remote_search_only"])
        self.assertIn("在宅要確認", row["tags"])

    def test_explicit_full_remote_review_does_not_get_warning(self):
        acquisition, remote = self.fresh_modules()
        remote.configure_production_policy()
        job = {
            "title": "完全在宅 データ整理スタッフ",
            "company_name": "Example",
            "description": "完全在宅でデータ整理とリサーチを行います。",
            "detected_extensions": {"posted_at": "1 day ago", "work_from_home": True},
            "apply_options": [{"title": "Indeed", "link": "https://jp.indeed.com/viewjob?jk=remote456"}],
        }
        base_scores = acquisition.legacy.Scores(
            remote=100,
            automation=55,
            freshness=98,
            risk=0,
            overall=80,
            tier="review",
            remote_reasons=["Google Jobs:在宅勤務フィルタ", "完全在宅"],
            automation_reasons=["データ整理", "リサーチ"],
            risk_reasons=[],
        )
        with patch.object(acquisition.legacy, "score_job", return_value=base_scores):
            row = acquisition.build_row(job, "structured_data", {})
        self.assertIsNotNone(row)
        self.assertFalse(row["remote_search_only"])


if __name__ == "__main__":
    unittest.main()
