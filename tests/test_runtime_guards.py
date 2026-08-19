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

    def test_production_update_uses_strict_remote_validator(self):
        workflow = (ROOT / ".github" / "workflows" / "update-jobs.yml").read_text(encoding="utf-8")
        check = (ROOT / ".github" / "workflows" / "check.yml").read_text(encoding="utf-8")
        self.assertIn("python scripts/validate_remote_feed.py", workflow)
        self.assertIn("python scripts/validate_remote_feed.py", check)
        self.assertLess(
            workflow.index("python scripts/validate_remote_feed.py"),
            workflow.index("- name: Commit refreshed feed"),
        )

    def test_serpapi_secret_is_referenced_without_logging_value(self):
        workflow = (ROOT / ".github" / "workflows" / "update-jobs.yml").read_text(encoding="utf-8")
        self.assertIn("SERPAPI_KEY: ${{ secrets.SERPAPI_KEY }}", workflow)
        self.assertNotIn('echo "$SERPAPI_KEY"', workflow)
        self.assertNotIn("printenv SERPAPI_KEY", workflow)

    def test_production_uses_remote_adapter_and_paginated_replenishment(self):
        workflow = (ROOT / ".github" / "workflows" / "update-jobs.yml").read_text(encoding="utf-8")
        adapter = (ROOT / "scripts" / "acquisition_remote.py").read_text(encoding="utf-8")
        acquisition = (ROOT / "scripts" / "acquisition.py").read_text(encoding="utf-8")
        self.assertIn("python scripts/acquisition_remote.py", workflow)
        self.assertIn('"ltype": "1"', adapter)
        self.assertIn("remote_api_filter=True", adapter)
        self.assertIn("next_page_token", adapter)
        self.assertIn("serpapi_pagination", adapter)
        self.assertIn('pagination.get("next")', adapter)
        self.assertIn('host not in {"serpapi.com", "www.serpapi.com"}', adapter)
        self.assertIn("pagination_queue", acquisition)
        self.assertIn("MAX_REQUESTS_PER_RUN = 30", acquisition)
        self.assertNotIn("run: python scripts/fetch_jobs.py", workflow)

    def test_daily_schedule_preserves_search_budget(self):
        workflow = (ROOT / ".github" / "workflows" / "update-jobs.yml").read_text(encoding="utf-8")
        self.assertIn("cron: '17 0 * * *'", workflow)
        self.assertNotIn("*/8", workflow)

    def test_recommendation_queue_defaults_to_all_hides_applied_and_tracks_daily_ten(self):
        app = (ROOT / "app.js").read_text(encoding="utf-8")
        index = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn("const DEFAULT_VISIBLE=30", app)
        self.assertIn("const DAILY_TARGET=10", app)
        self.assertIn("mode:'all'", app)
        self.assertIn("if(isHidden||isApplied)return false", app)
        self.assertIn("rows.slice(0,state.displayLimit)", app)
        self.assertIn("state.displayLimit+=DEFAULT_VISIBLE", app)
        self.assertIn("appliedAt", app)
        self.assertIn("remote_search_only", app)
        self.assertIn('class="chip active" data-mode="all"', index)
        self.assertIn('id="todayApplied"', index)
        self.assertIn('id="countAvailable"', index)
        self.assertIn('id="refreshFeed"', index)

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
        self.assertIn("ai-remote-finder-v9", sw)
        self.assertIn("await cache.put(key,response)", sw)
        self.assertIn("cacheKey:DATA_URL", sw)
        self.assertIn("cacheKey:INDEX_URL", sw)
        self.assertNotIn("caches.open(CACHE).then(c=>c.put", sw)


if __name__ == "__main__":
    unittest.main()
