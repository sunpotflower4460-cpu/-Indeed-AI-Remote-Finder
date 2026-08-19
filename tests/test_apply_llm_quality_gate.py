import importlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

mod = importlib.import_module("apply_llm_quality_gate")


def row(review=None):
    item = {"id": "a", "tier": "review", "carryover": False, "remote_search_only": False}
    if review is not None:
        item["llm_review"] = review
    return item


def review(**overrides):
    base = {
        "verdict": "strong",
        "automatable_fraction": 95,
        "confidence": 90,
        "human_dependency": "low",
        "physical_presence_required": False,
        "synchronous_human_interaction": "none",
        "blockers": [],
    }
    base.update(overrides)
    return base


class LlmQualityGateTests(unittest.TestCase):
    def test_missing_llm_review_never_causes_removal(self):
        self.assertIsNone(mod.reject_reason(row()))

    def test_clear_human_or_sync_mismatch_is_rejected(self):
        self.assertEqual(mod.reject_reason(row(review(verdict="reject"))), "verdict-reject")
        self.assertEqual(mod.reject_reason(row(review(human_dependency="high"))), "high-human-dependency")
        self.assertEqual(mod.reject_reason(row(review(synchronous_human_interaction="frequent"))), "frequent-sync")
        self.assertEqual(mod.reject_reason(row(review(physical_presence_required=True))), "physical-presence")

    def test_high_confidence_medium_human_dependency_is_rejected(self):
        self.assertEqual(
            mod.reject_reason(row(review(verdict="uncertain", human_dependency="medium", confidence=88))),
            "confirmed-medium-human-dependency",
        )

    def test_low_confidence_uncertainty_is_not_over_vetoed(self):
        self.assertIsNone(
            mod.reject_reason(row(review(verdict="uncertain", human_dependency="medium", confidence=65, automatable_fraction=80)))
        )

    def test_apply_updates_pool_metadata(self):
        bad = row(review(verdict="reject"))
        good = {"id": "b", "tier": "review", "carryover": True, "remote_search_only": False}
        payload = {"candidate_display_target": 100, "jobs": [bad, good]}
        got = mod.apply(payload)
        self.assertEqual([x["id"] for x in got["jobs"]], ["b"])
        self.assertEqual(got["candidate_pool_size"], 1)
        self.assertEqual(got["llm_quality_dropped"], 1)
        self.assertEqual(got["carryover_jobs"], 1)
        self.assertTrue(got["pool_under_display_target"])


if __name__ == "__main__":
    unittest.main()
