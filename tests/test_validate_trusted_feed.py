import importlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

sources = importlib.import_module("apply_sources")
validator = importlib.import_module("validate_feed_trusted")


class TrustedFeedValidatorTests(unittest.TestCase):
    def row_for(self, url: str) -> dict:
        target = sources.find_trusted_apply({"apply_options": [{"title": "apply", "link": url}]})
        self.assertIsNotNone(target)
        return {
            "id": target.job_id,
            "url": target.url,
            "apply_source": target.source,
            "apply_source_kind": target.kind,
            "trusted_apply_policy_version": 2,
        }

    def test_audited_ats_rows_revalidate_with_deterministic_identity(self):
        for url in (
            "https://jobs.lever.co/weloglobal/abc123",
            "https://jobs.ashbyhq.com/lilt-production/abc123/application",
            "https://job-boards.greenhouse.io/prolific/jobs/4750669101",
            "https://job-boards.eu.greenhouse.io/agency/jobs/4629002101",
        ):
            with self.subTest(url=url):
                self.assertTrue(validator.trusted_apply_row_valid(self.row_for(url)))

    def test_wrong_identity_or_unknown_host_is_rejected(self):
        row = self.row_for("https://jobs.ashbyhq.com/lilt-production/abc123/application")
        row["id"] = "tampered"
        self.assertFalse(validator.trusted_apply_row_valid(row))
        self.assertFalse(
            validator.trusted_apply_row_valid(
                {
                    "id": "x",
                    "url": "https://unknown.invalid/jobs/x",
                    "apply_source": "Unknown",
                    "apply_source_kind": "trusted-ats",
                    "trusted_apply_policy_version": 2,
                }
            )
        )


if __name__ == "__main__":
    unittest.main()
