import importlib.util
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "scripts" / "postprocess_feed.py"
spec = importlib.util.spec_from_file_location("postprocess", path)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def row(jid, title="AI Annotator", company="Example", tier="high", last_seen=None, published=None, location="Tokyo", snippet="", remote_reasons=None):
    now = datetime.now(timezone.utc)
    return {
        "id": jid,
        "title": title,
        "company": company,
        "tier": tier,
        "location": location,
        "snippet": snippet,
        "remote_reasons": list(remote_reasons or ["完全在宅"]),
        "freshness_confidence": 90,
        "score": 90,
        "automation_confidence": 95,
        "last_seen": (last_seen or now).isoformat(),
        "first_seen": (now - timedelta(days=1)).isoformat(),
        "search_published_at": (published or (now - timedelta(days=2))).isoformat(),
    }


class PostprocessTests(unittest.TestCase):
    def test_duplicate_company_title_collapses(self):
        rows = [row("a", location="Tokyo"), row("b", location="Osaka")]
        got, removed = mod.dedupe_rows(rows)
        self.assertEqual(len(got), 1)
        self.assertEqual(removed, 1)
        self.assertEqual(got[0]["duplicate_count"], 2)
        self.assertEqual(set(got[0]["alternate_locations"]), {"Tokyo", "Osaka"})

    def test_same_title_without_company_does_not_collapse(self):
        rows = [row("a", company="", location="Tokyo"), row("b", company="", location="Osaka")]
        got, removed = mod.dedupe_rows(rows)
        self.assertEqual(len(got), 2)
        self.assertEqual(removed, 0)

    def test_explicit_full_remote_contradiction_is_dropped(self):
        kept, dropped = mod.drop_remote_contradictions([row("a", snippet="業務はフルリモート不可です")])
        self.assertEqual(kept, [])
        self.assertEqual(dropped, 1)

    def test_negative_remote_reason_is_dropped(self):
        kept, dropped = mod.drop_remote_contradictions([
            row("a", snippet="フルリモート中心", remote_reasons=["フルリモート", "注意:週2出社"])
        ])
        self.assertEqual(kept, [])
        self.assertEqual(dropped, 1)

    def test_negated_hybrid_wording_is_not_false_rejected(self):
        kept, dropped = mod.drop_remote_contradictions([
            row("a", snippet="完全在宅で、ハイブリッド勤務は不可です", remote_reasons=["完全在宅", "注意:ハイブリッド"])
        ])
        self.assertEqual(len(kept), 1)
        self.assertEqual(dropped, 0)

    def test_missing_job_is_retained_as_review_reserve(self):
        now = datetime.now(timezone.utc)
        carried = mod.carryover_rows([], [row("a", last_seen=now - timedelta(days=5))], now)
        self.assertEqual(len(carried), 1)
        self.assertEqual(carried[0]["tier"], "review")
        self.assertTrue(carried[0]["carryover"])
        self.assertTrue(carried[0]["pool_reserve"])
        self.assertIn("最大14日", carried[0]["carryover_reason"])

    def test_reserve_row_does_not_refresh_last_seen(self):
        now = datetime.now(timezone.utc)
        old_seen = now - timedelta(days=5)
        carried = mod.carryover_rows([], [row("a", last_seen=old_seen)], now)
        self.assertEqual(carried[0]["last_seen"], old_seen.isoformat())

    def test_missing_job_older_than_14_days_is_dropped(self):
        now = datetime.now(timezone.utc)
        carried = mod.carryover_rows([], [row("a", last_seen=now - timedelta(days=15))], now)
        self.assertEqual(carried, [])

    def test_published_over_30_days_is_not_carried(self):
        now = datetime.now(timezone.utc)
        carried = mod.carryover_rows([], [row("a", last_seen=now - timedelta(days=2), published=now - timedelta(days=31))], now)
        self.assertEqual(carried, [])

    def test_process_reports_pool_health_and_new_jobs(self):
        now = datetime.now(timezone.utc)
        current = {"generated_at": now.isoformat(), "jobs": [row("new")], "pool_target_min": 30, "pool_target_max": 80}
        previous = {"jobs": [row("old", last_seen=now - timedelta(days=2))]}
        got = mod.process(current, previous)
        self.assertEqual(got["candidate_pool_size"], 2)
        self.assertEqual(got["new_jobs"], 1)
        self.assertEqual(got["carryover_jobs"], 1)
        self.assertTrue(got["pool_under_target"])

    def test_process_caps_visible_pool_at_80(self):
        now = datetime.now(timezone.utc)
        rows = [row(str(i), title=f"Role {i}", company=f"Company {i}") for i in range(100)]
        got = mod.process({"generated_at": now.isoformat(), "jobs": rows}, {})
        self.assertEqual(len(got["jobs"]), 80)
        self.assertEqual(got["candidate_pool_size"], 80)
        self.assertFalse(got["pool_under_target"])


if __name__ == "__main__":
    unittest.main()
