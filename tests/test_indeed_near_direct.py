import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

index_path = SCRIPTS / "supplement_indeed_web_index.py"
index_spec = importlib.util.spec_from_file_location("indeed_web_index_test", index_path)
index_mod = importlib.util.module_from_spec(index_spec)
sys.modules[index_spec.name] = index_mod
index_spec.loader.exec_module(index_mod)

import acquisition_precision as precision  # noqa: E402


class IndeedNearDirectTests(unittest.TestCase):
    def test_only_exact_viewjob_jk_is_canonical_indeed(self):
        self.assertEqual(
            index_mod.canonical_indeed_url(
                "https://jp.indeed.com/viewjob?jk=abcDEF_123&utm_source=test"
            ),
            ("https://jp.indeed.com/viewjob?jk=abcDEF_123", "abcDEF_123"),
        )
        for bad in (
            "https://jp.indeed.com/jobs?q=remote",
            "https://example.com/viewjob?jk=abcdef",
            "http://jp.indeed.com/viewjob?jk=abcdef",
            "https://jp.indeed.com/viewjob?jk=x",
        ):
            self.assertIsNone(index_mod.canonical_indeed_url(bad), bad)

    def test_google_index_results_keep_only_real_indeed_viewjobs(self):
        seeds = index_mod.extract_seeds(
            {
                "organic_results": [
                    {
                        "title": "Japanese AI Rater - job post - Indeed",
                        "link": "https://jp.indeed.com/viewjob?jk=ABCDEF123456&from=search",
                        "snippet": "完全在宅 AI評価 日本語",
                    },
                    {
                        "title": "Search results",
                        "link": "https://jp.indeed.com/jobs?q=AI",
                    },
                    {
                        "title": "Other site",
                        "link": "https://example.com/viewjob?jk=ABCDEF123456",
                    },
                ]
            },
            "ai-evaluation",
        )
        self.assertEqual(len(seeds), 1)
        self.assertEqual(seeds[0]["jk"], "ABCDEF123456")
        self.assertEqual(seeds[0]["title"], "Japanese AI Rater")
        self.assertEqual(seeds[0]["url"], "https://jp.indeed.com/viewjob?jk=ABCDEF123456")

    def test_strong_structured_match_is_promoted_and_original_target_is_preserved(self):
        payload = {
            "jobs": [
                {
                    "id": "old-id",
                    "title": "Japanese AI Rater",
                    "company": "Example AI",
                    "url": "https://jobs.example.com/japanese-ai-rater",
                    "apply_source": "Greenhouse",
                    "apply_source_kind": "trusted-ats",
                }
            ]
        }
        seeds = [
            {
                "jk": "ABCDEF123456",
                "url": "https://jp.indeed.com/viewjob?jk=ABCDEF123456",
                "title": "Japanese AI Rater",
                "snippet": "Example AI 完全在宅",
            }
        ]
        self.assertEqual(index_mod.promote_matches(payload, seeds), 1)
        row = payload["jobs"][0]
        self.assertEqual(row["id"], "ABCDEF123456")
        self.assertEqual(row["original_candidate_id"], "old-id")
        self.assertEqual(row["apply_source"], "Indeed")
        self.assertEqual(row["apply_source_kind"], "indeed")
        self.assertEqual(row["url"], "https://jp.indeed.com/viewjob?jk=ABCDEF123456")
        self.assertEqual(row["original_apply_source"], "Greenhouse")
        self.assertEqual(row["original_apply_url"], "https://jobs.example.com/japanese-ai-rater")
        self.assertGreaterEqual(row["indeed_index_match_score"], index_mod.MATCH_THRESHOLD)

    def test_unrelated_index_hit_cannot_promote_candidate(self):
        payload = {
            "jobs": [
                {
                    "title": "Japanese AI Rater",
                    "company": "Example AI",
                    "url": "https://jobs.example.com/rater",
                    "apply_source_kind": "trusted-ats",
                }
            ]
        }
        seeds = [
            {
                "jk": "ABCDEF123456",
                "url": "https://jp.indeed.com/viewjob?jk=ABCDEF123456",
                "title": "Senior Mechanical Engineer",
                "snippet": "Different Company onsite factory",
            }
        ]
        self.assertEqual(index_mod.promote_matches(payload, seeds), 0)
        self.assertNotEqual(payload["jobs"][0].get("apply_source_kind"), "indeed")

    def test_index_queries_target_indeed_viewjob_without_requesting_indeed_pages(self):
        for name, query in index_mod.SEARCH_PROFILES:
            self.assertIn("site:jp.indeed.com/viewjob", query, name)
        source = index_path.read_text(encoding="utf-8")
        self.assertIn('"engine": "google"', source)
        self.assertIn('"https://serpapi.com/search.json?"', source)
        self.assertIn('candidate_indeed_index_direct_indeed_requests', source)
        self.assertNotIn('urllib.request.Request("https://jp.indeed.com', source)

    def test_index_seed_is_inserted_at_the_next_rotation_cursor(self):
        previous = {
            "serpapi_rotation_cursor": 2,
            "candidate_indeed_index_seeds": [
                {"jk": "ABCDEF123456", "title": "Japanese AI Rater"}
            ],
        }
        seed = precision._indeed_index_seed_profile(previous)
        self.assertEqual(seed[0], "indeed_index_seed_ABCDEF123456")
        rows = [("a", "A"), ("b", "B"), ("c", "C"), ("d", "D")]
        got = precision._insert_at_next_rotation(rows, seed, previous)
        self.assertEqual(got[2], seed)

    def test_update_workflow_runs_index_match_before_postprocess(self):
        workflow = (ROOT / ".github/workflows/update-jobs.yml").read_text(encoding="utf-8")
        index_step = workflow.index("python scripts/supplement_indeed_web_index.py --previous /tmp/previous-jobs.json")
        postprocess = workflow.index("python scripts/postprocess_feed.py --previous /tmp/previous-jobs.json")
        self.assertLess(index_step, postprocess)
        self.assertIn("SERPAPI_KEY: ${{ secrets.SERPAPI_KEY }}", workflow)


if __name__ == "__main__":
    unittest.main()
