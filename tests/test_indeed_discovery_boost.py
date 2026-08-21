import importlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

boost = importlib.import_module("supplement_indeed_web_index_v5")


class IndeedDiscoveryBoostTests(unittest.TestCase):
    def test_nested_sitelinks_add_unique_indeed_candidates_without_extra_request(self):
        payload = {
            "organic_results": [
                {
                    "title": "AI 在宅求人 - Indeed",
                    "link": "https://jp.indeed.com/q-ai-%E6%B1%82%E4%BA%BA.html?vjk=TOPVJK123456",
                    "snippet": "AI 在宅求人の検索結果",
                    "sitelinks": {
                        "inline": [
                            {
                                "title": "Japanese AI Rater - job post - Indeed",
                                "link": "https://jp.indeed.com/viewjob?jk=DIRECT123456",
                            },
                            {
                                "title": "Data annotation jobs",
                                "link": "https://jp.indeed.com/q-data-%E6%B1%82%E4%BA%BA.html?vjk=NESTEDVJK123456",
                            },
                        ]
                    },
                }
            ]
        }
        seeds = boost.extract_seeds(payload, "broad-ai-remote")
        self.assertEqual({seed["jk"] for seed in seeds}, {"TOPVJK123456", "DIRECT123456", "NESTEDVJK123456"})
        direct = next(seed for seed in seeds if seed["jk"] == "DIRECT123456")
        self.assertEqual(direct["title"], "Japanese AI Rater")
        self.assertTrue(direct["indeed_exact_url_verified"])
        self.assertTrue(direct["indeed_promotion_eligible"])
        for key in ("TOPVJK123456", "NESTEDVJK123456"):
            seed = next(item for item in seeds if item["jk"] == key)
            self.assertEqual(seed["title"], "")
            self.assertFalse(seed["indeed_exact_url_verified"])
            self.assertFalse(seed["indeed_promotion_eligible"])

    def test_direct_evidence_wins_when_same_jk_appears_as_vjk_and_viewjob(self):
        payload = {
            "organic_results": [
                {
                    "title": "AI jobs - Indeed",
                    "link": "https://jp.indeed.com/q-ai-%E6%B1%82%E4%BA%BA.html?vjk=SAMEKEY123456",
                    "sitelinks": {
                        "inline": [
                            {
                                "title": "AI Trainer - job post - Indeed",
                                "link": "https://jp.indeed.com/viewjob?jk=SAMEKEY123456",
                            }
                        ]
                    },
                }
            ]
        }
        seeds = boost.extract_seeds(payload, "broad-ai-remote")
        self.assertEqual(len(seeds), 1)
        self.assertEqual(seeds[0]["indeed_index_link_kind"], "viewjob-jk")
        self.assertEqual(seeds[0]["title"], "AI Trainer")

    def test_broad_high_yield_profiles_are_first_and_keep_truth_surfaces(self):
        names = [name for name, _ in boost.SEARCH_PROFILES]
        self.assertEqual(names[:2], ["broad-ai-remote", "search-vjk-broad-ai-remote"])
        direct_query = boost.SEARCH_PROFILES[0][1]
        vjk_query = boost.SEARCH_PROFILES[1][1]
        self.assertIn("site:jp.indeed.com/viewjob", direct_query)
        self.assertIn("site:jp.indeed.com/q-", vjk_query)
        self.assertIn("inurl:vjk", vjk_query)
        self.assertIn("OR", direct_query)
        self.assertGreaterEqual(len(boost.SEARCH_PROFILES), 42)

    def test_monthly_budget_is_paced_across_days_left(self):
        budget, used, cap, surplus = boost.request_budget(
            {"serpapi_requests_month": 232, "serpapi_monthly_request_cap": 245, "serpapi_month_days_remaining": 11}
        )
        self.assertEqual((budget, used, cap), (1, 232, 245))
        self.assertEqual(surplus, 2)

        budget, _, _, _ = boost.request_budget(
            {"serpapi_requests_month": 223, "serpapi_monthly_request_cap": 245, "serpapi_month_days_remaining": 11}
        )
        self.assertEqual(budget, 2)

        budget, _, _, _ = boost.request_budget(
            {"serpapi_requests_month": 240, "serpapi_monthly_request_cap": 245, "serpapi_month_days_remaining": 11}
        )
        self.assertEqual(budget, 0)

    def test_stable_entrypoint_routes_to_v5(self):
        source = (SCRIPTS / "supplement_indeed_web_index.py").read_text(encoding="utf-8")
        self.assertIn("supplement_indeed_web_index_v5", source)
        self.assertEqual(boost.INDEX_VERSION, 5)

    def test_fast_refresh_is_manual_only_to_avoid_double_provider_spend(self):
        source = (ROOT / ".github/workflows/fast-indeed-refresh.yml").read_text(encoding="utf-8")
        self.assertIn("on:\n  workflow_dispatch:", source)
        self.assertNotIn("\n  pull_request:\n", source)
        self.assertNotIn("\n  push:\n    branches:", source)
        self.assertNotIn("python scripts/acquisition_precision.py", source)
        self.assertIn("python scripts/supplement_indeed_web_index.py", source)

    def test_v5_never_requests_indeed_backend(self):
        source = (SCRIPTS / "supplement_indeed_web_index_v5.py").read_text(encoding="utf-8")
        self.assertNotIn('urllib.request.Request("https://jp.indeed.com', source)
        self.assertIn("candidate_indeed_index_nested_result_links_scanned", source)


if __name__ == "__main__":
    unittest.main()
