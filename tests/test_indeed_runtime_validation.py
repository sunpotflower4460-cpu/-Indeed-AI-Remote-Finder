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
            "candidate_indeed_index_version": 4,
            "candidate_indeed_index_method": (
                "google-public-index-viewjob-jk-plus-search-vjk-to-indeed-job-key"
            ),
            "candidate_indeed_index_direct_indeed_requests": 0,
            "candidate_indeed_page_body_directly_accessed": False,
            "candidate_indeed_index_budget_surplus_before_run": 2,
            "candidate_indeed_index_request_run": 1,
            "candidate_indeed_index_query_profiles": ["ai-trainer"],
            "candidate_indeed_index_profile_count": 40,
            "candidate_indeed_index_profile_last_attempt": {
                "ai-trainer": "2026-08-21T00:00:00+00:00"
            },
            "candidate_indeed_index_profile_coverage_count": 1,
            "candidate_indeed_index_hits_run": 0,
            "candidate_indeed_index_exact_url_hits_run": 0,
            "candidate_indeed_index_search_vjk_hits_run": 0,
            "candidate_indeed_index_seeds": [],
            "candidate_indeed_index_exact_url_seed_count": 0,
            "candidate_indeed_index_search_vjk_seed_count": 0,
            "provider_configured": True,
        }

    def direct_seed(self):
        return {
            "jk": "ABCDEF123456",
            "url": "https://jp.indeed.com/viewjob?jk=ABCDEF123456",
            "title": "Japanese AI Rater",
            "indeed_index_link_kind": "viewjob-jk",
            "indeed_job_key_verified": True,
            "indeed_job_title_verified": True,
            "indeed_exact_url_verified": True,
            "indeed_canonical_url_derived_from_vjk": False,
            "indeed_promotion_eligible": True,
            "indeed_page_body_verified": False,
        }

    def vjk_seed(self):
        return {
            "jk": "VJKKEY123456",
            "url": "https://jp.indeed.com/viewjob?jk=VJKKEY123456",
            "title": "",
            "indexed_page_title": "AIトレーナー 在宅の求人",
            "indeed_index_link_kind": "search-vjk",
            "indeed_job_key_verified": True,
            "indeed_job_title_verified": False,
            "indeed_exact_url_verified": False,
            "indeed_canonical_url_derived_from_vjk": True,
            "indeed_promotion_eligible": False,
            "indeed_page_body_verified": False,
        }

    def test_valid_runtime_telemetry_passes_even_with_zero_hits(self):
        mod.validate(self.base_payload())

    def test_valid_mixed_seed_evidence_passes(self):
        payload = self.base_payload()
        payload["candidate_indeed_index_hits_run"] = 2
        payload["candidate_indeed_index_exact_url_hits_run"] = 1
        payload["candidate_indeed_index_search_vjk_hits_run"] = 1
        payload["candidate_indeed_index_seeds"] = [self.direct_seed(), self.vjk_seed()]
        payload["candidate_indeed_index_exact_url_seed_count"] = 1
        payload["candidate_indeed_index_search_vjk_seed_count"] = 1
        mod.validate(payload)

    def test_stale_v3_telemetry_fails(self):
        payload = self.base_payload()
        payload["candidate_indeed_index_version"] = 3
        with self.assertRaises(RuntimeError):
            mod.validate(payload)

    def test_missing_page_body_disclosure_fails(self):
        payload = self.base_payload()
        payload.pop("candidate_indeed_page_body_directly_accessed")
        with self.assertRaises(RuntimeError):
            mod.validate(payload)

    def test_inconsistent_profile_coverage_fails(self):
        payload = self.base_payload()
        payload["candidate_indeed_index_profile_coverage_count"] = 2
        with self.assertRaises(RuntimeError):
            mod.validate(payload)

    def test_inconsistent_hit_mix_fails(self):
        payload = self.base_payload()
        payload["candidate_indeed_index_hits_run"] = 1
        with self.assertRaises(RuntimeError):
            mod.validate(payload)

    def test_vjk_seed_cannot_claim_exact_url_or_promotion(self):
        payload = self.base_payload()
        bad = self.vjk_seed()
        bad["indeed_exact_url_verified"] = True
        bad["indeed_promotion_eligible"] = True
        payload["candidate_indeed_index_seeds"] = [bad]
        payload["candidate_indeed_index_search_vjk_seed_count"] = 1
        with self.assertRaises(RuntimeError):
            mod.validate(payload)

    def test_vjk_seed_cannot_claim_verified_job_title(self):
        payload = self.base_payload()
        bad = self.vjk_seed()
        bad["title"] = "Japanese AI Rater"
        bad["indeed_job_title_verified"] = True
        payload["candidate_indeed_index_seeds"] = [bad]
        payload["candidate_indeed_index_search_vjk_seed_count"] = 1
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
