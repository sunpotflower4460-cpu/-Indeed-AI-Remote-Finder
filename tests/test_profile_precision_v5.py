import importlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

mod = importlib.import_module("profile_precision_v5")


class ProfilePrecisionV5Tests(unittest.TestCase):
    def base_profiles(self):
        return [
            ("source_ai_trainer_remote", '"フルリモート" "AIトレーナー" Indeed'),
            ("source_annotation_remote", '"フルリモート" アノテーション Indeed'),
            ("source_ocr_home", '"完全在宅" OCR Indeed'),
            ("source_data_entry_remote", '"フルリモート" "データ入力" Indeed'),
        ]

    def payload(self):
        return {
            "generated_at": "2026-08-20T06:34:25+00:00",
            "candidate_search_profile_learning_through": "2026-08-20T06:34:25+00:00",
            "candidate_search_precision_phase": 0,
            "serpapi_rotation_cursor": 0,
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
                    "hard_rejections": 3,
                    "no_indeed": 5,
                    "soft_rejections": 1,
                },
            ],
            "candidate_search_profile_yield": [
                {
                    "profile": "source_ai_trainer_remote",
                    "seen": 5,
                    "indeed_apply": 2,
                    "accepted": 1,
                }
            ],
            "jobs": [
                {
                    "category": "source_ai_trainer_remote",
                    "carryover": False,
                    "seen_count": 3,
                    "first_seen": "2026-08-20T04:53:31+00:00",
                    "last_seen": "2026-08-20T06:34:25+00:00",
                }
            ],
        }

    def test_source_recovery_adds_high_intent_profiles_without_removing_existing(self):
        original = self.base_profiles()
        augmented = mod.augment_profiles(original, self.payload())
        names = [name for name, _ in augmented]
        self.assertEqual(names[: len(original)], [name for name, _ in original])
        self.assertEqual(len(augmented), len(original) + len(mod.SOURCE_HIGH_INTENT_PROFILES))
        self.assertIn("source_ai_trainer_japanese_en_remote", names)
        self.assertIn("source_ai_rater_japanese_en_remote", names)
        self.assertIn("source_prompt_eval_japanese_remote", names)
        self.assertIn("source_annotation_japanese_en_remote", names)
        for name, query in mod.SOURCE_HIGH_INTENT_PROFILES:
            self.assertTrue(name.startswith("source_"))
            self.assertIn("Indeed", query)

    def test_normal_rotation_gets_bounded_high_intent_anchors(self):
        normal = [
            ("data_entry_basic", "q data"),
            ("anchor_core_annotation_00", "q annotation"),
            ("proofreading", "q proofreading"),
        ]
        augmented = mod.augment_profiles(normal, self.payload())
        names = [name for name, _ in augmented]
        self.assertEqual(len(augmented), len(normal) + len(mod.NORMAL_HIGH_INTENT_PROFILES))
        self.assertIn("anchor_indeed_ai_trainer_english", names)
        self.assertIn("anchor_indeed_annotation_english", names)

    def test_fatigued_exact_champion_hands_off_to_same_proven_family(self):
        payload = self.payload()
        profiles = mod.augment_profiles(self.base_profiles(), payload)
        ordered = mod.order_profiles(profiles, payload)
        self.assertNotEqual(ordered[0][0], "source_ai_trainer_remote")
        self.assertEqual(mod.family_key(ordered[0][0]), "ai_rater")
        self.assertNotEqual(mod.family_key(ordered[0][0]), mod.family_key(ordered[1][0]))

        meta = mod.learning_metadata({"query_total": 2})
        self.assertEqual(meta["candidate_search_profile_learning_version"], 5)
        self.assertEqual(
            meta["candidate_search_precision_family_handoff_reason"],
            "proven-family-query-rotation",
        )
        self.assertEqual(meta["candidate_search_precision_family_handoff_family"], "ai_rater")
        self.assertIsNotNone(meta["candidate_search_precision_family_handoff_profile"])
        self.assertGreaterEqual(meta["candidate_search_precision_family_handoff_score"], 12.0)
        self.assertEqual(
            meta["candidate_search_precision_family_handoff_behavior"],
            "rotate-query-within-proven-family-before-unrelated-search",
        )

    def test_new_survivor_keeps_stronger_exact_champion(self):
        payload = self.payload()
        payload["jobs"] = [
            {
                "category": "source_ai_trainer_remote",
                "carryover": False,
                "seen_count": 1,
                "first_seen": "2026-08-20T06:34:25+00:00",
                "last_seen": "2026-08-20T06:34:25+00:00",
            }
        ]
        profiles = mod.augment_profiles(self.base_profiles(), payload)
        ordered = mod.order_profiles(profiles, payload)
        self.assertEqual(ordered[0][0], "source_ai_trainer_remote")
        meta = mod.learning_metadata({"query_total": 2})
        self.assertEqual(meta["candidate_search_precision_family_handoff_reason"], "exact-champion-selected")
        self.assertIsNone(meta["candidate_search_precision_family_handoff_profile"])

    def test_pool_target_met_disables_family_handoff(self):
        payload = self.payload()
        payload["pool_under_display_target"] = False
        profiles = mod.augment_profiles(self.base_profiles(), payload)
        mod.order_profiles(profiles, payload)
        meta = mod.learning_metadata({"query_total": 2})
        self.assertIsNone(meta["candidate_search_precision_family_handoff_profile"])
        self.assertIn(
            meta["candidate_search_precision_family_handoff_reason"],
            {"pool-target-met", "exact-champion-selected"},
        )

    def test_new_ai_evaluation_aliases_share_family_for_slot_diversity(self):
        for name in (
            "source_ai_trainer_japanese_en_remote",
            "source_ai_rater_japanese_en_remote",
            "source_model_response_eval_remote",
            "source_prompt_eval_japanese_remote",
        ):
            self.assertEqual(mod.family_key(name), "ai_rater", name)
        self.assertEqual(mod.family_key("source_annotation_japanese_en_remote"), "annotation")
        self.assertEqual(mod.family_key("source_search_eval_japanese_remote"), "search_quality")


if __name__ == "__main__":
    unittest.main()
