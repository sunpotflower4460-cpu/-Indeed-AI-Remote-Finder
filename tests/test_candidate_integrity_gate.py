import importlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

mod = importlib.import_module("apply_candidate_integrity_gate")


def row(title, company="Example", location="Japan (Remote)", snippet="fully remote フルリモート AI評価 データ評価", **extra):
    value = {
        "id": extra.pop("id", title),
        "title": title,
        "company": company,
        "location": location,
        "snippet": snippet,
        "tier": extra.pop("tier", "review"),
        "score": extra.pop("score", 80),
        "automation_confidence": extra.pop("automation_confidence", 90),
        "remote_confidence": extra.pop("remote_confidence", 100),
        "freshness_confidence": extra.pop("freshness_confidence", 80),
    }
    value.update(extra)
    return value


class CandidateIntegrityGateTests(unittest.TestCase):
    def test_rejects_us_based_remote_listing(self):
        candidate = row(
            "Medical Translators - Burmese - US-based",
            company="LILT",
            location="USA (Remote)",
            snippet="Fully remote. Applicants must be currently based in the United States of America.",
        )
        out = mod.apply({"jobs": [candidate]})
        self.assertEqual(out["jobs"], [])
        self.assertEqual(out["candidate_integrity_dropped"], 1)

    def test_keeps_japan_and_worldwide_remote_work(self):
        candidates = [
            row("Japanese AI Trainer", location="Japan (Remote)"),
            row("Japanese Language Specialist", location="World Wide - Remote"),
        ]
        out = mod.apply({"jobs": candidates})
        self.assertEqual(len(out["jobs"]), 2)
        statuses = {item["japan_eligibility_status"] for item in out["jobs"]}
        self.assertIn("japan-explicit", statuses)
        self.assertIn("worldwide-explicit", statuses)

    def test_rejects_own_voice_or_likeness_collection(self):
        candidate = row(
            "Japanese Multimodal Contributor",
            snippet=(
                "Fully remote. Services include providing recordings of your voice and likeness "
                "and submit content featuring only yourself."
            ),
        )
        out = mod.apply({"jobs": [candidate]})
        self.assertEqual(out["jobs"], [])
        self.assertGreater(out["candidate_integrity_dropped"], 0)

    def test_rejects_personal_account_and_activity_history_dependency(self):
        candidate = row(
            "Maps Personalization Relevance Rater",
            snippet=(
                "Fully remote. An existing, actively used Gmail account with prior usage history "
                "on Google Maps is required. Results are personalized based on your activity history."
            ),
        )
        out = mod.apply({"jobs": [candidate]})
        self.assertEqual(out["jobs"], [])

    def test_rejects_explicit_uninterrupted_human_session(self):
        candidate = row(
            "AI Trainer - Japanese",
            snippet="Fully remote. You must be prepared to complete paid tasks that require one hour of uninterrupted work.",
        )
        out = mod.apply({"jobs": [candidate]})
        self.assertEqual(out["jobs"], [])

    def test_collapses_prolific_city_variants_into_one_role_family(self):
        candidates = [
            row(
                "Japanese - Fluent Speakers - AI Training - Chiba, Japan",
                company="Prolific Academic Ltd",
                location="Remote",
                id="chiba",
                freshness_confidence=70,
            ),
            row(
                "Japanese - Fluent Speakers - AI Training - Hiroshima, Japan",
                company="Prolific Academic Ltd",
                location="Remote",
                id="hiroshima",
                freshness_confidence=80,
            ),
            row(
                "Japanese - Fluent Speakers - AI Training - Japan",
                company="Prolific Academic Ltd",
                location="Remote",
                id="japan",
                freshness_confidence=90,
            ),
        ]
        out = mod.apply({"jobs": candidates})
        self.assertEqual(len(out["jobs"]), 1)
        self.assertEqual(out["candidate_semantic_duplicates_dropped"], 2)
        self.assertEqual(out["jobs"][0]["duplicate_count"], 3)
        self.assertEqual(out["jobs"][0]["id"], "japan")

    def test_does_not_merge_distinct_lilt_subject_matter_roles(self):
        candidates = [
            row("Subject Matter Expert – Mathematics (Japanese) – Remote", company="LILT", id="math"),
            row("Subject Matter Expert – Finance (Japanese) – Remote", company="LILT", id="finance"),
        ]
        out = mod.apply({"jobs": candidates})
        self.assertEqual(len(out["jobs"]), 2)
        self.assertEqual(out["candidate_semantic_duplicates_dropped"], 0)

    def test_active_validator_requires_row_stamp_and_unique_family(self):
        payload = {
            "candidate_integrity_gate_version": 1,
            "jobs": [row("Japanese AI Trainer")],
        }
        errors = mod.validate_active_payload(payload)
        self.assertTrue(any("missing integrity-gate stamp" in value for value in errors))

    def test_inactive_validator_is_backward_compatible_with_current_feed(self):
        self.assertEqual(mod.validate_active_payload({"jobs": [row("Legacy")]}), [])


if __name__ == "__main__":
    unittest.main()
