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


def row(jid, title="AI Annotator", company="Example", tier="high", last_seen=None, published=None, location="Tokyo", snippet=""):
    now = datetime.now(timezone.utc)
    return {
        "id": jid,
        "title": title,
        "company": company,
        "tier": tier,
        "location": location,
        "snippet": snippet,
        "freshness_confidence": 90,
        "score": 90,
        "automation_confidence": 95,
        "last_seen": (last_seen or now).isoformat(),
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
        rows = [row("a", snippet="業務はフルリモート不可です")]
        kept, dropped = mod.drop_remote_contradictions(rows)
        self.assertEqual(kept, [])
        self.assertEqual(dropped, 1)

    def test_normal_full_remote_text_is_kept(self):
        rows = [row("a", snippet="フルリモートでデータ入力を行います")]
        kept, dropped = mod.drop_remote_contradictions(rows)
        self.assertEqual(len(kept), 1)
        self.assertEqual(dropped, 0)

    def test_contradictory_previous_row_is_not_carried(self):
        now = datetime.now(timezone.utc)
        old = row("a", last_seen=now - timedelta(hours=2), snippet="完全在宅ではありません")
        carried = mod.carryover_rows([], [old], now)
        self.assertEqual(carried, [])

    def test_recent_missing_job_is_carried_as_review(self):
        now = datetime.now(timezone.utc)
        carried = mod.carryover_rows([], [row("a", last_seen=now - timedelta(hours=8))], now)
        self.assertEqual(len(carried), 1)
        self.assertEqual(carried[0]["tier"], "review")
        self.assertTrue(carried[0]["carryover"])
        self.assertLessEqual(carried[0]["freshness_confidence"], 58)

    def test_missing_job_older_than_48h_is_dropped(self):
        now = datetime.now(timezone.utc)
        carried = mod.carryover_rows([], [row("a", last_seen=now - timedelta(hours=49))], now)
        self.assertEqual(carried, [])

    def test_published_over_30_days_is_not_carried(self):
        now = datetime.now(timezone.utc)
        carried = mod.carryover_rows([], [row("a", last_seen=now - timedelta(hours=2), published=now - timedelta(days=31))], now)
        self.assertEqual(carried, [])


if __name__ == "__main__":
    unittest.main()
