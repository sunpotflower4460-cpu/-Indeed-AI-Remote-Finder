import importlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

mod = importlib.import_module("supplement_rws_trainai")
targeted = importlib.import_module("supplement_targeted_public_ats")


def rws_japanese(index: int = 1) -> dict:
    return {
        "id": f"rws-jp-{index}",
        "text": f"AI Data Specialist - Japanese {index}",
        "workplaceType": "remote",
        "categories": {"location": "Tokyo", "allLocations": ["Tokyo"]},
        "descriptionPlain": (
            "Work from home on flexible Japanese AI data projects. Data collection, evaluation, "
            "annotation and labeling are core tasks. Perform pairwise comparisons, rate model "
            "responses, check relevance and quality, and submit structured ratings independently "
            "online. Japanese fluency required."
        ),
        "applyUrl": f"https://jobs.lever.co/rws/rws-jp-{index}",
    }


class RWSTrainAISupplyTests(unittest.TestCase):
    def setUp(self):
        targeted.acquisition._production_quality_policy_configured = False
        targeted.acquisition._production_remote_policy_configured = False
        targeted.acquisition.build_row = targeted.acquisition_precision._ORIGINAL_ACQUISITION_BUILD_ROW
        targeted.acquisition.legacy.score_job = targeted.acquisition_quality.GENERIC_SCORE_JOB

    def test_location_queries_are_bounded_and_use_official_lever_api(self):
        seen = []
        original = mod.base._fetch_json
        try:
            def fake(url, **kwargs):
                seen.append(url)
                return [rws_japanese()]
            mod.base._fetch_json = fake
            rows, stats = mod._fetch_rws_japan()
        finally:
            mod.base._fetch_json = original
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(seen), 2)
        self.assertTrue(all("api.lever.co/v0/postings/rws" in url for url in seen))
        self.assertTrue(any("location=Tokyo" in url for url in seen))
        self.assertTrue(any("location=Japan" in url for url in seen))
        self.assertEqual(stats["raw_tokyo"], 1)

    def test_rws_row_uses_existing_strict_builder_and_no_serpapi(self):
        out = mod.supplement({"jobs": []}, {}, posts=[rws_japanese()])
        self.assertFalse(out["candidate_rws_trainai_uses_serpapi"])
        self.assertTrue(out["candidate_rws_trainai_quality_gate_unchanged"])
        self.assertGreaterEqual(out["candidate_rws_trainai_deterministic_accepted"], 1)
        self.assertGreaterEqual(len(out["jobs"]), 1)
        row = out["jobs"][0]
        self.assertEqual(row["ats_provider"], "RWS TrainAI")
        self.assertEqual(row["discovery_source"], "targeted-public-employer-ats")
        self.assertEqual(row["quality_gate"], "async-ai-remote-v2")
        self.assertEqual(row["autonomy_attention_risk"], "low")
        self.assertIsNot(row.get("remote_search_only"), True)
        self.assertTrue(str(row.get("url", "")).startswith("https://jobs.lever.co/rws/"))

    def test_rws_stops_network_work_at_pre_final_target(self):
        existing = [{"id": f"existing-{i}"} for i in range(120)]
        out = mod.supplement({"jobs": existing}, {}, posts=[rws_japanese()])
        self.assertEqual(len(out["jobs"]), 120)
        self.assertEqual(out["candidate_rws_trainai_skipped"], "pool-at-or-above-pre-final-target")
        self.assertTrue(out["candidate_rws_trainai_pre_final_ready"])


if __name__ == "__main__":
    unittest.main()
