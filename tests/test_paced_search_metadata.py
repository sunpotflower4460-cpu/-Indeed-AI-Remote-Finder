import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

path = SCRIPTS / "acquisition_supply_yield.py"
spec = importlib.util.spec_from_file_location("paced_search_metadata_test", path)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class PacedSearchMetadataTests(unittest.TestCase):
    def test_effective_limit_prefers_paced_limit(self):
        payload = {"serpapi_effective_request_limit": 4, "query_total": 7}
        self.assertEqual(mod.effective_request_limit(payload), 4)

    def test_effective_limit_falls_back_to_actual_query_total(self):
        self.assertEqual(mod.effective_request_limit({"query_total": 3}), 3)

    def test_recovery_reports_every_effective_request_as_source_targeted(self):
        got = mod.search_window_minima(True, 4)
        self.assertEqual(
            got,
            {"anchors": 0, "indeed_bias": 4, "ordinary": 0, "source_targeted": 4},
        )

    def test_normal_nominal_window_keeps_three_anchors_and_both_classes(self):
        got = mod.search_window_minima(False, 7)
        self.assertEqual(got["anchors"], 3)
        self.assertEqual(got["indeed_bias"], 1)
        self.assertEqual(got["ordinary"], 1)
        self.assertEqual(got["source_targeted"], 1)

    def test_normal_four_request_paced_window_reports_two_anchors(self):
        got = mod.search_window_minima(False, 4)
        self.assertEqual(got["anchors"], 2)
        self.assertEqual(got["indeed_bias"], 1)
        self.assertEqual(got["ordinary"], 1)

    def test_short_window_does_not_overpromise_both_anchor_classes(self):
        got = mod.search_window_minima(False, 3)
        self.assertEqual(got["anchors"], 1)
        self.assertEqual(got["indeed_bias"], 0)
        self.assertEqual(got["ordinary"], 0)
        self.assertEqual(got["source_targeted"], 0)


if __name__ == "__main__":
    unittest.main()
