import importlib.util
import inspect
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

path = SCRIPTS / "acquisition_remote.py"
spec = importlib.util.spec_from_file_location("acquisition_remote_supply_test", path)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class ProductionRemoteAcquisitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        mod.configure_production_policy()

    def test_shallow_pool_can_sweep_all_profiles_and_page_deeper(self):
        self.assertGreaterEqual(mod.acquisition.MAX_REQUESTS_PER_RUN, len(mod.acquisition.QUERY_PROFILES))
        self.assertGreater(mod.acquisition.MAX_REQUESTS_PER_RUN, len(mod.acquisition.QUERY_PROFILES))

    def test_production_fetch_supports_next_page_token(self):
        params = inspect.signature(mod.acquisition.serpapi_fetch).parameters
        self.assertIn("next_page_token", params)

    def test_structured_work_from_home_is_review_evidence_not_high_proof(self):
        job = {
            "title": "データ入力スタッフ",
            "company_name": "Example",
            "location": "日本",
            "description": "データ入力と転記、Excelでのデータ整理を担当します。",
            "detected_extensions": {"posted_at": "1 day ago"},
            "apply_options": [{"title": "Indeed", "link": "https://jp.indeed.com/viewjob?jk=remote123"}],
        }
        row = mod.acquisition.build_row(job, "structured_data", {})
        self.assertIsNotNone(row)
        self.assertEqual(row["tier"], "review")
        self.assertTrue(row["remote_search_only"])
        self.assertIn("在宅要確認", row["tags"])
        self.assertTrue(any("本文要確認" in reason for reason in row["remote_reasons"]))

    def test_explicit_full_remote_review_does_not_need_warning_label(self):
        job = {
            "title": "完全在宅 データ入力スタッフ",
            "company_name": "Example",
            "location": "日本",
            "description": "完全在宅でデータ入力を担当します。",
            "detected_extensions": {"posted_at": "1 day ago"},
            "apply_options": [{"title": "Indeed", "link": "https://jp.indeed.com/viewjob?jk=remote456"}],
        }
        row = mod.acquisition.build_row(job, "structured_data", {})
        self.assertIsNotNone(row)
        self.assertFalse(row.get("remote_search_only"))
        self.assertNotIn("在宅要確認", row.get("tags") or [])


if __name__ == "__main__":
    unittest.main()
