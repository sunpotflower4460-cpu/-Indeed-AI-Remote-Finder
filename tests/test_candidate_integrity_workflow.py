import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CandidateIntegrityWorkflowTests(unittest.TestCase):
    def test_daily_and_free_refill_apply_integrity_before_final_validation(self):
        for relative in (
            ".github/workflows/update-jobs.yml",
            ".github/workflows/free-ats-refill.yml",
        ):
            text = (ROOT / relative).read_text(encoding="utf-8")
            gate = text.index("python scripts/apply_candidate_integrity_gate.py")
            remote_validator = text.index("python scripts/validate_remote_feed.py")
            integrity_validator = text.index("python scripts/validate_candidate_integrity.py")
            self.assertLess(gate, remote_validator)
            self.assertLess(gate, integrity_validator)

    def test_pages_bundles_integrity_layer_before_cache_continuity_ux_and_source_tabs(self):
        workflow = (ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8")
        self.assertIn(
            "cat integrity.js refill.js continuity.js ux.js source-tabs.js >> _site/app.js",
            workflow,
        )
        self.assertLess(workflow.index("integrity.js"), workflow.index("continuity.js"))
        self.assertLess(workflow.index("continuity.js"), workflow.index("ux.js"))
        self.assertLess(workflow.index("ux.js"), workflow.index("source-tabs.js"))

    def test_pwa_integrity_layer_evicts_old_cache_and_requires_row_stamp(self):
        source = (ROOT / "integrity.js").read_text(encoding="utf-8")
        self.assertIn("candidateIntegrityCacheMigrationV1", source)
        self.assertIn("localStorage.removeItem(LOCAL_CACHE_KEY)", source)
        self.assertIn("candidate_integrity_gate_version", source)
        self.assertIn("human_identity_dependency==='none-detected'", source)

    def test_check_workflow_syntax_checks_every_browser_layer(self):
        workflow = (ROOT / ".github/workflows/check.yml").read_text(encoding="utf-8")
        for filename in (
            "app.js",
            "integrity.js",
            "refill.js",
            "continuity.js",
            "ux.js",
            "source-tabs.js",
            "sw.js",
        ):
            self.assertIn(f"node --check {filename}", workflow)


if __name__ == "__main__":
    unittest.main()
