import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

index_path = SCRIPTS / "supplement_indeed_web_index.py"
implementation_path = SCRIPTS / "supplement_indeed_web_index_v2.py"
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
            "https://jp.indeed.com/q-ai-%E6%B1%82%E4%BA%BA.html?vjk=abcDEF_123",
            "https://example.com/viewjob?jk=abcdef",
            "http://jp.indeed.com/viewjob?jk=abcdef",
            "https://jp.indeed.com/viewjob?jk=x",
        ):
            self.assertIsNone(index_mod.canonical_indeed_url(bad), bad)

    def test_public_index_reference_accepts_search_vjk_as_job_key_only(self):
        got = index_mod.indexed_indeed_reference(
            "https://jp.indeed.com/q-ai-%E5%9C%A8%E5%AE%85-%E6%B1%82%E4%BA%BA.html?vjk=ABCDEF123456&from=web"
        )
        self.assertEqual(
            got,
            (
                "https://jp.indeed.com/viewjob?jk=ABCDEF123456",
                "ABCDEF123456",
                "search-vjk",
            ),
        )

    def test_google_index_results_keep_direct_and_vjk_truth_levels_separate(self):
        seeds = index_mod.extract_seeds(
            {
                "organic_results": [
                    {
                        "title": "Japanese AI Rater - job post - Indeed",
                        "link": "https://jp.indeed.com/viewjob?jk=ABCDEF123456&from=search",
                        "snippet": "完全在宅 AI評価 日本語",
                    },
                    {
                        "title": "AIトレーナー 在宅の求人 - Indeed",
                        "link": "https://jp.indeed.com/q-ai-%E6%B1%82%E4%BA%BA.html?vjk=VJKKEY123456",
                        "snippet": "検索結果ページの抜粋",
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
        self.assertEqual(len(seeds), 2)
        by_kind = {seed["indeed_index_link_kind"]: seed for seed in seeds}

        direct = by_kind["viewjob-jk"]
        self.assertEqual(direct["jk"], "ABCDEF123456")
        self.assertEqual(direct["title"], "Japanese AI Rater")
        self.assertEqual(direct["url"], "https://jp.indeed.com/viewjob?jk=ABCDEF123456")
        self.assertTrue(direct["indeed_exact_url_verified"])
        self.assertTrue(direct["indeed_job_title_verified"])
        self.assertTrue(direct["indeed_promotion_eligible"])
        self.assertFalse(direct["indeed_page_body_verified"])

        vjk = by_kind["search-vjk"]
        self.assertEqual(vjk["jk"], "VJKKEY123456")
        self.assertEqual(vjk["url"], "https://jp.indeed.com/viewjob?jk=VJKKEY123456")
        self.assertEqual(vjk["title"], "")
        self.assertEqual(vjk["indexed_page_title"], "AIトレーナー 在宅の求人")
        self.assertTrue(vjk["indeed_job_key_verified"])
        self.assertFalse(vjk["indeed_job_title_verified"])
        self.assertFalse(vjk["indeed_exact_url_verified"])
        self.assertTrue(vjk["indeed_canonical_url_derived_from_vjk"])
        self.assertFalse(vjk["indeed_promotion_eligible"])
        self.assertFalse(vjk["indeed_page_body_verified"])

    def test_strong_direct_match_is_promoted_and_original_target_is_preserved(self):
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
                "last_seen": "2026-08-21T00:00:00+00:00",
                "indeed_index_link_kind": "viewjob-jk",
                "indeed_promotion_eligible": True,
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
        self.assertTrue(row["indeed_exact_url_verified"])
        self.assertFalse(row["indeed_page_body_verified"])
        self.assertEqual(row["indeed_content_screening_basis"], "separate-screened-source")
        self.assertGreaterEqual(row["indeed_index_match_score"], index_mod.MATCH_THRESHOLD)

    def test_vjk_seed_cannot_promote_even_if_other_text_looks_similar(self):
        payload = {
            "jobs": [
                {
                    "id": "old-id",
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
                "title": "Japanese AI Rater",
                "snippet": "Example AI 完全在宅",
                "indeed_index_link_kind": "search-vjk",
                "indeed_promotion_eligible": False,
            }
        ]
        self.assertEqual(index_mod.promote_matches(payload, seeds), 0)
        self.assertEqual(payload["jobs"][0]["id"], "old-id")
        self.assertNotEqual(payload["jobs"][0].get("apply_source_kind"), "indeed")

    def test_unrelated_direct_index_hit_cannot_promote_candidate(self):
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
                "indeed_index_link_kind": "viewjob-jk",
                "indeed_promotion_eligible": True,
            }
        ]
        self.assertEqual(index_mod.promote_matches(payload, seeds), 0)
        self.assertNotEqual(payload["jobs"][0].get("apply_source_kind"), "indeed")

    def test_index_queries_cover_both_public_index_surfaces_without_direct_requests(self):
        direct = 0
        vjk = 0
        for name, query in index_mod.SEARCH_PROFILES:
            if name.startswith("search-vjk-"):
                self.assertIn("site:jp.indeed.com/q-", query, name)
                self.assertIn("inurl:vjk", query, name)
                vjk += 1
            else:
                self.assertIn("site:jp.indeed.com/viewjob", query, name)
                direct += 1
        self.assertGreaterEqual(direct, 20)
        self.assertGreaterEqual(vjk, 6)
        source = implementation_path.read_text(encoding="utf-8")
        self.assertIn('"engine": "google"', source)
        self.assertIn('"https://serpapi.com/search.json?"', source)
        self.assertIn('candidate_indeed_index_direct_indeed_requests', source)
        self.assertNotIn('urllib.request.Request("https://jp.indeed.com', source)

    def test_structured_search_seed_reuse_skips_unverified_vjk_title(self):
        previous = {
            "serpapi_rotation_cursor": 2,
            "candidate_indeed_index_seeds": [
                {
                    "jk": "VJKKEY123456",
                    "title": "",
                    "indeed_index_link_kind": "search-vjk",
                    "indeed_exact_url_verified": False,
                },
                {
                    "jk": "ABCDEF123456",
                    "title": "Japanese AI Rater",
                    "indeed_index_link_kind": "viewjob-jk",
                    "indeed_exact_url_verified": True,
                },
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
