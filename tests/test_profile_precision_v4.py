import importlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

mod = importlib.import_module("profile_precision_v4")


class ProfilePrecisionV4Tests(unittest.TestCase):
    def profiles(self):
        return [
            ("source_data_entry_remote", "q data"),
            ("source_annotation_remote", "q annotation"),
            ("source_ai_trainer_remote", "q trainer"),
            ("source_ocr_home", "q ocr"),
            ("source_testing_home", "q testing"),
            ("source_metadata_remote", "q metadata"),
        ]

    def payload(self):
        return {
            "generated_at": "2026-08-20T06:05:25+00:00",
            "candidate_search_profile_learning_through": "2026-08-20T06:05:25+00:00",
            "candidate_search_precision_phase": 2,
            "serpapi_rotation_cursor": 3,
            "pool_under_display_target": True,
            "candidate_search_profile_learning": [
                {
                    "profile": "source_ai_trainer_remote",
                    "seen": 5,
                    "indeed_apply": 2,
                    "accepted": 1,
                    "final_survivors": 1,
                    "no_indeed": 3,
                    "soft_rejections": 1,
                },
                {
                    "profile": "source_annotation_remote",
                    "seen": 10,
                    "indeed_apply": 5,
                    "accepted": 1,
                    "post_gate_losses": 1,
                    "hard_rejections": 3,
                    "no_indeed": 5,
                    "soft_rejections": 1,
                },
            ],
            "candidate_search_profile_yield": [
                {
                    "profile": "source_testing_home",
                    "seen": 10,
                    "indeed_apply": 7,
                    "accepted": 0,
                },
                {
                    "profile": "source_ocr_home",
                    "seen": 10,
                    "indeed_apply": 3,
                    "accepted": 0,
                },
            ],
            "jobs": [
                {
                    "category": "source_ai_trainer_remote",
                    "carryover": True,
                    "seen_count": 2,
                }
            ],
        }

    def actual_order(self, ordered, payload):
        cursor = payload["serpapi_rotation_cursor"] % len(ordered)
        return ordered[cursor:] + ordered[:cursor]

    def test_proven_exact_profile_owns_first_actual_slot_when_not_fatigued(self):
        payload = self.payload()
        ordered = mod.order_profiles(self.profiles(), payload)
        actual = self.actual_order(ordered, payload)
        self.assertEqual(actual[0][0], "source_ai_trainer_remote")
        self.assertNotEqual(mod.v3.family_key(actual[0][0]), mod.v3.family_key(actual[1][0]))
        meta = mod.learning_metadata({"query_total": 2})
        self.assertEqual(meta["candidate_search_profile_learning_version"], 4)
        self.assertEqual(meta["candidate_search_precision_champion_profile"], "source_ai_trainer_remote")
        self.assertGreaterEqual(meta["candidate_search_precision_champion_score"], 80.0)
        self.assertEqual(meta["candidate_search_precision_champion_suppression_reason"], "none")

    def test_immediate_research_without_new_survivor_suppresses_champion(self):
        payload = self.payload()
        payload["candidate_search_profile_yield"] = [
            {
                "profile": "source_ai_trainer_remote",
                "seen": 5,
                "indeed_apply": 2,
                "accepted": 1,
            }
        ]
        payload["jobs"] = [
            {
                "category": "source_ai_trainer_remote",
                "carryover": False,
                "seen_count": 3,
                "first_seen": "2026-08-20T04:53:31+00:00",
                "last_seen": "2026-08-20T06:05:25+00:00",
            }
        ]
        mod.order_profiles(self.profiles(), payload)
        meta = mod.learning_metadata({"query_total": 2})
        self.assertIsNone(meta["candidate_search_precision_champion_profile"])
        self.assertEqual(
            meta["candidate_search_precision_champion_suppression_reason"],
            "recent-search-no-new-survivor",
        )

    def test_recent_search_with_new_final_survivor_keeps_champion_eligible(self):
        payload = self.payload()
        payload["candidate_search_profile_yield"] = [
            {
                "profile": "source_ai_trainer_remote",
                "seen": 5,
                "indeed_apply": 2,
                "accepted": 1,
            }
        ]
        payload["jobs"] = [
            {
                "category": "source_ai_trainer_remote",
                "carryover": False,
                "seen_count": 1,
                "first_seen": "2026-08-20T06:05:25+00:00",
                "last_seen": "2026-08-20T06:05:25+00:00",
            }
        ]
        ordered = mod.order_profiles(self.profiles(), payload)
        actual = self.actual_order(ordered, payload)
        self.assertEqual(actual[0][0], "source_ai_trainer_remote")
        meta = mod.learning_metadata({"query_total": 2})
        self.assertEqual(meta["candidate_search_precision_champion_profile"], "source_ai_trainer_remote")

    def test_champion_is_exact_profile_only_not_same_family_substitute(self):
        payload = self.payload()
        profiles = [
            ("source_ai_rating_home", "q rating"),
            ("source_ocr_home", "q ocr"),
            ("source_testing_home", "q testing"),
        ]
        mod.order_profiles(profiles, payload)
        meta = mod.learning_metadata({"query_total": 2})
        self.assertIsNone(meta["candidate_search_precision_champion_profile"])
        self.assertEqual(
            meta["candidate_search_precision_champion_suppression_reason"],
            "no-eligible-champion",
        )

    def test_pool_target_met_disables_champion(self):
        payload = self.payload()
        payload["pool_under_display_target"] = False
        mod.order_profiles(self.profiles(), payload)
        meta = mod.learning_metadata({"query_total": 2})
        self.assertIsNone(meta["candidate_search_precision_champion_profile"])
        self.assertEqual(
            meta["candidate_search_precision_champion_suppression_reason"],
            "pool-target-met",
        )


if __name__ == "__main__":
    unittest.main()
