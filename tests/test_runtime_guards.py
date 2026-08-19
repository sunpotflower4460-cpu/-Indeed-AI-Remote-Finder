import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class RuntimeGuardTests(unittest.TestCase):
    def test_optional_llm_provider_failure_is_redacted_and_nonfatal(self):
        workflow = (ROOT / ".github" / "workflows" / "update-jobs.yml").read_text(encoding="utf-8")
        self.assertIn("continue-on-error: true", workflow)
        self.assertIn('data["llm_fatal_error"] = None', workflow)
        self.assertIn('data["llm_error_status"] = status', workflow)
        self.assertIn("2>/tmp/llm-review.err", workflow)
        self.assertLess(
            workflow.index('data["llm_fatal_error"] = None'),
            workflow.index("- name: Validate generated feed"),
        )

    def test_interrupted_llm_audit_cannot_silently_drop_cache(self):
        workflow = (ROOT / ".github" / "workflows" / "update-jobs.yml").read_text(encoding="utf-8")
        self.assertIn("id: llm_audit", workflow)
        self.assertIn("timeout-minutes: 10", workflow)
        self.assertIn("steps.llm_audit.outcome != 'success'", workflow)
        self.assertIn("--max-new-reviews 0", workflow)
        self.assertIn("/tmp/previous-jobs.json", workflow)
        self.assertIn('current["llm_attempts_uncertain"] = True', workflow)
        self.assertIn("attempts + 8", workflow)

    def test_actions_use_node24_setup_python(self):
        for relative in (
            Path(".github/workflows/check.yml"),
            Path(".github/workflows/update-jobs.yml"),
        ):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("actions/setup-python@v6", text, str(relative))
            self.assertNotIn("actions/setup-python@v5", text, str(relative))

    def test_service_worker_awaits_cache_writes(self):
        sw = (ROOT / "sw.js").read_text(encoding="utf-8")
        self.assertIn("ai-remote-finder-v7", sw)
        self.assertIn("await cache.put(key,response)", sw)
        self.assertIn("cacheKey:DATA_URL", sw)
        self.assertIn("cacheKey:INDEX_URL", sw)
        self.assertNotIn("caches.open(CACHE).then(c=>c.put", sw)


if __name__ == "__main__":
    unittest.main()
