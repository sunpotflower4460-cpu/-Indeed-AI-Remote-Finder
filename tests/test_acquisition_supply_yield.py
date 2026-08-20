import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

path = SCRIPTS / "acquisition_supply_yield.py"
spec = importlib.util.spec_from_file_location("acquisition_supply_yield_test", path)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class AcquisitionSupplyYieldTests(unittest.TestCase):
    def setUp(self):
        mod.reset_yield_telemetry()
        mod.select_query_profiles({})

    def test_async_core_and_indeed_anchor_templates_are_task_focused(self):
        self.assertGreaterEqual(len(mod.ASYNC_CORE_ANCHORS), 8)
        self.assertEqual(len(mod.INDEED_BIAS_ANCHORS), 4)
        all_names = [name for name, _ in mod.EXPERIMENTAL_ANCHORS]
        self.assertEqual(len(all_names), len(set(all_names)))

        core_text = " ".join(query for _, query in mod.ASYNC_CORE_ANCHORS)
        for term in ("データ入力", "アノテーション", "AI評価", "OCR", "データラベリング"):
            self.assertIn(term, core_text)
        self.assertNotIn("翻訳", core_text)
        self.assertNotIn("ローカライズ", core_text)

        for name, query in mod.ASYNC_CORE_ANCHORS:
            self.assertNotIn(" OR ", query, name)
            self.assertLessEqual(len(query), 40, name)
        for name, query in mod.INDEED_BIAS_ANCHORS:
            self.assertIn(mod.INDEED_SOURCE_BIAS_TERM, query, name)
            self.assertTrue('"完全在宅"' in query or '"フルリモート"' in query, name)
            self.assertNotIn("site:", query, name)
            self.assertNotIn(" OR ", query, name)

    def test_every_normal_daily_window_has_three_anchors_and_both_anchor_classes(self):
        profiles = mod.PRODUCTION_QUERY_PROFILES
        size = len(profiles)
        self.assertGreaterEqual(size, mod.base.DEEP_REQUESTS)
        for start in range(size):
            window = [profiles[(start + offset) % size][0] for offset in range(mod.base.DEEP_REQUESTS)]
            anchors = [name for name in window if name.startswith("anchor_")]
            self.assertGreaterEqual(
                len(anchors),
                3,
                f"fewer than three async anchors start={start} window={window}",
            )
            self.assertTrue(
                any(name.startswith("anchor_indeed_") for name in window),
                f"missing Indeed probe start={start} window={window}",
            )
            self.assertTrue(
                any(name.startswith("anchor_core_") for name in window),
                f"missing ordinary async-core anchor start={start} window={window}",
            )

    def test_source_recovery_profiles_use_empirical_indeed_keyword_and_explicit_remote(self):
        self.assertGreaterEqual(len(mod.SOURCE_RECOVERY_QUERY_PROFILES), 14)
        for name, query in mod.SOURCE_RECOVERY_QUERY_PROFILES:
            self.assertIn(mod.INDEED_SOURCE_BIAS_TERM, query, name)
            self.assertTrue('"完全在宅"' in query or '"フルリモート"' in query, name)
            self.assertNotIn("site:", query, name)
            self.assertNotIn(" OR ", query, name)

    def test_source_recovery_activates_only_for_measured_no_indeed_bottleneck(self):
        active, ratio = mod.source_recovery_signal(
            {
                "candidate_pool_size": 0,
                "candidate_quality_evaluated_jobs": 28,
                "candidate_quality_rejection_counts": {"no-indeed-apply": 22},
            }
        )
        self.assertTrue(active)
        self.assertAlmostEqual(ratio, 22 / 28)

        for payload in (
            {
                "candidate_pool_size": 0,
                "candidate_quality_evaluated_jobs": 28,
                "candidate_quality_rejection_counts": {"no-indeed-apply": 10},
            },
            {
                "candidate_pool_size": 0,
                "candidate_quality_evaluated_jobs": 9,
                "candidate_quality_rejection_counts": {"no-indeed-apply": 9},
            },
            {
                "candidate_pool_size": mod.SOURCE_RECOVERY_POOL_CEILING,
                "candidate_quality_evaluated_jobs": 28,
                "candidate_quality_rejection_counts": {"no-indeed-apply": 22},
            },
            {},
        ):
            active, _ = mod.source_recovery_signal(payload)
            self.assertFalse(active, payload)

    def test_failed_current_recovery_enters_cooldown_and_counts_down(self):
        active, ratio, cooldown, reason = mod.source_recovery_decision(
            {
                "candidate_pool_size": 0,
                "candidate_quality_evaluated_jobs": 0,
                "candidate_quality_rejection_counts": {},
                "candidate_search_source_recovery_active": True,
                "candidate_search_source_recovery_version": mod.SOURCE_RECOVERY_VERSION,
                "candidate_search_source_recovery_trigger_ratio_pct": 78.6,
            }
        )
        self.assertFalse(active)
        self.assertEqual(ratio, 0.0)
        self.assertEqual(cooldown, mod.SOURCE_RECOVERY_COOLDOWN_RUNS)
        self.assertEqual(reason, "recovery-empty-backoff")

        active, _, cooldown, reason = mod.source_recovery_decision(
            {
                "candidate_pool_size": 0,
                "candidate_quality_evaluated_jobs": 20,
                "candidate_quality_rejection_counts": {"no-indeed-apply": 18},
                "candidate_search_source_recovery_cooldown_runs_remaining": 3,
            }
        )
        self.assertFalse(active)
        self.assertEqual(cooldown, 2)
        self.assertEqual(reason, "cooldown")

    def test_strategy_upgrade_can_retry_previous_empty_v1_once(self):
        active, ratio, cooldown, reason = mod.source_recovery_decision(
            {
                "candidate_pool_size": 0,
                "candidate_quality_evaluated_jobs": 0,
                "candidate_quality_rejection_counts": {},
                "candidate_search_source_recovery_active": True,
                "candidate_search_source_recovery_version": 1,
                "candidate_search_source_recovery_trigger_ratio_pct": 78.6,
            }
        )
        self.assertTrue(active)
        self.assertAlmostEqual(ratio, 0.786)
        self.assertEqual(cooldown, 0)
        self.assertEqual(reason, "strategy-upgrade-retry")

    def test_profile_selector_switches_to_recovery_and_can_fall_back(self):
        recovery = mod.select_query_profiles(
            {
                "candidate_pool_size": 0,
                "candidate_quality_evaluated_jobs": 20,
                "candidate_quality_rejection_counts": {"no-indeed-apply": 15},
            }
        )
        self.assertTrue(mod._ACTIVE_SOURCE_RECOVERY)
        self.assertEqual(recovery, mod.SOURCE_RECOVERY_QUERY_PROFILES)
        self.assertTrue(all(mod.INDEED_SOURCE_BIAS_TERM in query for _, query in recovery))

        normal = mod.select_query_profiles(
            {
                "candidate_pool_size": 0,
                "candidate_quality_evaluated_jobs": 20,
                "candidate_quality_rejection_counts": {"no-indeed-apply": 2},
            }
        )
        self.assertFalse(mod._ACTIVE_SOURCE_RECOVERY)
        self.assertEqual(normal, mod.PRODUCTION_QUERY_PROFILES)

    def test_rotation_keeps_same_seven_request_budget(self):
        mod.base.PRODUCTION_QUERY_PROFILES = list(mod.PRODUCTION_QUERY_PROFILES)
        mod.base.configure_supply_rotation()
        self.assertEqual(mod.acquisition.MAX_REQUESTS_PER_RUN, 7)
        self.assertEqual(mod.acquisition.request_limit_for_pool(0), 7)

    def test_telemetry_counts_apply_sources_without_persisting_urls(self):
        job = {
            "title": "完全在宅 データ入力",
            "via": "Google Jobs",
            "apply_options": [
                {"title": "Indeed", "link": "https://jp.indeed.com/viewjob?jk=SECRET_ID"},
                {"title": "Company careers", "link": "https://example.com/private-token"},
            ],
        }
        mod.observe_job(job, "anchor_indeed_data_08")
        got = mod.yield_snapshot()
        self.assertEqual(got["candidate_yield_telemetry_version"], 6)
        self.assertEqual(got["candidate_yield_jobs_seen"], 1)
        self.assertEqual(got["candidate_jobs_with_apply_options"], 1)
        self.assertEqual(got["candidate_jobs_with_indeed_apply"], 1)
        self.assertEqual(got["candidate_deterministic_gate_accepted"], 0)
        self.assertEqual(got["candidate_indeed_apply_rate_pct"], 100.0)
        self.assertEqual(got["candidate_deterministic_accept_rate_pct"], 0.0)
        self.assertEqual(got["candidate_apply_source_counts"]["Indeed"], 1)
        serialized = json.dumps(got, ensure_ascii=False)
        self.assertNotIn("SECRET_ID", serialized)
        self.assertNotIn("private-token", serialized)

    def test_no_apply_options_is_visible_as_zero_yield(self):
        mod.observe_job(
            {"title": "完全在宅 OCRチェック", "via": "Example source"},
            "ocr_validation",
        )
        got = mod.yield_snapshot()
        self.assertEqual(got["candidate_yield_jobs_seen"], 1)
        self.assertEqual(got["candidate_jobs_with_apply_options"], 0)
        self.assertEqual(got["candidate_jobs_with_indeed_apply"], 0)
        self.assertEqual(got["candidate_apply_options_coverage_pct"], 0.0)
        self.assertEqual(got["candidate_via_source_counts"]["Example source"], 1)

    def test_source_labels_are_bounded_and_normalize_indeed(self):
        self.assertEqual(mod._source_label("Apply on Indeed Japan"), "Indeed")
        self.assertLessEqual(len(mod._source_label("x" * 200)), 60)


if __name__ == "__main__":
    unittest.main()
