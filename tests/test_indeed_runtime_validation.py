import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

spec = importlib.util.spec_from_file_location(
    "validate_indeed_discovery_runtime_test",
    SCRIPTS / "validate_indeed_discovery_runtime.py",
)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class IndeedRuntimeValidationTests(unittest.TestCase):
    def base_payload(self):
        return {
            "candidate_indeed_index_version": 3,
            "candidate_indeed_index_method": (
                "google-web-rotating-public-index-to-exact-indeed-viewjob"
            ),
            "candidate_indeed_index_direct_indeed_requests": 0,
            "candidate_indeed_page_body_directly_accessed": False,
            "candidate_indeed_index_budget_surplus_before_run": 2,
            "candidate_indeed_index_request_run": 1,
            "candidate_indeed_index_query_profiles": ["ai-trainer"],
            "candidate_indeed_index_profile_count": 32,
            "candidate_indeed_index_profile_last_attempt": {"ai-trainer":"2026-08-21T00:00:00+00:00"},
            "candidate_indeed_index_profile_coverage_count": 1,
            "provider_configured": True,
        }

    def test_valid_runtime_telemetry_passes_even_with_zero_hits(self):
        payload = self.base_payload()
        payload["candidate_indeed_index_hits_run"] = 0
        payload["candidate_indeed_index_promoted_run"] = 0
        mod.validate(payload)

    def test_stale_v2_telemetry_fails(self):
        payload = self.base_payload()
        payload["candidate_indeed_index_version"] = 2
        with self.assertRaises(RuntimeError):
            mod.validate(payload)

    def test_missing_page_body_disclosure_fails(self):
        payload=self.base_payload()
        payload.pop("candidate_indeed_page_body_directly_accessed")
        with self.assertRaises(RuntimeError):
            mod.validate(payload)

    def test_inconsistent_profile_coverage_fails(self):
        payload=self.base_payload()
        payload["candidate_indeed_index_profile_coverage_count"]=2
        with self.assertRaises(RuntimeError):
            mod.validate(payload)

    def test_configured_provider_with_surplus_requires_attempt(self):
        payload = self.base_payload()
        payload["candidate_indeed_index_request_run"] = 0
        payload["candidate_indeed_index_query_profiles"] = []
        with self.assertRaises(RuntimeError):
            mod.validate(payload)

    def test_unconfigured_provider_can_skip_attempt(self):
        payload = self.base_payload()
        payload["provider_configured"] = False
        payload["candidate_indeed_index_request_run"] = 0
        payload["candidate_indeed_index_query_profiles"] = []
        mod.validate(payload)

    def test_provider_health_main_enforces_runtime_contract(self):
        source = (SCRIPTS / "stamp_provider_health.py").read_text(encoding="utf-8")
        self.assertIn("import validate_indeed_discovery_runtime", source)
        self.assertIn("validate_indeed_discovery_runtime.validate(", source)
        self.assertLess(
            source.index("validate_indeed_discovery_runtime.validate("),
            source.index("harden_indeed_index_matches.main()"),
        )


if __name__ == "__main__":
    unittest.main()
