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

import indeed_index_core as core  # noqa: E402


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

    def test_queries_cover_current_remote_ai_role_wording(self):
        self.assertGreaterEqual(len(mod.SEARCH_PROFILES), 30)
        names={name for name,_ in mod.SEARCH_PROFILES}
        for expected in (
            "ai-trainer","ai-evaluation","senior-rater","quality-assurance-rater",
            "rater","annotation","data-labeling","ai-data","data-entry",
            "translation","proofreading","bilingual-editor","transcription","research",
            "fact-check","search-quality","content-review","chatbot-training",
            "generative-ai-review","llm-evaluation","qa-testing","telus-rater",
            "dataannotation",
        ):
            self.assertIn(expected,names)
        for name, query in mod.SEARCH_PROFILES:
            self.assertIn("site:jp.indeed.com/viewjob", query, name)
            self.assertNotIn(" OR ", query, name)
            self.assertLess(len(query), 120, name)

    def test_one_provider_request_asks_for_more_index_results(self):
        self.assertEqual(mod.RESULTS_PER_QUERY,20)
        source=path.read_text(encoding="utf-8")
        self.assertIn('"num": RESULTS_PER_QUERY',source)
        self.assertGreaterEqual(core.MAX_SEEDS,80)

    def test_request_budget_reserves_one_structured_search_per_future_day(self):
        self.assertEqual(core.BASELINE_REQUESTS_PER_DAY,1)
        payload = {
            "serpapi_requests_month": 220,
            "serpapi_monthly_request_cap": 245,
            "serpapi_month_days_remaining": 12,
        }
        budget, used, cap, surplus = mod.request_budget(payload)
        self.assertEqual((used, cap, surplus), (220, 245, 14))
        self.assertEqual(budget, 2)

        no_surplus = dict(payload, serpapi_requests_month=234)
        budget, _, _, surplus = mod.request_budget(no_surplus)
        self.assertEqual(surplus, 0)
        self.assertEqual(budget, 0)

    def test_profile_coverage_is_persisted_in_payload(self):
        source=path.read_text(encoding="utf-8")
        for needle in (
            "candidate_indeed_index_profile_last_attempt",
            "candidate_indeed_index_profile_last_success",
            "candidate_indeed_index_profile_coverage_count",
            "candidate_indeed_index_unseen_profiles",
        ):
            self.assertIn(needle,source)

    def test_truth_metadata_explicitly_says_indeed_body_is_not_fetched(self):
        source=path.read_text(encoding="utf-8")
        self.assertIn('candidate_indeed_page_body_directly_accessed',source)
        self.assertIn('False',source)
        self.assertIn('backend does not fetch Indeed job-page bodies',source)

    def test_search_uses_google_japan_without_indeed_backend_request(self):
        source = path.read_text(encoding="utf-8")
        self.assertIn('"google_domain": "google.co.jp"', source)
        self.assertIn('"engine": "google"', source)
        self.assertIn('"https://serpapi.com/search.json?"', source)
        self.assertNotIn('urllib.request.Request("https://jp.indeed.com', source)
        self.assertIn('candidate_indeed_index_direct_indeed_requests', source)


if __name__ == "__main__":
    unittest.main()
