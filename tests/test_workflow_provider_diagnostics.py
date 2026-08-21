import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ProviderDiagnosticsWorkflowTests(unittest.TestCase):
    def test_test_only_changes_do_not_trigger_paid_candidate_refresh(self):
        workflow = (ROOT / ".github/workflows/update-jobs.yml").read_text(encoding="utf-8")
        self.assertIn("- 'scripts/**'", workflow)
        self.assertIn("- '.github/workflows/update-jobs.yml'", workflow)
        self.assertNotIn("- 'tests/**'", workflow)

    def test_safe_provider_health_is_stamped_after_acquisition(self):
        workflow = (ROOT / ".github/workflows/update-jobs.yml").read_text(encoding="utf-8")
        refresh = "run: python scripts/acquisition_indeed_first.py"
        stamp = "run: python scripts/stamp_provider_health.py"
        postprocess = "run: python scripts/postprocess_feed.py --previous /tmp/previous-jobs.json"
        self.assertIn(refresh, workflow)
        self.assertIn(stamp, workflow)
        self.assertIn("SERPAPI_KEY: ${{ secrets.SERPAPI_KEY }}", workflow)
        self.assertLess(workflow.index(refresh), workflow.index(stamp))
        self.assertLess(workflow.index(stamp), workflow.index(postprocess))

        wrapper = (ROOT / "scripts/acquisition_precision.py").read_text(encoding="utf-8")
        self.assertIn("import acquisition_supply_yield as supply", wrapper)
        self.assertIn("supply.main()", wrapper)
        indeed_first = (ROOT / "scripts/acquisition_indeed_first.py").read_text(encoding="utf-8")
        self.assertIn("SerpApi quota reserved for dedicated Indeed discovery", indeed_first)

    def test_diagnostics_script_does_not_persist_raw_account_fields(self):
        script = (ROOT / "scripts/stamp_provider_health.py").read_text(encoding="utf-8")
        self.assertIn('"serpapi_guard_status"', script)
        self.assertIn('"serpapi_safe_request_headroom"', script)
        self.assertNotIn('result["api_key"]', script)
        self.assertNotIn('result["account_email"]', script)


if __name__ == "__main__":
    unittest.main()
