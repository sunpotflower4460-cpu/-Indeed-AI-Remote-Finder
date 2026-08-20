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
    def empty_sources(self):
        return {
            "fetched_lever": {"weloglobal": []},
            "fetched_ashby": {"lilt-production": []},
            "fetched_greenhouse": {"prolific": [], "agency": []},
        }

    def test_ashby_remote_japanese_ai_job_enters_existing_strict_builder(self):
        sources = self.empty_sources()
        sources["fetched_ashby"]["lilt-production"] = [ashby_job(1)]
        out = mod.supplement({"jobs": []}, {}, **sources)
        self.assertEqual(out["candidate_public_ats_deterministic_accepted"], 1)
        self.assertEqual(len(out["jobs"]), 1)
        row = out["jobs"][0]
        self.assertEqual(row["apply_source"], "Ashby")
        self.assertEqual(row["apply_source_kind"], "trusted-ats")
        self.assertEqual(row["quality_gate"], "async-ai-remote-v2")
        self.assertEqual(row["autonomy_attention_risk"], "low")
        self.assertEqual(row["remote_evidence_source"], "employer-ats-structured-remote")

    def test_lever_and_greenhouse_are_supported_without_serpapi(self):
        sources = self.empty_sources()
        sources["fetched_lever"]["weloglobal"] = [lever_job(1)]
        sources["fetched_greenhouse"]["agency"] = [greenhouse_job(1)]
        out = mod.supplement({"jobs": []}, {}, **sources)
        self.assertGreaterEqual(len(out["jobs"]), 2)
        self.assertFalse(out["candidate_public_ats_uses_serpapi"])
        self.assertEqual(out["candidate_public_ats_source_success"], 4)
        self.assertIn("Lever", out["candidate_public_ats_accepted_apply_sources"])
        self.assertIn("Greenhouse", out["candidate_public_ats_accepted_apply_sources"])

    def test_non_remote_and_live_human_media_jobs_are_rejected(self):
        sources = self.empty_sources()
        sources["fetched_ashby"]["lilt-production"] = [
            ashby_job(1, remote=False),
            ashby_job(2, title="Japanese Voice Talent AI Trainer") | {
                "isRemote": True,
                "workplaceType": "Remote",
                "location": "Japan (Remote)",
                "descriptionPlain": "Record your voice for AI training and join live video calls.",
            },
        ]
        out = mod.supplement({"jobs": []}, {}, **sources)
        self.assertEqual(out["jobs"], [])

    def test_thirty_plus_strict_candidates_can_be_held_before_ui_slice(self):
        sources = self.empty_sources()
        sources["fetched_ashby"]["lilt-production"] = [ashby_job(i) for i in range(35)]
        out = mod.supplement({"jobs": []}, {}, **sources)
        self.assertGreaterEqual(out["candidate_public_ats_deterministic_accepted"], 30)
        self.assertGreaterEqual(len(out["jobs"]), 30)
        self.assertLessEqual(len(out["jobs"]), 150)
        self.assertTrue(out["candidate_public_ats_goal_30_ready"])
        self.assertTrue(all(row.get("quality_gate") == "async-ai-remote-v2" for row in out["jobs"]))

    def test_greenhouse_multimodal_voice_likeness_collection_is_rejected(self):
        sources = self.empty_sources()
        sources["fetched_greenhouse"]["agency"] = [
            greenhouse_job(1, body_extra="This project requires recording of your voice and likeness.")
        ]
        out = mod.supplement({"jobs": []}, {}, **sources)
        self.assertEqual(out["jobs"], [])


if __name__ == "__main__":
    unittest.main()
