import importlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

mod = importlib.import_module("supplement_official_ai_providers")


OUTLIER_TEXT = (
    "Japanese AI Training remote apply. Work independently on your own schedule. "
    "Evaluate and rank AI responses, write prompts, fact-check answers, label data, "
    "perform annotation and structured quality evaluation in Japanese."
)
ONEFORMA_TEXT = (
    "Japanese Japan Remote Open Accepting applications. Apply to this project. "
    "Complete data annotation and evaluation tasks, labeling, classification, "
    "search relevance evaluation and structured AI response quality review."
)


class OfficialAIProviderSupplyTests(unittest.TestCase):
    def setUp(self):
        mod.acquisition._production_quality_policy_configured = False
        mod.acquisition._production_remote_policy_configured = False
        mod.acquisition.build_row = mod.acquisition_precision._ORIGINAL_ACQUISITION_BUILD_ROW
        mod.acquisition.legacy.score_job = mod.acquisition_quality.GENERIC_SCORE_JOB

    def test_live_outlier_page_uses_existing_strict_builder_without_serpapi(self):
        pages = {"outlier-japanese": OUTLIER_TEXT}
        out = mod.supplement({"jobs": []}, {}, fetched_pages=pages)
        self.assertFalse(out["candidate_direct_official_uses_serpapi"])
        self.assertTrue(out["candidate_direct_official_quality_gate_unchanged"])
        self.assertGreaterEqual(out["candidate_direct_official_deterministic_accepted"], 1)
        rows = [row for row in out["jobs"] if row.get("official_provider") == "Outlier"]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["discovery_source"], "official-provider-page")
        self.assertEqual(row["quality_gate"], "async-ai-remote-v2")
        self.assertEqual(row["autonomy_attention_risk"], "low")
        self.assertIsNot(row.get("remote_search_only"), True)
        self.assertEqual(row["apply_source"], "Outlier")
        self.assertEqual(row["apply_source_kind"], "trusted-provider")

    def test_oneforma_requires_current_japan_remote_open_signals(self):
        spec = next(x for x in mod.SOURCES if x.key == "oneforma-intent-japan")
        self.assertTrue(mod._live_text(spec, ONEFORMA_TEXT))
        self.assertFalse(mod._live_text(spec, ONEFORMA_TEXT.replace("Japan", "")))
        self.assertFalse(mod._live_text(spec, ONEFORMA_TEXT.replace("Accepting applications", "Not accepting applications")))

    def test_physical_media_participation_is_rejected_before_builder(self):
        spec = next(x for x in mod.SOURCES if x.key == "oneforma-intent-japan")
        self.assertFalse(mod._live_text(spec, ONEFORMA_TEXT + " You must record your voice."))
        self.assertFalse(mod._live_text(spec, ONEFORMA_TEXT + " Join a live video call."))

    def test_multiple_live_official_pages_remain_distinct_jobs(self):
        pages = {
            "outlier-japanese": OUTLIER_TEXT,
            "oneforma-intent-japan": ONEFORMA_TEXT,
            "oneforma-uhrs-japan": ONEFORMA_TEXT,
        }
        out = mod.supplement({"jobs": []}, {}, fetched_pages=pages)
        ids = [row.get("id") for row in out["jobs"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreaterEqual(out["candidate_direct_official_deterministic_accepted"], 3)
        self.assertEqual(out["candidate_direct_official_accepted_by_provider"].get("OneForma"), 2)

    def test_pre_final_target_skips_network_work(self):
        existing = [{"id": f"existing-{i}"} for i in range(120)]
        out = mod.supplement({"jobs": existing}, {}, fetched_pages={})
        self.assertEqual(len(out["jobs"]), 120)
        self.assertEqual(out["candidate_direct_official_skipped"], "pool-at-or-above-pre-final-target")
        self.assertTrue(out["candidate_direct_official_stock_ready"])


if __name__ == "__main__":
    unittest.main()
