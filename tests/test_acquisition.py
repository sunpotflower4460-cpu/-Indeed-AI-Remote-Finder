import importlib.util
import sys
import unittest
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


class AcquisitionTests(unittest.TestCase):
    def test_shallow_pool_gets_aggressive_replenishment(self):
        self.assertEqual(mod.request_limit_for_pool(0), 10)
        self.assertEqual(mod.request_limit_for_pool(29), 10)
        self.assertEqual(mod.request_limit_for_pool(30), 6)
        self.assertEqual(mod.request_limit_for_pool(49), 6)
        self.assertEqual(mod.request_limit_for_pool(50), 4)
        self.assertEqual(mod.request_limit_for_pool(79), 4)
        self.assertEqual(mod.request_limit_for_pool(80), 2)

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

    def test_build_row_does_not_trust_deprecated_remote_api_filter(self):
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

    def test_small_monthly_request_cap_is_honored(self):
        with patch.dict(mod.os.environ, {"SERPAPI_MONTHLY_REQUEST_CAP": "25"}):
            self.assertEqual(mod.configured_monthly_cap(), 25)


if __name__ == "__main__":
    unittest.main()
