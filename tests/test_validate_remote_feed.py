import importlib.util
import sys
import unittest
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "scripts" / "validate_remote_feed.py"
spec = importlib.util.spec_from_file_location("validate_remote_feed", path)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def row(tier="high", reasons=None, tags=None, remote_search_only=None):
    value = {
        "id": "abc123",
        "tier": tier,
        "remote_reasons": list(reasons or ["完全在宅"]),
        "tags": list(tags or []),
    }
    if remote_search_only is not None:
        value["remote_search_only"] = remote_search_only
    return value


class RemoteFeedValidationTests(unittest.TestCase):
    def test_high_requires_explicit_full_remote_reason(self):
        errors = mod.validate({"jobs": [row(reasons=["勤務地自由"])]})
        self.assertTrue(any("lacks explicit full-remote" in value for value in errors))

    def test_remote_warning_is_never_publishable(self):
        errors = mod.validate({"jobs": [row(reasons=["フルリモート", "注意:週2出社"])]})
        self.assertTrue(any("contradictory remote signal" in value for value in errors))

    def test_clean_high_row_passes(self):
        self.assertEqual(mod.validate({"jobs": [row()]}), [])

    def test_review_does_not_need_explicit_full_remote_reason(self):
        self.assertEqual(mod.validate({"jobs": [row(tier="review", reasons=["在宅勤務"])]}), [])

    def test_remote_search_only_must_be_review_and_labeled(self):
        errors = mod.validate({
            "jobs": [row(tier="review", reasons=["Google Jobs:在宅勤務フィルタ"], remote_search_only=True)]
        })
        self.assertTrue(any("must show 在宅要確認" in value for value in errors))

        errors = mod.validate({
            "jobs": [row(tier="high", reasons=["完全在宅"], tags=["在宅要確認"], remote_search_only=True)]
        })
        self.assertTrue(any("must be review tier" in value for value in errors))

    def test_labeled_remote_search_only_review_passes(self):
        value = row(
            tier="review",
            reasons=["Google Jobs:在宅勤務フィルタ", "検索条件:在宅候補（完全在宅は本文要確認）"],
            tags=["在宅要確認"],
            remote_search_only=True,
        )
        self.assertEqual(mod.validate({"jobs": [value]}), [])

    def test_malformed_job_counter_is_nonnegative(self):
        errors = mod.validate({"jobs": [], "malformed_jobs": -1})
        self.assertIn("malformed_jobs must be a non-negative integer", errors)


if __name__ == "__main__":
    unittest.main()
