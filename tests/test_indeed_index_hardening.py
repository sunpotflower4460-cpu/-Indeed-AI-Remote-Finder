import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

path = SCRIPTS / "harden_indeed_index_matches.py"
spec = importlib.util.spec_from_file_location("indeed_index_hardening_test", path)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class IndeedIndexHardeningTests(unittest.TestCase):
    def promoted_row(self, company="Example AI"):
        return {
            "id": "stable-id",
            "title": "Japanese AI Rater",
            "company": company,
            "url": "https://jp.indeed.com/viewjob?jk=ABCDEF123456",
            "apply_source": "Indeed",
            "apply_source_kind": "indeed",
            "original_apply_url": "https://jobs.example.com/rater",
            "original_apply_source": "Greenhouse",
            "original_apply_source_kind": "trusted-ats",
            "indeed_index_match_version": 1,
            "indeed_index_jk": "ABCDEF123456",
        }

    def test_company_evidence_keeps_promotion_and_restamps_counts(self):
        payload = {
            "jobs": [self.promoted_row()],
            "candidate_indeed_index_seeds": [
                {
                    "jk": "ABCDEF123456",
                    "title": "Japanese AI Rater - Example AI",
                    "snippet": "Example AI 完全在宅",
                }
            ],
        }
        got = mod.process(payload)
        row = got["jobs"][0]
        self.assertEqual(row["apply_source_kind"], "indeed")
        self.assertTrue(row["indeed_index_company_confirmed"])
        self.assertEqual(got["candidate_final_indeed_apply_jobs"], 1)
        self.assertEqual(got["candidate_indeed_index_hardening_kept"], 1)

    def test_same_title_from_different_company_is_reverted(self):
        payload = {
            "jobs": [self.promoted_row(company="Example AI")],
            "candidate_indeed_index_seeds": [
                {
                    "jk": "ABCDEF123456",
                    "title": "Japanese AI Rater - Different Corp",
                    "snippet": "Different Corp 完全在宅",
                }
            ],
        }
        got = mod.process(payload)
        row = got["jobs"][0]
        self.assertEqual(row["url"], "https://jobs.example.com/rater")
        self.assertEqual(row["apply_source"], "Greenhouse")
        self.assertEqual(row["apply_source_kind"], "trusted-ats")
        self.assertTrue(row["indeed_index_promotion_reverted"])
        self.assertEqual(got["candidate_final_indeed_apply_jobs"], 0)
        self.assertEqual(got["candidate_final_other_trusted_apply_jobs"], 1)
        self.assertEqual(got["candidate_indeed_index_hardening_reverted"], 1)

    def test_missing_seed_fails_closed_when_company_is_known(self):
        payload = {"jobs": [self.promoted_row()], "candidate_indeed_index_seeds": []}
        got = mod.process(payload)
        self.assertEqual(got["jobs"][0]["apply_source_kind"], "trusted-ats")
        self.assertEqual(got["candidate_final_indeed_apply_jobs"], 0)

    def test_generic_company_does_not_create_false_negative(self):
        payload = {
            "jobs": [self.promoted_row(company="非公開")],
            "candidate_indeed_index_seeds": [
                {"jk": "ABCDEF123456", "title": "Japanese AI Rater", "snippet": "完全在宅"}
            ],
        }
        got = mod.process(payload)
        self.assertEqual(got["jobs"][0]["apply_source_kind"], "indeed")
        self.assertFalse(got["jobs"][0]["indeed_index_company_confirmed"])

    def test_workflow_health_stamp_applies_hardening_before_postprocess(self):
        stamp_source = (SCRIPTS / "stamp_provider_health.py").read_text(encoding="utf-8")
        workflow = (ROOT / ".github/workflows/update-jobs.yml").read_text(encoding="utf-8")
        self.assertIn("harden_indeed_index_matches.main()", stamp_source)
        self.assertLess(
            workflow.index("python scripts/stamp_provider_health.py"),
            workflow.index("python scripts/postprocess_feed.py --previous /tmp/previous-jobs.json"),
        )


if __name__ == "__main__":
    unittest.main()
