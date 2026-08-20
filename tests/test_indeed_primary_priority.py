import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

path = SCRIPTS / "apply_sources.py"
spec = importlib.util.spec_from_file_location("apply_sources_indeed_priority_test", path)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class IndeedPrimaryPriorityTests(unittest.TestCase):
    def test_mixed_source_stock_does_not_count_as_indeed_stock(self):
        payload = {
            "jobs": [
                {
                    "apply_source_kind": "trusted-ats",
                    "url": "https://jobs.ashbyhq.com/example/abc/application",
                },
                {
                    "apply_source_kind": "trusted-provider",
                    "url": "https://oneforma.com/projects/example",
                },
            ]
        }
        self.assertEqual(mod._indeed_stock(payload), 0)

    def test_only_verified_indeed_viewjob_rows_count(self):
        payload = {
            "jobs": [
                {
                    "apply_source_kind": "indeed",
                    "url": "https://jp.indeed.com/viewjob?jk=ABCDEF123456",
                },
                {
                    "apply_source_kind": "indeed",
                    "url": "https://jp.indeed.com/jobs?q=remote",
                },
                {
                    "apply_source_kind": "trusted-ats",
                    "url": "https://jobs.ashbyhq.com/example/abc/application",
                },
            ]
        }
        self.assertEqual(mod._indeed_stock(payload), 1)

    def test_production_entrypoint_prioritizes_indeed_until_target(self):
        source = path.read_text(encoding="utf-8")
        self.assertIn("INDEED_PRIMARY_STOCK_TARGET = 30", source)
        self.assertIn("endswith(\"/acquisition_precision.py\")", source)
        self.assertIn("stock < INDEED_PRIMARY_STOCK_TARGET", source)
        self.assertIn("SOURCE_RECOVERY_QUERY_PROFILES", source)
        self.assertIn("indeed-primary-stock-low", source)


if __name__ == "__main__":
    unittest.main()
