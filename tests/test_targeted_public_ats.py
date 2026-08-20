import importlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

mod = importlib.import_module("supplement_targeted_public_ats")


def welo(index: int) -> dict:
    return {
        "id": f"welo-{index}",
        "text": f"Japanese Search Quality Rater {index}",
        "workplaceType": "remote",
        "categories": {"location": "Japan", "allLocations": ["Japan"]},
        "descriptionPlain": (
            "Evaluate Japanese search results and AI recommendations independently. "
            "Rate relevance, annotate results, and provide structured data evaluation feedback."
        ),
        "applyUrl": f"https://jobs.lever.co/weloglobal/welo-{index}",
    }


def lilt_language(index: int) -> dict:
    return {
        "title": f"Linguist - Japanese - Finance - Remote {index}",
        "location": "Japan (Remote)",
        "secondaryLocations": [],
        "isListed": True,
        "isRemote": True,
        "workplaceType": "Remote",
        "descriptionPlain": (
            "Translate and review Japanese financial content, perform localization quality assurance, "
            "proofreading, terminology verification, and structured quality review."
        ),
        "publishedAt": "2026-08-19T12:00:00Z",
        "applyUrl": f"https://jobs.ashbyhq.com/lilt-production/lang-{index}/application",
        "jobUrl": f"https://jobs.ashbyhq.com/lilt-production/lang-{index}",
    }


def prolific(index: int = 1) -> dict:
    return {
        "id": 4000000 + index,
        "title": "AI Trainer - Advanced Japanese Fluency",
        "updated_at": "2026-08-19T12:00:00Z",
        "location": {"name": "Remote"},
        "absolute_url": f"https://job-boards.eu.greenhouse.io/prolificacademicltd/jobs/{4000000 + index}",
        "content": (
            "Remote Japanese AI training tasks. Analyze, edit, and write in Japanese, judge AI "
            "responses to Japanese prompts, and improve model quality. Work independently online."
        ),
    }


class TargetedPublicATSTests(unittest.TestCase):
    def setUp(self):
        # Restore the fresh-process production setup expected by the workflow.
        mod.acquisition._production_quality_policy_configured = False
        mod.acquisition._production_remote_policy_configured = False
        mod.acquisition.build_row = mod.acquisition_precision._ORIGINAL_ACQUISITION_BUILD_ROW
        mod.acquisition.legacy.score_job = mod.acquisition_quality.GENERIC_SCORE_JOB

    def test_lever_location_filter_is_used_and_bounded(self):
        seen = []
        original = mod.base._fetch_json
        try:
            def fake(url, **kwargs):
                seen.append(url)
                return [welo(1)]
            mod.base._fetch_json = fake
            rows, pages = mod._fetch_welo_japan()
        finally:
            mod.base._fetch_json = original
        self.assertEqual(len(rows), 1)
        self.assertEqual(pages, 1)
        self.assertIn("location=Japan", seen[0])
        self.assertIn("limit=200", seen[0])
        self.assertIn("skip=0", seen[0])

    def test_eighteen_existing_rows_can_be_topped_up_past_thirty_without_relaxing_gate(self):
        existing = [{"id": f"existing-{i}", "tier": "review", "score": 80} for i in range(18)]
        out = mod.top_up(
            {"jobs": existing},
            {},
            welo_posts=[welo(i) for i in range(12)],
            lilt_posts=[lilt_language(i) for i in range(8)],
            prolific_posts=[prolific()],
        )
        self.assertGreaterEqual(out["candidate_targeted_public_ats_deterministic_accepted"], 12)
        self.assertGreaterEqual(out["candidate_targeted_public_ats_pool_after"], 30)
        self.assertTrue(out["candidate_targeted_public_ats_goal_30_ready"])
        self.assertFalse(out["candidate_targeted_public_ats_uses_serpapi"])
        new_rows = [row for row in out["jobs"] if str(row.get("id", "")).startswith("apply-")]
        self.assertGreaterEqual(len(new_rows), 12)
        self.assertTrue(all(row.get("quality_gate") == "async-ai-remote-v2" for row in new_rows))
        self.assertTrue(all(row.get("autonomy_attention_risk") == "low" for row in new_rows))
        self.assertTrue(all(row.get("remote_search_only") is not True for row in new_rows))

    def test_foreign_prolific_and_voice_media_are_not_topup_candidates(self):
        self.assertFalse(mod._prolific_title_eligible("Japanese - Fluent Speakers - AI Training - Düsseldorf, Germany"))
        voice = prolific()
        voice["content"] += " Join live video calls and record your voice."
        self.assertIsNone(mod._prolific_job(voice))


if __name__ == "__main__":
    unittest.main()
