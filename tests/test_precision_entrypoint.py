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
        self.assertIn("import profile_precision_v4 as profile_precision", wrapper)
        self.assertIn("profiles = _ORIGINAL_SELECT(previous_payload)", wrapper)
        self.assertIn("profile_precision.order_profiles", wrapper)
        self.assertIn("profile_precision.learning_metadata", wrapper)
        self.assertIn("supply.main()", wrapper)


if __name__ == "__main__":
    unittest.main()
