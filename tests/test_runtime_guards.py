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

    def test_production_uses_provider_account_budget_guard(self):
        adapter = (ROOT / "scripts" / "acquisition_remote.py").read_text(encoding="utf-8")
        self.assertIn('ACCOUNT_API_URL = "https://serpapi.com/account.json"', adapter)
        self.assertIn('account.get("this_hour_searches")', adapter)
        self.assertIn('account.get("account_rate_limit_per_hour")', adapter)
        self.assertIn('account.get("this_month_usage")', adapter)
        self.assertIn('account.get("total_searches_left")', adapter)
        self.assertIn("provider_cap == 0", adapter)
        self.assertNotIn('print(account', adapter)
        self.assertNotIn('json.dumps(account', adapter)

    def test_production_uses_rotating_explicit_full_remote_supply(self):
        workflow = (ROOT / ".github" / "workflows" / "update-jobs.yml").read_text(encoding="utf-8")
        supply = (ROOT / "scripts" / "acquisition_supply.py").read_text(encoding="utf-8")
        quality = (ROOT / "scripts" / "acquisition_quality.py").read_text(encoding="utf-8")
        self.assertIn("python scripts/acquisition_supply.py", workflow)
        self.assertNotIn("run: python scripts/acquisition_remote.py", workflow)
        self.assertIn("PRODUCTION_QUERY_PROFILES", supply)
        self.assertIn("DEEP_REQUESTS = 15", supply)
        self.assertIn("MID_REQUESTS = 10", supply)
        self.assertIn("TOPUP_REQUESTS = 6", supply)
        self.assertIn('"rotating-explicit-full-remote-first-pages"', supply)
        self.assertIn("acquisition.QUERY_PROFILES = list(PRODUCTION_QUERY_PROFILES)", supply)
        self.assertIn("acquisition_quality.configure_quality_policy()", supply)
        self.assertNotIn("R = acquisition.REMOTE_QUERY", supply)
        self.assertIn('"完全在宅"', supply)
        self.assertIn("acquisition.serpapi_fetch = GENERIC_SERPAPI_FETCH", quality)
        self.assertIn("remote_api_filter=False", quality)
        self.assertIn('row.get("remote_search_only") is True', quality)

    def test_ai_substitution_policy_excludes_synchronous_attention_work(self):
        adapter = (ROOT / "scripts" / "acquisition_remote.py").read_text(encoding="utf-8")
        quality = (ROOT / "scripts" / "acquisition_quality.py").read_text(encoding="utf-8")
        postprocess = (ROOT / "scripts" / "postprocess_feed.py").read_text(encoding="utf-8")
        self.assertIn("SERVER_POOL_TARGET = 100", adapter)
        self.assertIn('"問い合わせ対応"', adapter)
        self.assertIn('"常時監視"', adapter)
        self.assertIn('"会議参加"', adapter)
        self.assertIn('"顧客折衝"', adapter)
        self.assertIn('"調整業務"', quality)
        self.assertIn('"進捗管理"', quality)
        self.assertIn("REVIEW_AUTOMATION_MIN = 55", quality)
        self.assertIn("REVIEW_HUMAN_RISK_MAX = 25", quality)
        self.assertIn('row["quality_gate"] = QUALITY_GATE', quality)
        self.assertIn('old.get("quality_gate") != QUALITY_GATE', postprocess)
        self.assertIn('"ai-substitutable-async-remote"', adapter)

    def test_daily_schedule_preserves_search_budget(self):
        workflow = (ROOT / ".github" / "workflows" / "update-jobs.yml").read_text(encoding="utf-8")
        self.assertIn("cron: '17 0 * * *'", workflow)
        self.assertNotIn("*/8", workflow)

    def test_recommendation_queue_tracks_100_stock_favorites_declines_and_daily_ten(self):
        app = (ROOT / "app.js").read_text(encoding="utf-8")
        index = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn("const DEFAULT_VISIBLE=30", app)
        self.assertIn("const DAILY_TARGET=10", app)
        self.assertIn("const SERVER_POOL_TARGET=100", app)
        self.assertIn("const LOCAL_POOL_LIMIT=250", app)
        self.assertIn("candidateCacheV2", app)
        self.assertIn("mode:'all'", app)
        self.assertIn("declinedJobs", app)
        self.assertIn("savedJobs", app)
        self.assertIn("if(isDeclined||isApplied)return false", app)
        self.assertIn("rows.slice(0,state.displayLimit)", app)
        self.assertIn("state.displayLimit+=DEFAULT_VISIBLE", app)
        self.assertIn("appliedAt", app)
        self.assertIn("remote_search_only", app)
        self.assertIn('class="chip active" data-mode="all"', index)
        self.assertIn('data-mode="favorite"', index)
        self.assertIn('data-mode="declined"', index)
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
        self.assertIn("ai-remote-finder-v10", sw)
        self.assertIn("await cache.put(key,response)", sw)
        self.assertIn("cacheKey:DATA_URL", sw)
        self.assertIn("cacheKey:INDEX_URL", sw)
        self.assertNotIn("caches.open(CACHE).then(c=>c.put", sw)


if __name__ == "__main__":
    unittest.main()
