import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

path = SCRIPTS / "acquisition_remote.py"
spec = importlib.util.spec_from_file_location("provider_budget_monotonic_test", path)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class ProviderBudgetMonotonicTests(unittest.TestCase):
    def _configured_count(self, local_usage: int, provider_usage: int) -> int:
        month = mod.acquisition.month_key()
        payload = {
            "serpapi_budget_month": month,
            "serpapi_requests_month": local_usage,
        }
        account = {
            "this_month_usage": provider_usage,
            "account_rate_limit_per_hour": 100,
            "this_hour_searches": 0,
            "total_searches_left": 100,
        }

        def local_count(data, requested_month):
            if requested_month == month:
                return int(data.get("serpapi_requests_month") or 0)
            return 0

        with patch.object(mod, "fetch_serpapi_account", return_value=account), patch.object(
            mod.acquisition, "previous_request_count", side_effect=local_count
        ), patch.object(
            mod.acquisition, "request_limit_for_pool", side_effect=lambda _: 7
        ):
            mod.configure_provider_budget("secret")
            return mod.acquisition.previous_request_count(payload, month)

    def test_lagging_provider_sample_cannot_roll_local_usage_back(self):
        self.assertEqual(self._configured_count(local_usage=176, provider_usage=173), 176)

    def test_provider_sample_can_raise_usage_when_it_is_ahead(self):
        self.assertEqual(self._configured_count(local_usage=176, provider_usage=190), 190)


if __name__ == "__main__":
    unittest.main()
