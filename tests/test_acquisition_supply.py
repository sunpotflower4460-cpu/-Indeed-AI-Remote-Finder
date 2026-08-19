import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

path = SCRIPTS / "acquisition_supply.py"
spec = importlib.util.spec_from_file_location("acquisition_supply_test", path)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class AcquisitionSupplyTests(unittest.TestCase):
    def test_many_distinct_async_profiles_are_available(self):
        profiles = mod.PRODUCTION_QUERY_PROFILES
        self.assertGreaterEqual(len(profiles), 60)
        names = [name for name, _ in profiles]
        self.assertEqual(len(names), len(set(names)))

    def test_queries_remain_remote_and_task_focused(self):
        forbidden = ("電話営業", "テレアポ", "接客", "訪問営業", "コールセンター")
        for name, query in mod.PRODUCTION_QUERY_PROFILES:
            self.assertIn("リモート", query, name)
            for term in forbidden:
                self.assertNotIn(term, query, name)

    def test_request_budget_tapers_as_pool_grows(self):
        self.assertEqual(mod.supply_request_limit(0), 15)
        self.assertEqual(mod.supply_request_limit(19), 15)
        self.assertEqual(mod.supply_request_limit(20), 10)
        self.assertEqual(mod.supply_request_limit(49), 10)
        self.assertEqual(mod.supply_request_limit(50), 6)
        self.assertEqual(mod.supply_request_limit(99), 6)
        self.assertEqual(mod.supply_request_limit(100), 2)

    def test_supply_configuration_prefers_breadth_over_page_two(self):
        mod.configure_supply_rotation()
        self.assertEqual(mod.acquisition.MAX_REQUESTS_PER_RUN, 15)
        self.assertEqual(mod.acquisition.QUERY_PROFILES, mod.PRODUCTION_QUERY_PROFILES)
        self.assertGreater(len(mod.acquisition.QUERY_PROFILES), mod.acquisition.MAX_REQUESTS_PER_RUN)
        self.assertEqual(mod.acquisition.request_limit_for_pool(4), 15)


if __name__ == "__main__":
    unittest.main()