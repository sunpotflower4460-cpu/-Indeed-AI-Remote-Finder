import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class RuntimeGuardTests(unittest.TestCase):
    def test_optional_llm_provider_failure_is_redacted_and_nonfatal(self):
        workflow = (ROOT / ".github/workflows/update-jobs.yml").read_text(encoding="utf-8")
        self.assertIn("continue-on-error: true", workflow)
        self.assertIn('data["llm_fatal_error"] = None', workflow)
        self.assertIn("2>/tmp/llm-review.err", workflow)
        self.assertIn("2>/tmp/llm-review-tier.err", workflow)
        self.assertLess(workflow.index('data["llm_fatal_error"] = None'), workflow.index("- name: Validate generated feed"))

    def test_interrupted_primary_llm_audit_reserves_full_run_budget(self):
        workflow = (ROOT / ".github/workflows/update-jobs.yml").read_text(encoding="utf-8")
        self.assertIn("steps.llm_audit.outcome != 'success'", workflow)
        self.assertIn("--max-new-reviews 0", workflow)
        self.assertIn('current["llm_attempts_uncertain"] = True', workflow)
        self.assertIn("attempts + 8", workflow)

    def test_review_tier_audit_uses_only_shared_eight_attempt_cap(self):
        workflow = (ROOT / ".github/workflows/update-jobs.yml").read_text(encoding="utf-8")
        quality_llm = (ROOT / "scripts/llm_review_quality.py").read_text(encoding="utf-8")
        self.assertIn("--run-attempt-cap 8", workflow)
        self.assertIn("RUN_ATTEMPT_CAP = 8", quality_llm)
        self.assertIn("remaining_run", quality_llm)
        self.assertIn("previous_attempts", quality_llm)
        self.assertIn("spent_this_run", quality_llm)

    def test_llm_quality_veto_runs_before_validation(self):
        workflow = (ROOT / ".github/workflows/update-jobs.yml").read_text(encoding="utf-8")
        self.assertIn("python scripts/apply_llm_quality_gate.py", workflow)
        self.assertLess(workflow.index("python scripts/apply_llm_quality_gate.py"), workflow.index("python scripts/validate_remote_feed.py"))

    def test_final_gate_rejects_human_attendance_not_automatable_online_state(self):
        gate = (ROOT / "scripts/apply_llm_quality_gate.py").read_text(encoding="utf-8")
        validator = (ROOT / "scripts/validate_remote_feed.py").read_text(encoding="utf-8")
        for needle in (
            '"カメラ常時on"',
            '"zoom常時接続"',
            '"pc前で待機"',
            '"在席必須"',
            '"must remain at your computer"',
            "PRESENCE_GATE_VERSION = 1",
        ):
            self.assertIn(needle, gate)
        self.assertNotIn('    "常時ログイン",', gate)
        self.assertNotIn('    "オンライン待機",', gate)
        self.assertIn("presence_requirement_signal", validator)
        self.assertIn("continuous_presence_risk", validator)
        self.assertIn("candidate_requires_no_continuous_human_presence", validator)

    def test_pre_presence_local_candidate_cache_is_purged_once(self):
        index = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn("presenceGateCacheMigrationV1", index)
        self.assertIn("localStorage.removeItem('candidateCacheV3')", index)
        self.assertIn("localStorage.setItem(migration,'1')", index)
        self.assertLess(index.index("presenceGateCacheMigrationV1"), index.index('<script src="./app.js"></script>'))

    def test_production_update_uses_strict_remote_validator(self):
        workflow = (ROOT / ".github/workflows/update-jobs.yml").read_text(encoding="utf-8")
        check = (ROOT / ".github/workflows/check.yml").read_text(encoding="utf-8")
        self.assertIn("python scripts/validate_remote_feed.py", workflow)
        self.assertIn("python scripts/validate_remote_feed.py", check)

    def test_serpapi_secret_is_referenced_without_logging_value(self):
        workflow = (ROOT / ".github/workflows/update-jobs.yml").read_text(encoding="utf-8")
        self.assertIn("SERPAPI_KEY: ${{ secrets.SERPAPI_KEY }}", workflow)
        self.assertNotIn('echo "$SERPAPI_KEY"', workflow)
        self.assertNotIn("printenv SERPAPI_KEY", workflow)

    def test_provider_account_budget_guard_remains_active(self):
        adapter = (ROOT / "scripts/acquisition_remote.py").read_text(encoding="utf-8")
        for needle in (
            'ACCOUNT_API_URL = "https://serpapi.com/account.json"',
            'account.get("this_hour_searches")',
            'account.get("account_rate_limit_per_hour")',
            'account.get("this_month_usage")',
            'account.get("total_searches_left")',
        ):
            self.assertIn(needle, adapter)

    def test_broad_discovery_keeps_strict_v2_publication(self):
        supply = (ROOT / "scripts/acquisition_supply.py").read_text(encoding="utf-8")
        quality = (ROOT / "scripts/acquisition_quality.py").read_text(encoding="utf-8")
        self.assertIn("DEEP_REQUESTS = 7", supply)
        self.assertIn("DEEP_REQUESTS * 31 <= 220", supply)
        self.assertIn("DISCOVERY_REMOTE_QUERY", supply)
        self.assertIn('"在宅ワーク"', supply)
        self.assertIn('"リモートワーク"', supply)
        self.assertIn("QUALITY_POLICY_VERSION = 2", quality)
        self.assertIn('QUALITY_GATE = "async-ai-remote-v2"', quality)
        self.assertIn("REVIEW_AUTOMATION_MIN = 64", quality)
        self.assertIn("REVIEW_HUMAN_RISK_MAX = 18", quality)
        self.assertIn("REVIEW_AUTOMATION_SIGNAL_MIN = 2", quality)
        self.assertIn("explicit_full_remote_evidence", quality)
        self.assertIn("RICH_SNIPPET_MAX = 6000", quality)
        self.assertIn("human_presence_blocker", quality)
        self.assertIn('row["full_listing_presence_screened"] = True', quality)
        self.assertIn('payload["candidate_full_listing_presence_screened"] = True', quality)
        self.assertIn("remote_api_filter=False", quality)

    def test_early_attention_filter_is_context_aware(self):
        adapter = (ROOT / "scripts/acquisition_remote.py").read_text(encoding="utf-8")
        for needle in ('"問い合わせ対応"', '"会議参加"', '"顧客折衝"', '"オンコール"'):
            self.assertIn(needle, adapter)
        for needle in ('"有人監視"', '"監視オペレーター"', "AUTONOMY_HUMAN_CONTEXT_PATTERNS"):
            self.assertIn(needle, adapter)
        # Generic real-time machine work must not be a bare hard blocker.
        self.assertNotIn('    "常時監視",', adapter)
        self.assertNotIn('    "リアルタイム監視",', adapter)
        self.assertNotIn('    "即時対応",', adapter)

    def test_server_reserve_exceeds_user_display_target(self):
        adapter = (ROOT / "scripts/acquisition_remote.py").read_text(encoding="utf-8")
        self.assertIn("USER_DISPLAY_TARGET = 100", adapter)
        self.assertIn("SERVER_POOL_TARGET = 150", adapter)
        self.assertIn("acquisition.DISPLAY_TARGET = USER_DISPLAY_TARGET", adapter)
        self.assertIn("acquisition.POOL_TARGET = SERVER_POOL_TARGET", adapter)
        self.assertIn("acquisition.POOL_LIMIT = SERVER_POOL_TARGET", adapter)

    def test_ai_substitution_policy_excludes_synchronous_attention_work(self):
        quality = (ROOT / "scripts/acquisition_quality.py").read_text(encoding="utf-8")
        for needle in ('"調整業務"', '"進捗管理"', '"顧客窓口"', '"エスカレーション対応"'):
            self.assertIn(needle, quality)

    def test_daily_schedule_and_month_safe_supply(self):
        workflow = (ROOT / ".github/workflows/update-jobs.yml").read_text(encoding="utf-8")
        supply = (ROOT / "scripts/acquisition_supply.py").read_text(encoding="utf-8")
        self.assertIn("cron: '17 0 * * *'", workflow)
        self.assertNotIn("*/8", workflow)
        self.assertIn("DEEP_REQUESTS = 7", supply)

    def test_client_migrates_to_v3_cache_and_v2_quality_gate(self):
        app = (ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn("candidateCacheV3", app)
        self.assertNotIn("candidateCacheV2", app)
        self.assertIn("QUALITY_POLICY_VERSION=2", app)
        self.assertIn("QUALITY_GATE='async-ai-remote-v2'", app)
        self.assertIn("REVIEW_AUTOMATION_MIN=64", app)
        self.assertIn("REVIEW_HUMAN_RISK_MAX=18", app)
        self.assertIn("llmQualityRejected", app)
        self.assertIn("qualityEligible", app)

    def test_recommendation_queue_keeps_user_actions(self):
        app = (ROOT / "app.js").read_text(encoding="utf-8")
        index = (ROOT / "index.html").read_text(encoding="utf-8")
        for needle in ("const DEFAULT_VISIBLE=30", "const DAILY_TARGET=10", "declinedJobs", "savedJobs", "appliedAt"):
            self.assertIn(needle, app)
        for needle in ('data-mode="favorite"', 'data-mode="declined"', 'id="todayApplied"', 'id="refreshFeed"'):
            self.assertIn(needle, index)

    def test_actions_use_node24_setup_python(self):
        for relative in (Path(".github/workflows/check.yml"), Path(".github/workflows/update-jobs.yml")):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("actions/setup-python@v6", text, str(relative))
            self.assertNotIn("actions/setup-python@v5", text, str(relative))

    def test_service_worker_rotated_and_awaits_cache_writes(self):
        sw = (ROOT / "sw.js").read_text(encoding="utf-8")
        self.assertIn("ai-remote-finder-v11", sw)
        self.assertIn("await cache.put(key,response)", sw)
        self.assertIn("cacheKey:DATA_URL", sw)
        self.assertIn("cacheKey:INDEX_URL", sw)
        self.assertNotIn("caches.open(CACHE).then(c=>c.put", sw)


if __name__ == "__main__":
    unittest.main()
