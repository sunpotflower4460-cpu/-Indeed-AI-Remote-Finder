import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class RefreshResilienceWorkflowTests(unittest.TestCase):
    def test_acquisition_failure_does_not_hide_refresh_diagnostics(self):
        workflow = (ROOT / ".github/workflows/update-jobs.yml").read_text(encoding="utf-8")
        self.assertIn("id: acquisition", workflow)
        acquisition_block = workflow[
            workflow.index("- name: Refresh diverse autonomous-work candidates"):
            workflow.index("- name: Stamp safe provider guard diagnostics")
        ]
        self.assertIn("continue-on-error: true", acquisition_block)
        self.assertIn("python scripts/acquisition_precision.py", acquisition_block)

        wrapper = (ROOT / "scripts/acquisition_precision.py").read_text(encoding="utf-8")
        self.assertIn("import acquisition_supply_yield as supply", wrapper)
        self.assertIn("supply.main()", wrapper)

        provider_block = workflow[
            workflow.index("- name: Stamp safe provider guard diagnostics"):
            workflow.index("- name: Stamp safe acquisition outcome")
        ]
        self.assertIn("if: always()", provider_block)

        outcome_block = workflow[
            workflow.index("- name: Stamp safe acquisition outcome"):
            workflow.index("- name: Deduplicate and maintain rolling candidate pool")
        ]
        self.assertIn("if: always()", outcome_block)
        self.assertIn("ACQUISITION_OUTCOME: ${{ steps.acquisition.outcome }}", outcome_block)
        self.assertIn("python scripts/stamp_refresh_outcome.py", outcome_block)

    def test_postprocess_runs_after_a_failed_acquisition(self):
        workflow = (ROOT / ".github/workflows/update-jobs.yml").read_text(encoding="utf-8")
        postprocess_block = workflow[
            workflow.index("- name: Deduplicate and maintain rolling candidate pool"):
            workflow.index("- name: Optional LLM second-opinion audit")
        ]
        self.assertIn("if: always()", postprocess_block)
        self.assertIn("postprocess_feed.py", postprocess_block)

    def test_refresh_never_rebases_stale_generated_data_onto_newer_main(self):
        workflow = (ROOT / ".github/workflows/update-jobs.yml").read_text(encoding="utf-8")
        commit_block = workflow[workflow.index("- name: Commit refreshed feed"):]
        self.assertIn("git fetch origin main", commit_block)
        self.assertIn('"$(git rev-parse HEAD)" != "$(git rev-parse origin/main)"', commit_block)
        self.assertIn("skipping stale generated-feed commit", commit_block)
        self.assertIn("git push origin HEAD:main", commit_block)
        self.assertNotIn("git pull --rebase", commit_block)


if __name__ == "__main__":
    unittest.main()
