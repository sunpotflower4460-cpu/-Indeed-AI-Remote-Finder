import importlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

stamp = importlib.import_module("stamp_free_ats_refresh")


class FreeATSRefillWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = (ROOT / ".github/workflows/free-ats-refill.yml").read_text(encoding="utf-8")
        cls.wrapper = (ROOT / "scripts" / "supplement_targeted_public_ats_buffered.py").read_text(encoding="utf-8")

    def test_runs_four_times_daily_without_serpapi(self):
        self.assertIn("cron: '17 */6 * * *'", self.workflow)
        self.assertIn("supplement_targeted_public_ats_buffered.py", self.workflow)
        self.assertIn("120-row pre-final buffer", self.workflow)
        self.assertNotIn("SERPAPI_KEY", self.workflow)
        self.assertNotIn("acquisition_precision.py", self.workflow)

    def test_wrapper_includes_direct_provider_and_ats_sources(self):
        self.assertIn("supplement_official_ai_providers", self.wrapper)
        self.assertIn("supplement_official_japan_depth", self.wrapper)
        self.assertIn("supplement_rws_trainai", self.wrapper)
        self.assertIn("supplement_targeted_public_ats", self.wrapper)
        self.assertIn("PRE_FINAL_BUFFER_TARGET = 120", self.wrapper)

    def test_uses_same_final_quality_and_trusted_validators(self):
        for marker in (
            "apply_llm_quality_gate.py",
            "apply_ai_tool_policy_gate.py",
            "validate_feed_trusted.py",
            "validate_remote_feed.py",
        ):
            self.assertIn(marker, self.workflow)
        self.assertIn("group: update-job-candidates", self.workflow)

    def test_stamp_marks_refresh_as_expanded_official_sources_only(self):
        out = stamp.stamp({"jobs": [{"id": "a"}, {"id": "b"}]})
        self.assertEqual(out["candidate_pool_size"], 2)
        self.assertFalse(out["candidate_free_ats_refresh_uses_serpapi"])
        self.assertEqual(out["candidate_free_ats_refresh_mode"], "official-sources-only")
        self.assertEqual(out["candidate_free_ats_refresh_version"], 3)
        self.assertTrue(out["candidate_free_official_refresh"])
        self.assertEqual(
            out["candidate_free_official_source_layers"],
            [
                "public-employer-ats",
                "targeted-public-employer-ats",
                "official-provider-page",
                "official-provider-page-japan-depth",
                "rws-trainai-lever",
            ],
        )
        self.assertTrue(out["generated_at"])


if __name__ == "__main__":
    unittest.main()
