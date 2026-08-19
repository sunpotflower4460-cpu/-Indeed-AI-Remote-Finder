import importlib.util
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

path = SCRIPTS / "fetch_pool.py"
spec = importlib.util.spec_from_file_location("fetch_pool", path)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class PoolFetchTests(unittest.TestCase):
    def test_supply_targets_are_large_enough_for_daily_applications(self):
        self.assertEqual(mod.POOL_TARGET_MIN, 30)
        self.assertEqual(mod.POOL_TARGET_MAX, 80)
        self.assertGreaterEqual(mod.BOOTSTRAP_SEARCHES_PER_RUN, 12)
        self.assertLess(mod.NORMAL_SEARCHES_PER_RUN, mod.BOOTSTRAP_SEARCHES_PER_RUN)

    def test_query_bank_is_broad_and_rotating(self):
        self.assertGreaterEqual(len(mod.QUERY_BANK), 10)
        categories = {category for category, _ in mod.QUERY_BANK}
        for expected in {"data_entry", "annotation", "research", "ec", "qa", "office"}:
            self.assertIn(expected, categories)

    def test_previous_pool_size_ignores_expired_rows(self):
        now = datetime.now(timezone.utc)
        payload = {
            "jobs": [
                {"tier": "review", "search_published_at": (now - timedelta(days=2)).isoformat()},
                {"tier": "review", "search_published_at": (now - timedelta(days=31)).isoformat()},
                {"tier": "high", "search_published_at": (now - timedelta(days=3)).isoformat()},
            ]
        }
        self.assertEqual(mod.current_pool_size(payload), 2)

    def test_next_best_digital_role_can_be_review_without_becoming_high(self):
        job = {
            "title": "完全在宅 リサーチ事務",
            "company_name": "Example",
            "location": "日本",
            "description": "フルリモートでデータ収集、情報収集、Excel集計、記事作成を行います。",
            "detected_extensions": {"posted_at": "1日前"},
            "apply_options": [{"title": "Indeed", "link": "https://jp.indeed.com/viewjob?jk=review123"}],
        }
        row = mod.build_pool_row(job, "research", {})
        self.assertIsNotNone(row)
        self.assertEqual(row["tier"], "review")

    def test_hard_physical_role_is_never_kept_as_reserve_candidate(self):
        job = {
            "title": "完全在宅 商品登録と梱包",
            "company_name": "Example",
            "location": "日本",
            "description": "商品登録、データ入力、梱包、商品撮影を担当します。",
            "detected_extensions": {"posted_at": "1日前"},
            "apply_options": [{"title": "Indeed", "link": "https://jp.indeed.com/viewjob?jk=physical123"}],
        }
        self.assertIsNone(mod.build_pool_row(job, "ec", {}))

    def test_serpapi_guard_leaves_headroom(self):
        self.assertLessEqual(mod.DEFAULT_MONTHLY_SEARCH_CAP, 225)
        self.assertGreater(mod.DEFAULT_MONTHLY_SEARCH_CAP, 180)


if __name__ == "__main__":
    unittest.main()
