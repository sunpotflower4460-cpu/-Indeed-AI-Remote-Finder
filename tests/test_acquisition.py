import importlib.util
import inspect
import json
import sys
import unittest
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

path = SCRIPTS / "acquisition.py"
spec = importlib.util.spec_from_file_location("acquisition", path)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class _FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps({"jobs_results": []}).encode("utf-8")


class AcquisitionTests(unittest.TestCase):
    def test_supply_targets_support_daily_ten_applications(self):
        self.assertEqual(mod.DAILY_APPLICATION_TARGET, 10)
        self.assertEqual(mod.DISPLAY_TARGET, 30)
        self.assertEqual(mod.POOL_TARGET, 80)
        self.assertEqual(mod.POOL_LIMIT, 100)

    def test_shallow_pool_gets_aggressive_replenishment_and_page2_headroom(self):
        self.assertEqual(mod.request_limit_for_pool(0), 30)
        self.assertEqual(mod.request_limit_for_pool(29), 30)
        self.assertGreater(mod.MAX_REQUESTS_PER_RUN, len(mod.QUERY_PROFILES))
        self.assertEqual(mod.request_limit_for_pool(30), 6)
        self.assertEqual(mod.request_limit_for_pool(49), 6)
        self.assertEqual(mod.request_limit_for_pool(50), 4)
        self.assertEqual(mod.request_limit_for_pool(79), 4)
        self.assertEqual(mod.request_limit_for_pool(80), 2)

    def test_serpapi_fetch_supports_next_page_token(self):
        params = inspect.signature(mod.serpapi_fetch).parameters
        self.assertIn("next_page_token", params)

    def test_default_search_origin_is_city_level_and_no_deprecated_ltype(self):
        captured = {}

        def fake_urlopen(request, timeout=30):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            return _FakeResponse()

        with patch.dict(mod.os.environ, {}, clear=False):
            mod.os.environ.pop("SERPAPI_SEARCH_ORIGIN", None)
            with patch.object(mod.urllib.request, "urlopen", side_effect=fake_urlopen):
                mod.serpapi_fetch("完全在宅 データ入力", "secret")

        params = urllib.parse.parse_qs(urllib.parse.urlparse(captured["url"]).query)
        self.assertEqual(params["location"], ["Tokyo, Japan"])
        self.assertEqual(params["engine"], ["google_jobs"])
        self.assertNotIn("ltype", params)
        self.assertEqual(captured["timeout"], 30)

    def test_search_origin_can_be_overridden_without_changing_quality_rules(self):
        with patch.dict(mod.os.environ, {"SERPAPI_SEARCH_ORIGIN": "Osaka, Japan"}):
            self.assertEqual(mod.configured_search_origin(), "Osaka, Japan")
        self.assertEqual(mod.DEFAULT_SEARCH_ORIGIN, "Tokyo, Japan")

    def test_query_rotation_changes_starting_theme(self):
        first = mod.rotated_profiles(0)
        second = mod.rotated_profiles(1)
        self.assertEqual(first[1], second[0])
        self.assertNotEqual(first[0], second[0])

    def test_review_fallback_accepts_plausible_next_best(self):
        scores = mod.legacy.Scores(
            remote=62,
            automation=55,
            freshness=90,
            risk=10,
            overall=61,
            tier="hidden",
            remote_reasons=["在宅ワーク"],
            automation_reasons=["リサーチ"],
            risk_reasons=["電話"],
        )
        self.assertTrue(mod.review_fallback(scores, datetime.now(timezone.utc) - timedelta(days=2)))

    def test_review_fallback_rejects_high_human_risk(self):
        scores = mod.legacy.Scores(
            remote=80,
            automation=80,
            freshness=90,
            risk=70,
            overall=40,
            tier="hidden",
            remote_reasons=["完全在宅"],
            automation_reasons=["データ入力"],
            risk_reasons=["訪問"],
        )
        self.assertFalse(mod.review_fallback(scores, datetime.now(timezone.utc)))

    def test_build_row_does_not_trust_remote_api_filter_in_base_module(self):
        job = {
            "title": "完全在宅 データ入力",
            "company_name": "Example",
            "description": "完全在宅でデータ入力と転記を行います",
            "detected_extensions": {"posted_at": "1 day ago"},
            "apply_options": [{"title": "Indeed", "link": "https://jp.indeed.com/viewjob?jk=abc123"}],
        }
        scores = mod.legacy.Scores(
            remote=100,
            automation=100,
            freshness=98,
            risk=0,
            overall=99,
            tier="high",
            remote_reasons=["完全在宅"],
            automation_reasons=["データ入力", "転記"],
            risk_reasons=[],
        )
        with patch.object(mod.legacy, "score_job", return_value=scores) as score:
            row = mod.build_row(job, "structured_data", {})
        self.assertIsNotNone(row)
        self.assertFalse(score.call_args.kwargs["remote_api_filter"])

    def test_eligible_previous_count_uses_fourteen_day_window(self):
        now = datetime.now(timezone.utc)
        payload = {
            "jobs": [
                {"id": "a", "tier": "review", "last_seen": (now - timedelta(days=10)).isoformat(), "search_published_at": (now - timedelta(days=12)).isoformat()},
                {"id": "b", "tier": "review", "last_seen": (now - timedelta(days=15)).isoformat(), "search_published_at": (now - timedelta(days=15)).isoformat()},
            ]
        }
        self.assertEqual(mod.eligible_previous_count(payload, now), 1)

    def test_monthly_request_guard_leaves_headroom(self):
        self.assertLessEqual(mod.DEFAULT_MONTHLY_REQUEST_CAP, 220)
        with patch.dict(mod.os.environ, {"SERPAPI_MONTHLY_REQUEST_CAP": "25"}):
            self.assertEqual(mod.configured_monthly_cap(), 25)


if __name__ == "__main__":
    unittest.main()
