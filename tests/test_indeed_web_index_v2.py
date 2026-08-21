import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

path = SCRIPTS / "supplement_indeed_web_index_v2.py"
spec = importlib.util.spec_from_file_location("indeed_web_index_v2_test", path)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class IndeedWebIndexV2Tests(unittest.TestCase):
    def test_no_result_provider_message_is_valid_empty_search(self):
        got = mod.normalize_provider_payload(
            {"error": "Google hasn't returned any results for this query."}
        )
        self.assertEqual(got["organic_results"], [])
        self.assertTrue(got["_indeed_index_no_results"])

    def test_real_provider_error_still_fails_closed(self):
        with self.assertRaises(RuntimeError):
            mod.normalize_provider_payload({"error": "Invalid API key"})

    def test_queries_are_short_direct_viewjob_searches(self):
        self.assertGreaterEqual(len(mod.SEARCH_PROFILES), 6)
        for name, query in mod.SEARCH_PROFILES:
            self.assertIn("site:jp.indeed.com/viewjob", query, name)
            self.assertNotIn(" OR ", query, name)
            self.assertLess(len(query), 120, name)

    def test_request_budget_uses_only_monthly_surplus(self):
        payload = {
            "serpapi_requests_month": 220,
            "serpapi_monthly_request_cap": 245,
            "serpapi_month_days_remaining": 12,
        }
        budget, used, cap, surplus = mod.request_budget(payload)
        self.assertEqual((used, cap, surplus), (220, 245, 3))
        self.assertEqual(budget, 2)

        no_surplus = dict(payload, serpapi_requests_month=223)
        budget, _, _, surplus = mod.request_budget(no_surplus)
        self.assertEqual(surplus, 0)
        self.assertEqual(budget, 0)

    def test_search_uses_google_japan_without_indeed_backend_request(self):
        source = path.read_text(encoding="utf-8")
        self.assertIn('"google_domain": "google.co.jp"', source)
        self.assertIn('"engine": "google"', source)
        self.assertIn('"https://serpapi.com/search.json?"', source)
        self.assertNotIn('urllib.request.Request("https://jp.indeed.com', source)
        self.assertIn('candidate_indeed_index_direct_indeed_requests', source)


if __name__ == "__main__":
    unittest.main()
