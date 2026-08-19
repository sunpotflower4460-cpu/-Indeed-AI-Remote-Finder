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

    def test_discovery_uses_broad_remote_terms_but_stays_task_focused(self):
        self.assertIn("在宅ワーク", mod.DISCOVERY_REMOTE_QUERY)
        self.assertIn("リモートワーク", mod.DISCOVERY_REMOTE_QUERY)
        self.assertIn("完全在宅", mod.DISCOVERY_REMOTE_QUERY)
        forbidden = ("電話営業", "テレアポ", "接客", "訪問営業", "コールセンター")
        for name, query in mod.PRODUCTION_QUERY_PROFILES:
            self.assertTrue(any(term in query for term in ("在宅", "リモート", "remote")), name)
            for term in forbidden:
                self.assertNotIn(term, query, name)

    def test_deep_budget_can_run_through_31_day_month(self):
        self.assertEqual(mod.DEEP_REQUESTS, 7)
        self.assertLessEqual(mod.DEEP_REQUESTS * 31, 220)

    def test_request_budget_tapers_as_pool_grows(self):
        self.assertEqual(mod.supply_request_limit(0), 7)
        self.assertEqual(mod.supply_request_limit(19), 7)
        self.assertEqual(mod.supply_request_limit(20), 6)
        self.assertEqual(mod.supply_request_limit(49), 6)
        self.assertEqual(mod.supply_request_limit(50), 4)
        self.assertEqual(mod.supply_request_limit(99), 4)
        self.assertEqual(mod.supply_request_limit(100), 2)

    def test_supply_configuration_prefers_breadth_over_page_two(self):
        mod.configure_supply_rotation()
        self.assertEqual(mod.acquisition.MAX_REQUESTS_PER_RUN, 7)
        self.assertEqual(mod.acquisition.QUERY_PROFILES, mod.PRODUCTION_QUERY_PROFILES)
        self.assertGreater(len(mod.acquisition.QUERY_PROFILES), mod.acquisition.MAX_REQUESTS_PER_RUN)
        self.assertEqual(mod.acquisition.request_limit_for_pool(4), 7)


if __name__ == "__main__":
    unittest.main()
