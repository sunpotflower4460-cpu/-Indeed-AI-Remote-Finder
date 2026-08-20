import importlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

mod = importlib.import_module("supplement_oneforma_catalog")

INDEX = """
<html><body>
<a href="/projects/japanese-search-evaluation-annotator/">good</a>
<a href="https://www.oneforma.com/projects/japanese-search-evaluation-annotator/">duplicate</a>
<a href="/projects/first-person-video-japan/">physical</a>
<a href="/projects/german-search-rater/">foreign</a>
<a href="https://example.com/projects/not-allowed/">external</a>
</body></html>
"""

GOOD_URL = "https://www.oneforma.com/projects/japanese-search-evaluation-annotator/"
PHYSICAL_URL = "https://www.oneforma.com/projects/first-person-video-japan/"
FOREIGN_URL = "https://www.oneforma.com/projects/german-search-rater/"

GOOD_DETAIL = """
<html><body><h1>Japanese Search Evaluation Annotator</h1>
<p>Open and Accepting applications. Apply to this project.</p>
<p>This is a Remote project available in Japan. Language: Japanese - Japan.</p>
<p>Work independently on flexible asynchronous tasks. Review and evaluate search results,
annotate and label text data, compare AI responses, apply quality guidelines, check relevance,
classify results, and provide structured written quality feedback. No calls, meetings, customer
support, or live collaboration are required. The work is fully remote and completed online.</p>
</body></html>
"""

PHYSICAL_DETAIL = """
<html><body><h1>Japanese First-Person Video Data Collection</h1>
<p>Accepting applications. Apply to this project. Remote. Available in Japan. Japanese - Japan.</p>
<p>First-person video data collection. Record video of yourself and capture photos of yourself.</p>
</body></html>
"""

FOREIGN_DETAIL = """
<html><body><h1>German Search Evaluation Rater</h1>
<p>Accepting applications. Apply to this project. Remote. Available in Germany. German.</p>
<p>Search evaluation, annotation and quality rating.</p>
</body></html>
"""


class OneFormaCatalogSupplyTests(unittest.TestCase):
    def setUp(self):
        mod.acquisition._production_quality_policy_configured = False
        mod.acquisition._production_remote_policy_configured = False
        mod.acquisition.build_row = mod.acquisition_precision._ORIGINAL_ACQUISITION_BUILD_ROW
        mod.acquisition.legacy.score_job = mod.acquisition_quality.GENERIC_SCORE_JOB

    def test_discovery_is_bounded_deduplicated_and_oneforma_only(self):
        pages = {url: INDEX for url in mod.INDEX_URLS}
        urls = mod.discover_urls(pages)
        self.assertIn(GOOD_URL, urls)
        self.assertIn(PHYSICAL_URL, urls)
        self.assertIn(FOREIGN_URL, urls)
        self.assertEqual(urls.count(GOOD_URL), 1)
        self.assertTrue(all("oneforma.com" in value for value in urls))
        self.assertLessEqual(len(urls), mod.MAX_DISCOVERED_PAGES)

    def test_japan_remote_digital_role_uses_existing_strict_builder(self):
        index_pages = {url: INDEX for url in mod.INDEX_URLS}
        detail_pages = {
            GOOD_URL: GOOD_DETAIL,
            PHYSICAL_URL: PHYSICAL_DETAIL,
            FOREIGN_URL: FOREIGN_DETAIL,
        }
        out = mod.supplement(
            {"jobs": []},
            {},
            index_pages=index_pages,
            detail_pages=detail_pages,
        )
        self.assertFalse(out["candidate_oneforma_catalog_uses_serpapi"])
        self.assertTrue(out["candidate_oneforma_catalog_quality_gate_unchanged"])
        self.assertEqual(out["candidate_oneforma_catalog_deterministic_accepted"], 1)
        self.assertEqual(len(out["jobs"]), 1)
        row = out["jobs"][0]
        self.assertEqual(row["official_provider"], "OneForma")
        self.assertEqual(row["discovery_source"], "official-provider-page")
        self.assertEqual(row["quality_policy_version"], 2)
        self.assertEqual(row["quality_gate"], "async-ai-remote-v2")
        self.assertEqual(row["autonomy_attention_risk"], "low")
        self.assertIsNot(row.get("remote_search_only"), True)
        self.assertEqual(row["apply_source"], "OneForma")
        self.assertEqual(row["apply_source_kind"], "trusted-provider")

    def test_physical_self_data_collection_is_rejected(self):
        self.assertFalse(mod._live_candidate(mod._page_text(PHYSICAL_DETAIL)))

    def test_foreign_only_remote_project_is_rejected(self):
        self.assertFalse(mod._live_candidate(mod._page_text(FOREIGN_DETAIL)))

    def test_pre_final_target_skips_catalog_work(self):
        existing = [{"id": f"existing-{i}"} for i in range(120)]
        out = mod.supplement({"jobs": existing}, {}, index_pages={}, detail_pages={})
        self.assertEqual(len(out["jobs"]), 120)
        self.assertEqual(out["candidate_oneforma_catalog_skipped"], "pool-at-or-above-pre-final-target")


if __name__ == "__main__":
    unittest.main()
