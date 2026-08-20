import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PrecisionEntrypointTests(unittest.TestCase):
    def test_production_refresh_uses_adaptive_precision_wrapper(self):
        workflow = (ROOT / ".github/workflows/update-jobs.yml").read_text(encoding="utf-8")
        self.assertIn("run: python scripts/acquisition_precision.py", workflow)
        self.assertNotIn("run: python scripts/acquisition_supply_yield.py", workflow)

    def test_precision_wrapper_keeps_existing_supply_pipeline_as_underlying_engine(self):
        wrapper = (ROOT / "scripts/acquisition_precision.py").read_text(encoding="utf-8")
        self.assertIn("import acquisition_supply_yield as supply", wrapper)
        self.assertIn("import profile_precision_v7 as profile_precision", wrapper)
        self.assertIn("import apply_sources", wrapper)
        self.assertIn("profiles = _ORIGINAL_SELECT(previous_payload)", wrapper)
        self.assertIn("profile_precision.augment_profiles", wrapper)
        self.assertIn("profile_precision.order_profiles", wrapper)
        self.assertIn("profile_precision.actual_order", wrapper)
        self.assertIn("stamp_attempt_telemetry", wrapper)
        self.assertIn("candidate_search_zero_result_profiles", wrapper)
        self.assertIn("trusted_source_build_row", wrapper)
        self.assertIn("candidate_apply_destination_policy", wrapper)
        self.assertIn("SAFE_INTERNAL_MONTHLY_CAP = 245", wrapper)
        self.assertIn("serpapi_provider_guard_remains_authoritative", wrapper)
        self.assertIn("profile_precision.learning_metadata", wrapper)
        self.assertIn("supply.main()", wrapper)


if __name__ == "__main__":
    unittest.main()
