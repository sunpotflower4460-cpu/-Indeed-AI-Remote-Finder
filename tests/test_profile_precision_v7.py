import importlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

mod = importlib.import_module("profile_precision_v7")
core = importlib.import_module("profile_precision")


class ProfilePrecisionV7Tests(unittest.TestCase):
    def test_successful_empty_search_gets_bounded_penalty(self):
        key = "source_ai_rater_japanese_en_remote"
        no_empty = {key: {"search_attempts": 1.0, "zero_result_attempts": 0.0}}
        one_empty = {key: {"search_attempts": 1.0, "zero_result_attempts": 1.0}}
        self.assertLess(mod.precision_score(key, one_empty), mod.precision_score(key, no_empty))
        self.assertGreater(mod.precision_score(key, one_empty), mod.precision_score(key, no_empty) - 25.0)

    def test_repeated_empty_searches_penalize_more_than_one_empty_search(self):
        key = "source_ai_rater_japanese_en_remote"
        one = {key: {"search_attempts": 1.0, "zero_result_attempts": 1.0}}
        repeated = {key: {"search_attempts": 4.0, "zero_result_attempts": 4.0}}
        self.assertLess(mod.precision_score(key, repeated), mod.precision_score(key, one))

    def test_provider_failure_without_zero_result_is_not_penalized(self):
        key = "source_ai_rater_japanese_en_remote"
        baseline = {key: {"search_attempts": 0.0, "zero_result_attempts": 0.0}}
        failed = {key: {"search_attempts": 1.0, "zero_result_attempts": 0.0}}
        self.assertEqual(mod.precision_score(key, failed), mod.precision_score(key, baseline))

    def test_learning_folds_attempt_and_zero_result_fields(self):
        payload = {
            "generated_at": "2026-08-20T07:05:14+00:00",
            "candidate_search_profile_learning_through": "2026-08-20T07:00:42+00:00",
            "candidate_search_profile_yield": [
                {
                    "profile": "source_ai_rater_japanese_en_remote",
                    "seen": 0,
                    "apply_options": 0,
                    "indeed_apply": 0,
                    "accepted": 0,
                    "search_attempts": 1,
                    "successful_search_attempts": 1,
                    "zero_result_attempts": 1,
                }
            ],
            "candidate_quality_rejection_by_profile": [],
            "jobs": [],
        }
        history, through = mod.build_learning(payload)
        stats = history["source_ai_rater_japanese_en_remote"]
        self.assertEqual(through, payload["generated_at"])
        self.assertEqual(stats["search_attempts"], 1.0)
        self.assertEqual(stats["zero_result_attempts"], 1.0)

    def test_metadata_declares_v7_zero_result_policy(self):
        meta = mod.learning_metadata({"query_total": 2})
        self.assertEqual(meta["candidate_search_profile_learning_version"], 7)
        self.assertIn("zero-result-aware", meta["candidate_search_precision_policy"])
        self.assertEqual(meta["candidate_search_precision_zero_result_penalty"], 32.0)
        self.assertIn("provider-failure", meta["candidate_search_precision_zero_result_behavior"])


if __name__ == "__main__":
    unittest.main()
