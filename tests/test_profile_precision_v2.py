import importlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

mod = importlib.import_module("profile_precision_v2")


class ProfilePrecisionV2Tests(unittest.TestCase):
    def test_post_gate_loss_is_folded_for_accepted_candidate_that_does_not_survive(self):
        payload = {
            "generated_at": "2026-08-20T05:53:30+00:00",
            "candidate_search_profile_learning_through": "2026-08-20T05:37:20+00:00",
            "candidate_search_profile_yield": [
                {
                    "profile": "source_annotation_remote",
                    "seen": 10,
                    "indeed_apply": 5,
                    "accepted": 1,
                },
                {
                    "profile": "source_ai_trainer_remote",
                    "seen": 5,
                    "indeed_apply": 2,
                    "accepted": 1,
                },
            ],
            "candidate_quality_rejection_by_profile": [
                {
                    "profile": "source_annotation_remote",
                    "evaluated": 10,
                    "accepted": 1,
                    "reasons": {"no-indeed-apply": 5},
                },
                {
                    "profile": "source_ai_trainer_remote",
                    "evaluated": 5,
                    "accepted": 1,
                    "reasons": {"no-indeed-apply": 3},
                },
            ],
            "jobs": [
                {
                    "category": "source_ai_trainer_remote",
                    "carryover": False,
                }
            ],
        }
        history, through = mod.build_learning(payload)
        self.assertEqual(through, payload["generated_at"])
        self.assertEqual(history["source_annotation_remote"]["post_gate_losses"], 1.0)
        self.assertEqual(history["source_ai_trainer_remote"].get("post_gate_losses", 0.0), 0.0)
        self.assertGreater(
            mod.precision_score("source_ai_trainer_remote", history),
            mod.precision_score("source_annotation_remote", history),
        )

    def test_quality_and_yield_acceptance_views_are_not_double_counted(self):
        payload = {
            "generated_at": "2026-08-20T06:00:00+00:00",
            "candidate_search_profile_yield": [
                {"profile": "source_annotation_remote", "seen": 10, "accepted": 1}
            ],
            "candidate_quality_rejection_by_profile": [
                {"profile": "source_annotation_remote", "evaluated": 10, "accepted": 1}
            ],
            "jobs": [],
        }
        history, _ = mod.build_learning(payload)
        self.assertEqual(history["source_annotation_remote"]["post_gate_losses"], 1.0)

    def test_stored_post_gate_loss_is_not_folded_twice(self):
        payload = {
            "generated_at": "2026-08-20T06:10:00+00:00",
            "candidate_search_profile_learning_through": "2026-08-20T06:10:00+00:00",
            "candidate_search_profile_learning": [
                {
                    "profile": "source_annotation_remote",
                    "seen": 10,
                    "accepted": 1,
                    "post_gate_losses": 1,
                }
            ],
            "candidate_search_profile_yield": [
                {"profile": "source_annotation_remote", "seen": 10, "accepted": 1}
            ],
            "jobs": [],
        }
        history, through = mod.build_learning(payload)
        self.assertEqual(through, payload["generated_at"])
        self.assertEqual(history["source_annotation_remote"]["post_gate_losses"], 1.0)

    def test_metadata_declares_v2_final_outcome_policy_and_persists_loss_field(self):
        payload = {
            "generated_at": "2026-08-20T06:20:00+00:00",
            "serpapi_rotation_cursor": 0,
            "candidate_search_precision_phase": 0,
            "candidate_search_profile_yield": [
                {"profile": "source_annotation_remote", "seen": 10, "accepted": 1},
                {"profile": "source_ai_trainer_remote", "seen": 5, "accepted": 1},
            ],
            "jobs": [
                {"category": "source_ai_trainer_remote", "carryover": False}
            ],
        }
        profiles = [
            ("source_annotation_remote", "query a"),
            ("source_ai_trainer_remote", "query b"),
            ("source_data_entry_remote", "query c"),
        ]
        mod.order_profiles(profiles, payload)
        metadata = mod.learning_metadata({"query_total": 3})
        self.assertEqual(metadata["candidate_search_profile_learning_version"], 2)
        self.assertEqual(
            metadata["candidate_search_precision_policy"],
            "two-exploit-one-explore-v2-final-outcome",
        )
        self.assertIn("post-gate-loss", metadata["candidate_search_precision_empirical_signals"])
        annotation = next(
            row
            for row in metadata["candidate_search_profile_learning"]
            if row["profile"] == "source_annotation_remote"
        )
        self.assertEqual(annotation["post_gate_losses"], 1.0)


if __name__ == "__main__":
    unittest.main()
