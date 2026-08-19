import importlib.util
import sys
import unittest
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "scripts" / "validate_remote_feed.py"
spec = importlib.util.spec_from_file_location("validate_remote_feed", path)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def row(tier="high", reasons=None):
    return {
        "id": "abc123",
        "tier": tier,
        "remote_reasons": list(reasons or ["完全在宅"]),
    }


class RemoteFeedValidationTests(unittest.TestCase):
    def test_high_requires_explicit_full_remote_reason(self):
        errors = mod.validate({"jobs": [row(reasons=["勤務地自由"])]})
        self.assertTrue(any("lacks explicit full-remote" in value for value in errors))

    def test_remote_warning_is_never_publishable(self):
        errors = mod.validate(
            {"jobs": [row(reasons=["フルリモート", "注意:週2出社"])]}
        )
        self.assertTrue(any("contradictory remote signal" in value for value in errors))

    def test_clean_high_row_passes(self):
        self.assertEqual(mod.validate({"jobs": [row()]}), [])

    def test_review_does_not_need_explicit_full_remote_reason(self):
        self.assertEqual(
            mod.validate({"jobs": [row(tier="review", reasons=["在宅勤務"])]}), []
        )

    def test_malformed_job_counter_is_nonnegative(self):
        errors = mod.validate({"jobs": [], "malformed_jobs": -1})
        self.assertIn("malformed_jobs must be a non-negative integer", errors)


if __name__ == "__main__":
    unittest.main()
