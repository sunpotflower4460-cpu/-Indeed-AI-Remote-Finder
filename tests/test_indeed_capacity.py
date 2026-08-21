import importlib
import sys
import unittest
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

core = importlib.import_module("indeed_index_core")
v5 = importlib.import_module("supplement_indeed_web_index_v5")


class IndeedCapacityTests(unittest.TestCase):
    def setUp(self):
        self.old_ttl = core.SEED_TTL_DAYS
        self.old_max = core.MAX_SEEDS

    def tearDown(self):
        core.SEED_TTL_DAYS = self.old_ttl
        core.MAX_SEEDS = self.old_max

    def test_capacity_is_raised_without_more_requests_per_run(self):
        self.assertEqual(v5.RESULTS_PER_QUERY, 100)
        self.assertEqual(v5.SEED_TTL_DAYS, 45)
        self.assertEqual(v5.MAX_SEEDS, 300)
        self.assertEqual(v5.MAX_REQUESTS_PER_RUN, 2)

    def test_install_applies_capacity_to_shared_merge_engine(self):
        v5.install()
        self.assertEqual(core.SEED_TTL_DAYS, 45)
        self.assertEqual(core.MAX_SEEDS, 300)
        self.assertEqual(v5.v4.RESULTS_PER_QUERY, 100)

    def test_30_day_old_seed_is_retained_but_46_day_old_seed_expires(self):
        v5.install()
        def seed(jk, age_days):
            return {
                "jk": jk,
                "url": f"https://jp.indeed.com/viewjob?jk={jk}",
                "title": "Japanese AI Rater",
                "snippet": "完全在宅",
                "last_seen": (core.NOW - timedelta(days=age_days)).isoformat(),
                "indeed_index_link_kind": "viewjob-jk",
            }

        kept = core.merge_seeds(
            [seed("KEEP123456", 30), seed("DROP123456", 46)],
            [],
        )
        keys = {item["jk"] for item in kept}
        self.assertIn("KEEP123456", keys)
        self.assertNotIn("DROP123456", keys)

    def test_seed_capacity_allows_more_than_previous_100_limit(self):
        v5.install()
        seeds = []
        for index in range(180):
            jk = f"JOB{index:09d}"
            seeds.append({
                "jk": jk,
                "url": f"https://jp.indeed.com/viewjob?jk={jk}",
                "title": f"AI Rater {index}",
                "snippet": "完全在宅",
                "last_seen": core.NOW.isoformat(),
                "indeed_index_link_kind": "viewjob-jk",
            })
        merged = core.merge_seeds([], seeds)
        self.assertEqual(len(merged), 180)


if __name__ == "__main__":
    unittest.main()
