import importlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

mod = importlib.import_module("supplement_targeted_public_ats_buffered")
targeted = importlib.import_module("supplement_targeted_public_ats")


def welo(index: int) -> dict:
    return {
        "id": f"buffer-welo-{index}",
        "text": f"Japanese Search Quality Rater Buffer {index}",
        "workplaceType": "remote",
        "categories": {"location": "Japan", "allLocations": ["Japan"]},
        "descriptionPlain": (
            "Evaluate Japanese search results and AI recommendations independently. "
            "Rate relevance, annotate results, and provide structured data evaluation feedback."
        ),
        "applyUrl": f"https://jobs.lever.co/weloglobal/buffer-welo-{index}",
    }


class PreFinalSupplyBufferTests(unittest.TestCase):
    def setUp(self):
        targeted.acquisition._production_quality_policy_configured = False
        targeted.acquisition._production_remote_policy_configured = False
        targeted.acquisition.build_row = targeted.acquisition_precision._ORIGINAL_ACQUISITION_BUILD_ROW
        targeted.acquisition.legacy.score_job = targeted.acquisition_quality.GENERIC_SCORE_JOB

    def test_pool_in_thirties_is_still_topped_up_for_final_gate_headroom(self):
        existing = [{"id": f"existing-{i}", "tier": "review", "score": 80} for i in range(35)]
        out = mod.top_up_with_buffer(
            {"jobs": existing},
            {},
            welo_posts=[welo(i) for i in range(12)],
            lilt_posts=[],
            prolific_posts=[],
        )
        self.assertGreaterEqual(len(out["jobs"]), 45)
        self.assertTrue(out["candidate_targeted_public_ats_goal_30_ready"])
        self.assertTrue(out["candidate_pre_final_buffer_ready"])
        self.assertEqual(out["candidate_pre_final_buffer_target"], 45)
        self.assertEqual(out["candidate_visible_minimum"], 30)

    def test_pool_at_buffer_target_skips_extra_ats_work(self):
        existing = [{"id": f"existing-{i}", "tier": "review", "score": 80} for i in range(45)]
        out = mod.top_up_with_buffer(
            {"jobs": existing},
            {},
            welo_posts=[],
            lilt_posts=[],
            prolific_posts=[],
        )
        self.assertEqual(len(out["jobs"]), 45)
        self.assertEqual(out["candidate_targeted_public_ats_skipped"], "pool-at-or-above-buffer-target")
        self.assertTrue(out["candidate_targeted_public_ats_goal_30_ready"])
        self.assertTrue(out["candidate_pre_final_buffer_ready"])

    def test_workflow_uses_buffered_entrypoint(self):
        workflow = (ROOT / ".github/workflows/update-jobs.yml").read_text(encoding="utf-8")
        self.assertIn("Maintain 45-candidate pre-final ATS safety buffer", workflow)
        self.assertIn("python scripts/supplement_targeted_public_ats_buffered.py", workflow)


if __name__ == "__main__":
    unittest.main()
