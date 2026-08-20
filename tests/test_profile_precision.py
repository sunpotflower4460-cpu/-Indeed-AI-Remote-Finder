import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

path = SCRIPTS / "profile_precision.py"
spec = importlib.util.spec_from_file_location("profile_precision_test", path)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class ProfilePrecisionTests(unittest.TestCase):
    def sample_payload(self):
        return {
            "generated_at": "2026-08-20T05:37:20+00:00",
            "serpapi_rotation_cursor": 10,
            "candidate_search_precision_phase": 0,
            "candidate_search_profile_yield": [
                {
                    "profile": "source_proofreading_home",
                    "seen": 10,
                    "indeed_apply": 4,
                    "accepted": 0,
                },
                {
                    "profile": "source_labeling_remote",
                    "seen": 10,
                    "indeed_apply": 4,
                    "accepted": 0,
                },
                {
                    "profile": "source_transcription_home",
                    "seen": 7,
                    "indeed_apply": 3,
                    "accepted": 0,
                },
            ],
            "candidate_quality_rejection_by_profile": [
                {
                    "profile": "source_proofreading_home",
                    "evaluated": 10,
                    "accepted": 0,
                    "reasons": {
                        "no-indeed-apply": 6,
                        "synchronous-human-attention": 3,
                        "missing-explicit-full-remote": 1,
                    },
                },
                {
                    "profile": "source_labeling_remote",
                    "evaluated": 10,
                    "accepted": 0,
                    "reasons": {
                        "no-indeed-apply": 6,
                        "score-below-candidate-floor": 2,
                        "partial-or-conditional-remote": 1,
                        "synchronous-human-attention": 1,
                    },
                },
                {
                    "profile": "source_transcription_home",
                    "evaluated": 7,
                    "accepted": 0,
                    "reasons": {
                        "no-indeed-apply": 4,
                        "synchronous-human-attention": 2,
                        "partial-or-conditional-remote": 1,
                    },
                },
            ],
            "jobs": [
                {
                    "category": "source_ai_trainer_remote",
                    "carryover": True,
                }
            ],
        }

    def profiles(self):
        names = [
            "source_data_entry_home",
            "source_annotation_home",
            "source_annotation_remote",
            "source_ai_rating_home",
            "source_ai_trainer_remote",
            "source_ocr_home",
            "source_labeling_remote",
            "source_transcription_home",
            "source_proofreading_home",
            "source_data_check_home",
            "source_metadata_remote",
            "source_testing_home",
        ]
        return [(name, f"query {name}") for name in names]

    def test_anchor_slot_suffixes_share_learning_identity(self):
        self.assertEqual(
            mod.profile_key("anchor_core_annotation_02"),
            "anchor_core_annotation",
        )
        self.assertEqual(
            mod.profile_key("anchor_indeed_rater_101"),
            "anchor_indeed_rater",
        )
        self.assertEqual(
            mod.profile_key("source_annotation_remote"),
            "source_annotation_remote",
        )

    def test_empirical_rejections_downrank_weak_profiles(self):
        history, through = mod.build_learning(self.sample_payload())
        self.assertEqual(through, "2026-08-20T05:37:20+00:00")
        trainer = mod.precision_score("source_ai_trainer_remote", history)
        annotation = mod.precision_score("source_annotation_remote", history)
        proofreading = mod.precision_score("source_proofreading_home", history)
        transcription = mod.precision_score("source_transcription_home", history)
        self.assertGreater(trainer, proofreading)
        self.assertGreater(annotation, proofreading)
        self.assertGreater(trainer, transcription)

    def test_final_live_survivor_is_stronger_signal_than_carryover(self):
        payload = self.sample_payload()
        payload["jobs"] = [
            {"category": "source_data_check_home", "carryover": False},
            {"category": "source_ai_trainer_remote", "carryover": True},
        ]
        history, _ = mod.build_learning(payload)
        self.assertEqual(history["source_data_check_home"]["final_survivors"], 1.0)
        self.assertNotIn("source_ai_trainer_remote", history)

    def test_precision_cycle_keeps_exploration_but_spends_two_of_three_on_preferred(self):
        payload = self.sample_payload()
        profiles = self.profiles()
        ordered = mod.order_profiles(profiles, payload)
        self.assertEqual(len(ordered), len(profiles))
        self.assertEqual({name for name, _ in ordered}, {name for name, _ in profiles})

        cursor = payload["serpapi_rotation_cursor"] % len(ordered)
        actual = ordered[cursor:] + ordered[:cursor]
        meta = mod.learning_metadata({"query_total": 3})
        preferred = set(meta["candidate_search_precision_priority_profiles"])
        first_three = [mod.profile_key(name) for name, _ in actual[:3]]
        self.assertGreaterEqual(sum(name in preferred for name in first_three), 2)
        self.assertEqual(meta["candidate_search_precision_phase"], 3)
        self.assertTrue(meta["candidate_search_profile_learning_active"])
        self.assertEqual(meta["candidate_search_precision_exploration_share_pct"], 33.3)

    def test_existing_precision_phase_advances_without_using_legacy_cursor_as_learning_phase(self):
        payload = self.sample_payload()
        payload["candidate_search_precision_phase"] = 4
        mod.order_profiles(self.profiles(), payload)
        meta = mod.learning_metadata({"query_total": 3})
        self.assertEqual(meta["candidate_search_precision_phase"], 7)

    def test_no_profile_telemetry_preserves_original_rotation(self):
        profiles = self.profiles()
        got = mod.order_profiles(profiles, {"candidate_pool_size": 1})
        self.assertEqual(got, profiles)
        meta = mod.learning_metadata({"query_total": 3})
        self.assertFalse(meta["candidate_search_profile_learning_active"])

    def test_stored_history_is_not_folded_twice_when_through_matches_generated(self):
        payload = {
            "generated_at": "2026-08-20T05:40:00+00:00",
            "candidate_search_profile_learning_through": "2026-08-20T05:40:00+00:00",
            "candidate_search_profile_learning": [
                {
                    "profile": "source_annotation_remote",
                    "seen": 10,
                    "accepted": 1,
                }
            ],
            "candidate_search_profile_yield": [
                {
                    "profile": "source_annotation_remote",
                    "seen": 10,
                    "accepted": 1,
                }
            ],
        }
        history, through = mod.build_learning(payload)
        self.assertEqual(through, payload["generated_at"])
        self.assertEqual(history["source_annotation_remote"]["seen"], 10.0)
        self.assertEqual(history["source_annotation_remote"]["accepted"], 1.0)


if __name__ == "__main__":
    unittest.main()
