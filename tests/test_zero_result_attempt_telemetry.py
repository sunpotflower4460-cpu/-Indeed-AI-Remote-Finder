import importlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

entry = importlib.import_module("acquisition_precision")
v4 = importlib.import_module("profile_precision_v4")


class ZeroResultAttemptTelemetryTests(unittest.TestCase):
    def test_successful_zero_result_profile_is_added_to_yield_rows(self):
        payload = {
            "serpapi_requests_run": 2,
            "serpapi_paginated_requests_run": 0,
            "errors": [],
            "candidate_search_profile_yield": [
                {
                    "profile": "profile-positive",
                    "seen": 5,
                    "apply_options": 5,
                    "indeed_apply": 2,
                    "accepted": 1,
                }
            ],
        }
        planned = [("profile-zero", "q0"), ("profile-positive", "q1")]
        entry.stamp_attempt_telemetry(payload, planned)
        rows = {row["profile"]: row for row in payload["candidate_search_profile_yield"]}
        self.assertEqual(rows["profile-zero"]["search_attempts"], 1)
        self.assertEqual(rows["profile-zero"]["successful_search_attempts"], 1)
        self.assertEqual(rows["profile-zero"]["zero_result_attempts"], 1)
        self.assertEqual(rows["profile-positive"]["search_attempts"], 1)
        self.assertNotIn("zero_result_attempts", rows["profile-positive"])
        self.assertEqual(payload["candidate_search_zero_result_profiles"], ["profile-zero"])
        self.assertEqual(payload["candidate_search_zero_result_profile_count"], 1)
        self.assertIn("profile-zero", v4._recently_searched_profiles(payload))

    def test_provider_failure_is_not_mislabeled_as_zero_result(self):
        payload = {
            "serpapi_requests_run": 1,
            "serpapi_paginated_requests_run": 0,
            "errors": ["profile-failed: TimeoutError"],
            "candidate_search_profile_yield": [],
        }
        entry.stamp_attempt_telemetry(payload, [("profile-failed", "q")])
        row = payload["candidate_search_profile_yield"][0]
        self.assertEqual(row["search_attempts"], 1)
        self.assertEqual(row["query_failures"], 1)
        self.assertNotIn("successful_search_attempts", row)
        self.assertNotIn("zero_result_attempts", row)
        self.assertEqual(payload["candidate_search_failed_profiles"], ["profile-failed"])
        self.assertEqual(payload["candidate_search_zero_result_profile_count"], 0)

    def test_page_two_requests_do_not_create_fake_first_page_profile_attempts(self):
        payload = {
            "serpapi_requests_run": 3,
            "serpapi_paginated_requests_run": 1,
            "errors": [],
            "candidate_search_profile_yield": [],
        }
        planned = [("first", "q0"), ("second", "q1"), ("not-first-page", "q2")]
        entry.stamp_attempt_telemetry(payload, planned)
        self.assertEqual(payload["candidate_search_first_page_attempts"], 2)
        self.assertEqual(payload["candidate_search_attempted_profiles"], ["first", "second"])
        names = [row["profile"] for row in payload["candidate_search_profile_yield"]]
        self.assertNotIn("not-first-page", names)


if __name__ == "__main__":
    unittest.main()
