import importlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

mod = importlib.import_module("profile_precision_v8")


class ProfilePrecisionV8Tests(unittest.TestCase):
    def base_profiles(self):
        return [
            ("source_document_check_home", "q document"),
            ("source_testing_home", "q testing"),
            ("source_ai_trainer_remote", "q trainer"),
            ("source_annotation_remote", "q annotation"),
            ("source_web_research_home", "q web"),
            ("source_search_eval_japanese_remote", "q search eval"),
        ]

    def payload(self, pool=1, width=4):
        return {
            "generated_at": "2026-08-20T07:53:59+00:00",
            "candidate_pool_size": pool,
            "pool_under_display_target": pool < 100,
            "serpapi_effective_request_limit": width,
            "serpapi_rotation_cursor": 0,
            "candidate_search_precision_phase": 0,
            "candidate_search_profile_learning": [],
            "candidate_search_profile_yield": [],
            "candidate_quality_rejection_by_profile": [],
            "jobs": [],
        }

    def ordered_actual(self, pool=1, width=4, payload=None):
        payload = payload or self.payload(pool, width)
        profiles = mod.augment_profiles(self.base_profiles(), payload)
        ordered = mod.order_profiles(profiles, payload)
        return mod.actual_order(ordered, payload), payload

    def test_critical_pool_uses_every_available_slot_for_focus_work(self):
        actual, _ = self.ordered_actual(pool=1, width=4)
        self.assertEqual(len(actual[:4]), 4)
        self.assertTrue(all(mod.is_focus_profile(name) for name, _ in actual[:4]))
        self.assertTrue(any(name.startswith("source_rescue_") for name, _ in actual[:4]))

    def test_low_stock_pool_uses_at_least_three_of_four_focus_slots(self):
        actual, _ = self.ordered_actual(pool=10, width=4)
        focus = sum(1 for name, _ in actual[:4] if mod.is_focus_profile(name))
        self.assertGreaterEqual(focus, 3)

    def test_rescue_disables_at_thirty_candidates(self):
        actual, payload = self.ordered_actual(pool=30, width=4)
        self.assertTrue(actual)
        meta = mod.learning_metadata({**payload, "query_total": 4})
        self.assertFalse(meta["candidate_search_precision_rescue_active"])
        self.assertEqual(meta["candidate_search_precision_rescue_profiles_added"], 0)
        self.assertEqual(meta["candidate_search_precision_rescue_focus_target"], 0)

    def test_recent_exact_rescue_profile_is_avoided_when_alternatives_exist(self):
        payload = self.payload(pool=1, width=3)
        payload["candidate_search_profile_yield"] = [
            {
                "profile": "source_rescue_ai_trainer_outlier_japanese",
                "seen": 5,
                "indeed_apply": 1,
                "accepted": 0,
            }
        ]
        actual, _ = self.ordered_actual(payload=payload)
        first_three = [name for name, _ in actual[:3]]
        self.assertNotIn("source_rescue_ai_trainer_outlier_japanese", first_three)
        self.assertTrue(all(mod.is_focus_profile(name) for name in first_three))

    def test_metadata_declares_critical_rescue_policy(self):
        actual, payload = self.ordered_actual(pool=1, width=4)
        self.assertTrue(actual)
        meta = mod.learning_metadata({**payload, "query_total": 4})
        self.assertEqual(meta["candidate_search_profile_learning_version"], 8)
        self.assertTrue(meta["candidate_search_precision_rescue_active"])
        self.assertEqual(meta["candidate_search_precision_rescue_pool_size"], 1)
        self.assertEqual(meta["candidate_search_precision_rescue_focus_target"], 4)
        self.assertEqual(meta["candidate_search_precision_rescue_focus_actual"], 4)
        self.assertGreater(meta["candidate_search_precision_rescue_profiles_added"], 0)
        self.assertIn("critical-low-stock-focus", meta["candidate_search_precision_policy"])


if __name__ == "__main__":
    unittest.main()
