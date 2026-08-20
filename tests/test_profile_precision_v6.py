import importlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

mod = importlib.import_module("profile_precision_v6")
core = importlib.import_module("profile_precision")


class ProfilePrecisionV6Tests(unittest.TestCase):
    def setUp(self):
        self.original_state = core._STATE
        core._STATE = {
            "source_ai_trainer_remote": {
                "seen": 5.0,
                "indeed_apply": 2.0,
                "accepted": 1.0,
                "final_survivors": 1.0,
                "hard_rejections": 0.0,
                "no_indeed": 3.0,
                "soft_rejections": 1.0,
                "observed_runs": 1.0,
                "post_gate_losses": 0.0,
            },
            "source_transcription_home": {
                "seen": 10.0,
                "indeed_apply": 4.0,
                "accepted": 0.0,
                "final_survivors": 0.0,
                "hard_rejections": 4.0,
                "no_indeed": 6.0,
                "soft_rejections": 0.0,
                "observed_runs": 1.0,
                "post_gate_losses": 0.0,
            },
        }

    def tearDown(self):
        core._STATE = self.original_state

    def payload(self):
        return {
            "pool_under_display_target": True,
            "serpapi_effective_request_limit": 2,
            "candidate_search_profile_yield": [],
        }

    def test_known_negative_second_slot_is_replaced_by_unseen_positive_family(self):
        actual = [
            ("source_ai_trainer_remote", "q trainer"),
            ("source_transcription_home", "q transcription"),
            ("source_annotation_japanese_en_remote", "q annotation"),
            ("source_search_eval_japanese_remote", "q search"),
        ]
        guarded = mod._guard_scarce_window(list(actual), self.payload())
        self.assertEqual(guarded[0][0], "source_ai_trainer_remote")
        self.assertEqual(guarded[1][0], "source_annotation_japanese_en_remote")
        self.assertNotEqual(mod.family_key(guarded[0][0]), mod.family_key(guarded[1][0]))
        self.assertTrue(mod._SCARCE_GUARD_ACTIVE)
        self.assertEqual(mod._SCARCE_GUARD_WIDTH, 2)
        self.assertEqual(len(mod._SCARCE_REPLACEMENTS), 1)
        self.assertEqual(mod._SCARCE_REPLACEMENTS[0]["from_profile"], "source_transcription_home")
        self.assertEqual(mod._SCARCE_REPLACEMENTS[0]["to_profile"], "source_annotation_japanese_en_remote")

    def test_healthy_second_slot_is_not_replaced(self):
        actual = [
            ("source_ai_trainer_remote", "q trainer"),
            ("source_annotation_japanese_en_remote", "q annotation"),
            ("source_search_eval_japanese_remote", "q search"),
        ]
        guarded = mod._guard_scarce_window(list(actual), self.payload())
        self.assertEqual(guarded, actual)
        self.assertEqual(mod._SCARCE_REPLACEMENTS, [])

    def test_recent_profile_is_not_used_as_replacement(self):
        payload = self.payload()
        payload["candidate_search_profile_yield"] = [
            {"profile": "source_annotation_japanese_en_remote", "seen": 5}
        ]
        actual = [
            ("source_ai_trainer_remote", "q trainer"),
            ("source_transcription_home", "q transcription"),
            ("source_annotation_japanese_en_remote", "q annotation"),
            ("source_search_eval_japanese_remote", "q search"),
        ]
        guarded = mod._guard_scarce_window(list(actual), payload)
        self.assertEqual(guarded[1][0], "source_search_eval_japanese_remote")

    def test_guard_is_disabled_when_pool_target_is_met(self):
        payload = self.payload()
        payload["pool_under_display_target"] = False
        actual = [
            ("source_ai_trainer_remote", "q trainer"),
            ("source_transcription_home", "q transcription"),
            ("source_annotation_japanese_en_remote", "q annotation"),
        ]
        guarded = mod._guard_scarce_window(list(actual), payload)
        self.assertEqual(guarded, actual)
        self.assertFalse(mod._SCARCE_GUARD_ACTIVE)

    def test_guard_is_disabled_for_wider_windows(self):
        payload = self.payload()
        payload["serpapi_effective_request_limit"] = 4
        actual = [
            ("source_ai_trainer_remote", "q trainer"),
            ("source_transcription_home", "q transcription"),
            ("source_annotation_japanese_en_remote", "q annotation"),
            ("source_search_eval_japanese_remote", "q search"),
        ]
        guarded = mod._guard_scarce_window(list(actual), payload)
        self.assertEqual(guarded, actual)
        self.assertFalse(mod._SCARCE_GUARD_ACTIVE)

    def test_metadata_documents_quality_floor(self):
        actual = [
            ("source_ai_trainer_remote", "q trainer"),
            ("source_transcription_home", "q transcription"),
            ("source_annotation_japanese_en_remote", "q annotation"),
        ]
        mod._guard_scarce_window(actual, self.payload())
        meta = mod.learning_metadata({"query_total": 2})
        self.assertEqual(meta["candidate_search_profile_learning_version"], 6)
        self.assertEqual(
            meta["candidate_search_precision_policy"],
            "v6-scarce-quality-floor+family-handoff+guarded-champion",
        )
        self.assertTrue(meta["candidate_search_precision_scarce_guard_active"])
        self.assertEqual(meta["candidate_search_precision_scarce_guard_window"], 2)
        self.assertEqual(meta["candidate_search_precision_scarce_slot_min_score"], -5.0)
        self.assertEqual(meta["candidate_search_precision_scarce_replacement_min_score"], 12.0)
        self.assertTrue(meta["candidate_search_precision_scarce_replacements"])


if __name__ == "__main__":
    unittest.main()
