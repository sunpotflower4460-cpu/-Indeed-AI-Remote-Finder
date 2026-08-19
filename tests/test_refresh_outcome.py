import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

path = SCRIPTS / "stamp_refresh_outcome.py"
spec = importlib.util.spec_from_file_location("stamp_refresh_outcome_test", path)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class RefreshOutcomeTests(unittest.TestCase):
    def test_normalizes_only_known_github_step_outcomes(self):
        for value in ("success", "failure", "cancelled", "skipped"):
            self.assertEqual(mod.normalize_outcome(value), value)
        self.assertEqual(mod.normalize_outcome("anything else"), "unknown")
        self.assertEqual(mod.normalize_outcome(None), "unknown")

    def test_failure_preserves_existing_feed_and_marks_previous_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = Path(tmp) / "jobs.json"
            original = {
                "generated_at": "2026-08-19T13:32:05+00:00",
                "jobs": [{"id": "abc123", "title": "existing"}],
                "provider_configured": True,
            }
            feed.write_text(json.dumps(original), encoding="utf-8")
            got = mod.stamp(feed, outcome="failure")
            self.assertEqual(got["jobs"], original["jobs"])
            self.assertEqual(got["generated_at"], original["generated_at"])
            self.assertEqual(got["candidate_acquisition_outcome"], "failure")
            self.assertTrue(got["candidate_refresh_preserved_previous_feed"])
            self.assertEqual(got["candidate_refresh_pipeline_version"], 1)
            self.assertIn("candidate_refresh_attempted_at", got)

    def test_success_does_not_claim_previous_feed_was_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = Path(tmp) / "jobs.json"
            feed.write_text(json.dumps({"jobs": []}), encoding="utf-8")
            got = mod.stamp(feed, outcome="success")
            self.assertEqual(got["candidate_acquisition_outcome"], "success")
            self.assertFalse(got["candidate_refresh_preserved_previous_feed"])


if __name__ == "__main__":
    unittest.main()
