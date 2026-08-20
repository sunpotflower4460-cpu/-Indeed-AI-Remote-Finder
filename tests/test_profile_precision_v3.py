import importlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

mod = importlib.import_module("profile_precision_v3")


class ProfilePrecisionV3Tests(unittest.TestCase):
    def test_ai_rater_anchor_and_task_share_one_family(self):
        self.assertEqual(mod.family_key("anchor_core_ai_rater_36"), "ai_rater")
        self.assertEqual(mod.family_key("anchor_indeed_rater_08"), "ai_rater")
        self.assertEqual(mod.family_key("ai_rater"), "ai_rater")
        self.assertEqual(mod.family_key("source_ai_trainer_remote"), "ai_rater")

    def test_family_diverse_cycle_separates_high_scoring_equivalent_variants(self):
        profiles = [
            ("anchor_core_ai_rater_36", "q1"),
            ("ai_rater", "q2"),
            ("anchor_indeed_rater_08", "q3"),
            ("source_annotation_remote", "q4"),
            ("ocr_validation", "q5"),
            ("data_entry_basic", "q6"),
        ]
        history = {
            "source_annotation_remote": {"seen": 10, "accepted": 1, "post_gate_losses": 1},
        }
        cycle, _ = mod.family_diverse_precision_cycle(profiles, history)
        first_three = [mod.family_key(name) for name, _ in cycle[:3]]
        self.assertEqual(len(first_three), len(set(first_three)))

    def test_cursor_compensated_two_request_window_uses_distinct_families(self):
        payload = {
            "generated_at": "2026-08-20T06:01:33+00:00",
            "serpapi_rotation_cursor": 15,
            "candidate_search_precision_phase": 5,
            "candidate_search_profile_yield": [
                {"profile": "anchor_core_ai_rater_36", "seen": 10, "indeed_apply": 1, "accepted": 0},
                {"profile": "ai_rater", "seen": 9, "indeed_apply": 0, "accepted": 0},
            ],
            "candidate_quality_rejection_by_profile": [
                {
                    "profile": "anchor_core_ai_rater_36",
                    "evaluated": 10,
                    "accepted": 0,
                    "reasons": {"no-indeed-apply": 9},
                },
                {
                    "profile": "ai_rater",
                    "evaluated": 9,
                    "accepted": 0,
                    "reasons": {"no-indeed-apply": 9},
                },
            ],
            "jobs": [],
        }
        profiles = [
            ("anchor_core_ai_rater_36", "q1"),
            ("ai_rater", "q2"),
            ("anchor_indeed_rater_08", "q3"),
            ("source_annotation_remote", "q4"),
            ("ocr_validation", "q5"),
            ("data_entry_basic", "q6"),
            ("metadata_tagging", "q7"),
            ("web_research", "q8"),
        ]
        ordered = mod.order_profiles(profiles, payload)
        cursor = payload["serpapi_rotation_cursor"] % len(ordered)
        actual = ordered[cursor:] + ordered[:cursor]
        first_two = [mod.family_key(name) for name, _ in actual[:2]]
        self.assertNotEqual(first_two[0], first_two[1])

    def test_metadata_declares_family_diverse_v3_policy(self):
        payload = {
            "generated_at": "2026-08-20T06:05:00+00:00",
            "serpapi_rotation_cursor": 0,
            "candidate_search_precision_phase": 0,
            "candidate_search_profile_yield": [
                {"profile": "ai_rater", "seen": 10, "accepted": 0},
                {"profile": "ocr_validation", "seen": 10, "accepted": 0},
            ],
            "jobs": [],
        }
        profiles = [
            ("anchor_core_ai_rater_36", "q1"),
            ("ai_rater", "q2"),
            ("ocr_validation", "q3"),
            ("data_entry_basic", "q4"),
        ]
        mod.order_profiles(profiles, payload)
        metadata = mod.learning_metadata({"query_total": 2})
        self.assertEqual(metadata["candidate_search_profile_learning_version"], 3)
        self.assertEqual(
            metadata["candidate_search_precision_policy"],
            "two-exploit-one-explore-v3-family-diverse-final-outcome",
        )
        self.assertEqual(metadata["candidate_search_precision_family_diversity_window"], 2)
        priorities = metadata["candidate_search_precision_priority_profiles"]
        self.assertEqual(len(priorities), len(set(priorities)))


if __name__ == "__main__":
    unittest.main()
