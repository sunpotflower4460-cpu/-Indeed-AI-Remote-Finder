import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

path = SCRIPTS / "stamp_provider_health.py"
spec = importlib.util.spec_from_file_location("stamp_provider_health_test", path)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class ProviderHealthTests(unittest.TestCase):
    def test_not_configured_is_explicit_and_secret_free(self):
        got = mod.safe_status("")
        self.assertEqual(got["serpapi_guard_status"], "not-configured")
        self.assertIsNone(got["serpapi_safe_request_headroom"])
        self.assertNotIn("api_key", got)
        self.assertNotIn("account_email", got)

    def test_ready_uses_only_coarse_account_numbers(self):
        account = {
            "account_rate_limit_per_hour": 50,
            "this_hour_searches": 10,
            "total_searches_left": 140,
            "this_month_usage": 110,
            "account_email": "private@example.com",
            "api_key": "SUPER_SECRET",
        }
        with patch.object(mod.acquisition_remote, "fetch_serpapi_account", return_value=account):
            got = mod.safe_status("SUPER_SECRET")
        self.assertEqual(got["serpapi_guard_status"], "ready")
        self.assertEqual(got["serpapi_safe_request_headroom"], 38)
        self.assertEqual(got["serpapi_provider_month_usage"], 110)
        serialized = json.dumps(got)
        self.assertNotIn("SUPER_SECRET", serialized)
        self.assertNotIn("private@example.com", serialized)

    def test_zero_headroom_is_visible_without_raw_provider_payload(self):
        account = {
            "account_rate_limit_per_hour": 50,
            "this_hour_searches": 50,
            "total_searches_left": 100,
        }
        with patch.object(mod.acquisition_remote, "fetch_serpapi_account", return_value=account):
            got = mod.safe_status("secret")
        self.assertEqual(got["serpapi_guard_status"], "no-safe-request-headroom")
        self.assertEqual(got["serpapi_safe_request_headroom"], 0)

    def test_account_failure_is_redacted(self):
        with patch.object(
            mod.acquisition_remote,
            "fetch_serpapi_account",
            side_effect=RuntimeError("provider said api_key=SECRET account_email=private@example.com"),
        ):
            got = mod.safe_status("SECRET")
        self.assertEqual(got["serpapi_guard_status"], "account-check-unavailable")
        serialized = json.dumps(got)
        self.assertNotIn("SECRET", serialized)
        self.assertNotIn("private@example.com", serialized)

    def test_stamp_preserves_feed_and_adds_only_safe_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = Path(tmp) / "jobs.json"
            feed.write_text(json.dumps({"jobs": [], "provider_configured": True}), encoding="utf-8")
            account = {
                "account_rate_limit_per_hour": 50,
                "this_hour_searches": 49,
                "total_searches_left": 100,
                "this_month_usage": 111,
                "api_key": "SECRET",
            }
            with patch.object(mod.acquisition_remote, "fetch_serpapi_account", return_value=account):
                got = mod.stamp(feed, api_key="SECRET")
            self.assertEqual(got["jobs"], [])
            self.assertTrue(got["provider_configured"])
            self.assertEqual(got["serpapi_guard_status"], "no-safe-request-headroom")
            persisted = feed.read_text(encoding="utf-8")
            self.assertNotIn("SECRET", persisted)


if __name__ == "__main__":
    unittest.main()
