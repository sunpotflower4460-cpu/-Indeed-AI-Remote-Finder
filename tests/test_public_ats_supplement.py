import importlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

mod = importlib.import_module("supplement_public_ats")


def ashby_job(index: int, *, remote: bool = True, title: str | None = None) -> dict:
    return {
        "title": title or f"Japanese AI Benchmark Evaluator {index}",
        "location": "Japan (Remote)" if remote else "Tokyo, Japan",
        "secondaryLocations": [],
        "isListed": True,
        "isRemote": remote,
        "workplaceType": "Remote" if remote else "OnSite",
        "descriptionPlain": (
            "Evaluate AI model responses and multilingual benchmark tasks in Japanese. "
            "Perform annotation, data evaluation, quality evaluation, fact checking, "
            "and rubric-based review asynchronously. No phone support or meetings required."
        ),
        "publishedAt": "2026-08-19T12:00:00Z",
        "jobUrl": f"https://jobs.ashbyhq.com/lilt-production/job-{index}",
        "applyUrl": f"https://jobs.ashbyhq.com/lilt-production/job-{index}/application",
    }


def lever_job(index: int) -> dict:
    return {
        "id": f"lever-{index}",
        "text": f"Japanese Search Quality Rater {index}",
        "workplaceType": "remote",
        "categories": {"location": "Japan", "allLocations": ["Japan"]},
        "descriptionPlain": (
            "Japanese search quality rating and AI evaluation. Review search relevance, "
            "annotate results, and perform data evaluation independently."
        ),
        "applyUrl": f"https://jobs.lever.co/weloglobal/lever-{index}",
    }


def greenhouse_job(index: int, *, body_extra: str = "") -> dict:
    return {
        "id": 100000 + index,
        "title": f"Japanese Language Specialist - Freelance AI Trainer {index}",
        "updated_at": "2026-08-19T12:00:00Z",
        "location": {"name": "World Wide - Remote"},
        "absolute_url": f"https://job-boards.eu.greenhouse.io/agency/jobs/{100000 + index}",
        "content": (
            "Remote freelance Japanese AI trainer. Evaluate model responses, annotate errors, "
            "verify factual accuracy, and provide structured quality feedback asynchronously. "
            + body_extra
        ),
    }


class PublicATSSupplementTests(unittest.TestCase):
    def test_multi_source_pipeline_can_hold_thirty_strict_rows_and_blocks_bad_media(self):
        # Mapping safety can be checked without mutating the production builder.
        self.assertIsNone(mod._map_ashby(ashby_job(900, remote=False), "lilt-production", "LILT"))
        voice = ashby_job(901, title="Japanese Voice Talent AI Trainer")
        voice["descriptionPlain"] = "Record your voice for AI training and join live video calls."
        self.assertIsNone(mod._map_ashby(voice, "lilt-production", "LILT"))
        self.assertIsNone(
            mod._map_greenhouse(
                greenhouse_job(902, body_extra="This requires recording of your voice and likeness."),
                "agency",
                "Meridial / Invisible Agency",
            )
        )

        # Other unit tests deliberately monkey-patch the shared acquisition module.
        # Restore the same clean process state used by the production workflow.
        mod.acquisition._production_quality_policy_configured = False
        mod.acquisition._production_remote_policy_configured = False
        mod.acquisition.build_row = mod.acquisition_precision._ORIGINAL_ACQUISITION_BUILD_ROW
        mod.acquisition.legacy.score_job = mod.acquisition_quality.GENERIC_SCORE_JOB

        sources = {
            "fetched_lever": {"weloglobal": [lever_job(1)]},
            "fetched_ashby": {"lilt-production": [ashby_job(i) for i in range(35)]},
            "fetched_greenhouse": {
                "prolific": [],
                "agency": [greenhouse_job(1)],
            },
        }
        out = mod.supplement({"jobs": []}, {}, **sources)

        self.assertGreaterEqual(out["candidate_public_ats_deterministic_accepted"], 30)
        self.assertGreaterEqual(len(out["jobs"]), 30)
        self.assertLessEqual(len(out["jobs"]), 150)
        self.assertTrue(out["candidate_public_ats_goal_30_ready"])
        self.assertFalse(out["candidate_public_ats_uses_serpapi"])
        self.assertEqual(out["candidate_public_ats_source_success"], 4)
        self.assertIn("Ashby", out["candidate_public_ats_accepted_apply_sources"])
        self.assertIn("Lever", out["candidate_public_ats_accepted_apply_sources"])
        self.assertIn("Greenhouse", out["candidate_public_ats_accepted_apply_sources"])
        self.assertTrue(all(row.get("quality_gate") == "async-ai-remote-v2" for row in out["jobs"]))
        self.assertTrue(all(row.get("autonomy_attention_risk") == "low" for row in out["jobs"]))
        self.assertTrue(all(row.get("remote_search_only") is not True for row in out["jobs"]))
        self.assertTrue(any(row.get("apply_source") == "Ashby" for row in out["jobs"]))
        self.assertTrue(any(row.get("apply_source") == "Greenhouse" for row in out["jobs"]))


if __name__ == "__main__":
    unittest.main()
