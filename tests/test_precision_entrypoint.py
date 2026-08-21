import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


class PrecisionEntrypointTests(unittest.TestCase):
    def test_production_refresh_uses_indeed_first_quota_wrapper(self):
        workflow = (ROOT / ".github/workflows/update-jobs.yml").read_text(encoding="utf-8")
        self.assertIn("run: python scripts/acquisition_indeed_first.py", workflow)
        self.assertNotIn("run: python scripts/acquisition_supply_yield.py", workflow)
        indeed_first = (ROOT / "scripts/acquisition_indeed_first.py").read_text(encoding="utf-8")
        self.assertIn("import acquisition_precision", indeed_first)
        self.assertIn("acquisition_precision.main()", indeed_first)

    def test_healthy_pool_reserves_structured_search_quota_for_indeed(self):
        path = SCRIPTS / "acquisition_indeed_first.py"
        spec = importlib.util.spec_from_file_location("acquisition_indeed_first_test", path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        self.assertTrue(mod.should_skip_structured_search({"candidate_pool_size": 30, "jobs": []}))
        self.assertTrue(mod.should_skip_structured_search({"candidate_pool_size": 0, "jobs": [{}] * 30}))
        self.assertFalse(mod.should_skip_structured_search({"candidate_pool_size": 29, "jobs": [{}] * 29}))

    def test_precision_wrapper_keeps_existing_supply_pipeline_as_underlying_engine(self):
        wrapper = (ROOT / "scripts/acquisition_precision.py").read_text(encoding="utf-8")
        self.assertIn("import acquisition_supply_yield as supply", wrapper)
        self.assertIn("import profile_precision_v8 as profile_precision", wrapper)
        self.assertIn("import apply_sources", wrapper)
        self.assertIn("profiles = _ORIGINAL_SELECT(previous_payload)", wrapper)
        self.assertIn("profile_precision.augment_profiles", wrapper)
        self.assertIn("profile_precision.order_profiles", wrapper)
        self.assertIn("profile_precision.actual_order", wrapper)
        self.assertIn("stamp_attempt_telemetry", wrapper)
        self.assertIn("candidate_search_zero_result_profiles", wrapper)
        self.assertIn("trusted_source_build_row", wrapper)
        self.assertIn("candidate_apply_destination_policy", wrapper)
        self.assertIn("candidate_trusted_apply_ats_domains", wrapper)
        self.assertIn("candidate_trusted_apply_provider_domains", wrapper)
        self.assertIn("SAFE_INTERNAL_MONTHLY_CAP = 245", wrapper)
        self.assertIn("serpapi_provider_guard_remains_authoritative", wrapper)
        self.assertIn("profile_precision.learning_metadata", wrapper)
        self.assertIn("supply.main()", wrapper)


if __name__ == "__main__":
    unittest.main()
