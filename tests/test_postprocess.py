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


def row(jid, title="AI Annotator", company="Example", tier="high", last_seen=None, published=None, first_seen=None, location="Tokyo", snippet="", remote_reasons=None, score=90):
    now = datetime.now(timezone.utc)
    return {
        "id": jid,
        "title": title,
        "company": company,
        "tier": tier,
        "location": location,
        "snippet": snippet,
        "remote_reasons": list(remote_reasons or []),
        "freshness_confidence": 90,
        "score": score,
        "automation_confidence": 95,
        "last_seen": (last_seen or now).isoformat(),
        "first_seen": (first_seen or now).isoformat(),
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

    def test_fullwidth_percent_remote_contradiction_is_dropped(self):
        kept, dropped = mod.drop_remote_contradictions([row("a", snippet="100％リモートではありません")])
        self.assertEqual(kept, [])
        self.assertEqual(dropped, 1)

    def test_negative_remote_reason_is_dropped_even_with_positive_wording(self):
        kept, dropped = mod.drop_remote_contradictions([
            row("a", snippet="フルリモート中心のデータ入力", remote_reasons=["フルリモート", "注意:ハイブリッド"])
        ])
        self.assertEqual(kept, [])
        self.assertEqual(dropped, 1)

    def test_negated_hybrid_wording_is_not_false_rejected(self):
        kept, dropped = mod.drop_remote_contradictions([
            row("a", snippet="完全在宅で、ハイブリッド勤務は不可です", remote_reasons=["完全在宅", "注意:ハイブリッド"])
        ])
        self.assertEqual(len(kept), 1)
        self.assertEqual(dropped, 0)

    def test_recent_missing_job_is_carried_as_review_reserve_without_refreshing_last_seen(self):
        now = datetime.now(timezone.utc)
        old_seen = now - timedelta(days=10)
        carried = mod.carryover_rows([], [row("a", last_seen=old_seen)], now)
        self.assertEqual(len(carried), 1)
        self.assertEqual(carried[0]["tier"], "review")
        self.assertTrue(carried[0]["carryover"])
        self.assertTrue(carried[0]["pool_reserve"])
        self.assertEqual(carried[0]["last_seen"], old_seen.isoformat())
        self.assertLessEqual(carried[0]["freshness_confidence"], 58)

    def test_missing_job_older_than_14_days_is_dropped(self):
        now = datetime.now(timezone.utc)
        self.assertEqual(mod.carryover_rows([], [row("a", last_seen=now - timedelta(days=15))], now), [])

    def test_published_over_30_days_is_not_carried(self):
        now = datetime.now(timezone.utc)
        self.assertEqual(mod.carryover_rows([], [row("a", last_seen=now - timedelta(hours=2), published=now - timedelta(days=31))], now), [])

    def test_live_review_ranks_ahead_of_stronger_scored_reserve_review(self):
        now = datetime.now(timezone.utc)
        live = row("live", company="Live", tier="review", score=55, first_seen=now)
        reserve = row("reserve", company="Reserve", tier="review", score=95, last_seen=now - timedelta(days=2), first_seen=now - timedelta(days=5))
        got = mod.process({"generated_at": now.isoformat(), "jobs": [live]}, {"jobs": [reserve]})
        self.assertEqual(got["jobs"][0]["id"], "live")
        self.assertEqual(got["jobs"][1]["id"], "reserve")
        self.assertTrue(got["jobs"][1]["carryover"])

    def test_remote_text_check_ranks_after_stronger_remote_evidence(self):
        now = datetime.now(timezone.utc)
        clear = row("clear", company="Clear", tier="review", score=60)
        weak = row("weak", company="Weak", tier="review", score=95)
        weak["remote_search_only"] = True
        got = mod.process({"generated_at": now.isoformat(), "jobs": [weak, clear]}, None)
        self.assertEqual([x["id"] for x in got["jobs"][:2]], ["clear", "weak"])

    def test_process_reports_supply_health(self):
        now = datetime.now(timezone.utc)
        current = [row("new", company="New", tier="review", first_seen=now)]
        previous = [row("old", company="Old", tier="review", last_seen=now - timedelta(days=2), first_seen=now - timedelta(days=3))]
        payload = {"generated_at": now.isoformat(), "candidate_display_target": 30, "jobs": current}
        got = mod.process(payload, {"jobs": previous})
        self.assertEqual(got["candidate_pool_size"], 2)
        self.assertEqual(got["new_jobs"], 1)
        self.assertEqual(got["live_jobs"], 1)
        self.assertEqual(got["carryover_jobs"], 1)
        self.assertTrue(got["pool_under_display_target"])

    def test_pool_is_capped_at_one_hundred(self):
        now = datetime.now(timezone.utc)
        rows = [row(str(i), title=f"Role {i}", company=f"Company {i}", last_seen=now) for i in range(130)]
        got = mod.process({"generated_at": now.isoformat(), "jobs": rows}, None)
        self.assertEqual(len(got["jobs"]), 100)
        self.assertEqual(got["candidate_pool_size"], 100)
        self.assertFalse(got["pool_under_display_target"])


if __name__ == "__main__":
    unittest.main()
