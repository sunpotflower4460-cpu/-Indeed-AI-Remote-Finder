import importlib.util
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

path = SCRIPTS / "postprocess_feed.py"
spec = importlib.util.spec_from_file_location("postprocess", path)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def row(jid, *, tier="high", last_seen=None, published=None, snippet="", company="Example", title="AI Annotator", score=90):
    now = datetime.now(timezone.utc)
    return {
        "id": jid,
        "title": title,
        "company": company,
        "tier": tier,
        "location": "Tokyo",
        "snippet": snippet,
        "remote_reasons": ["完全在宅"],
        "freshness_confidence": 90,
        "score": score,
        "automation_confidence": 95,
        "human_dependency_risk": 0,
        "automation_reasons": ["アノテーション", "分類"],
        "autonomy_attention_risk": "low",
        "autonomy_policy_version": 2,
        "quality_policy_version": 2,
        "quality_gate": "async-ai-remote-v2",
        "full_listing_presence_screened": True,
        "presence_gate_version": 1,
        "continuous_presence_risk": "low",
        "remote_search_only": False,
        "last_seen": (last_seen or now).isoformat(),
        "first_seen": now.isoformat(),
        "search_published_at": (published or (now - timedelta(days=2))).isoformat(),
    }


class PostprocessTests(unittest.TestCase):
    def test_duplicate_company_title_collapses(self):
        got, removed = mod.dedupe_rows([row("a"), row("b")])
        self.assertEqual(len(got), 1)
        self.assertEqual(removed, 1)

    def test_remote_contradictions_are_dropped(self):
        for text in (
            "フルリモート不可です",
            "ほぼフルリモートですが月1回出社です",
            "完全在宅相談可です",
        ):
            kept, dropped = mod.drop_remote_contradictions([row("a", snippet=text)])
            self.assertEqual(kept, [], text)
            self.assertEqual(dropped, 1, text)

    def test_negated_hybrid_is_not_false_rejected(self):
        item = row("a", snippet="完全在宅で、ハイブリッド勤務は不可です")
        item["remote_reasons"] = ["完全在宅", "注意:ハイブリッド"]
        kept, dropped = mod.drop_remote_contradictions([item])
        self.assertEqual(len(kept), 1)
        self.assertEqual(dropped, 0)

    def test_current_quality_job_can_be_carried_for_ten_days(self):
        now = datetime.now(timezone.utc)
        item = row("a", last_seen=now - timedelta(days=10))
        item["search_published_at"] = None
        carried = mod.carryover_rows([], [item], now)
        self.assertEqual(len(carried), 1)
        self.assertEqual(carried[0]["tier"], "review")
        self.assertTrue(carried[0]["carryover"])
        self.assertEqual(carried[0]["verification_status"], "reserve-not-rediscovered")
        self.assertEqual(carried[0]["verification_age_days"], 10)

    def test_v1_job_never_reenters_reserve(self):
        now = datetime.now(timezone.utc)
        item = row("a", last_seen=now - timedelta(days=2))
        item["quality_policy_version"] = 1
        item["quality_gate"] = "async-ai-remote"
        self.assertEqual(mod.carryover_rows([], [item], now), [])

    def test_pre_full_listing_presence_job_never_reenters_reserve(self):
        now = datetime.now(timezone.utc)
        for field, value in (
            ("full_listing_presence_screened", False),
            ("presence_gate_version", 0),
            ("continuous_presence_risk", None),
        ):
            item = row(f"old-{field}", last_seen=now - timedelta(days=2))
            item[field] = value
            self.assertEqual(mod.carryover_rows([], [item], now), [], field)

    def test_explicit_ai_use_ban_never_reenters_reserve(self):
        now = datetime.now(timezone.utc)
        item = row(
            "ai-ban",
            last_seen=now - timedelta(days=2),
            snippet="完全在宅です。生成AIの使用は禁止です。",
        )
        self.assertEqual(mod.carryover_rows([], [item], now), [])

    def test_weak_or_single_signal_review_never_reenters(self):
        now = datetime.now(timezone.utc)
        weak = row("weak", tier="review", last_seen=now - timedelta(days=2))
        weak["automation_confidence"] = 63
        single = row("single", tier="review", last_seen=now - timedelta(days=2))
        single["automation_reasons"] = ["データ入力"]
        self.assertEqual(mod.carryover_rows([], [weak], now), [])
        self.assertEqual(mod.carryover_rows([], [single], now), [])

    def test_remote_search_only_never_reenters(self):
        now = datetime.now(timezone.utc)
        item = row("a", tier="review", last_seen=now - timedelta(days=2))
        item["remote_search_only"] = True
        self.assertEqual(mod.carryover_rows([], [item], now), [])

    def test_older_than_fourteen_days_never_reenters(self):
        now = datetime.now(timezone.utc)
        self.assertEqual(mod.carryover_rows([], [row("a", last_seen=now - timedelta(days=15))], now), [])
        self.assertEqual(mod.carryover_rows([], [row("b", published=now - timedelta(days=31))], now), [])

    def test_live_rows_get_current_verification_stamp_and_rank_before_reserve(self):
        now = datetime.now(timezone.utc)
        live = row("live", tier="review", company="Live", score=70)
        reserve = row("reserve", tier="review", company="Reserve", score=95, last_seen=now - timedelta(days=2))
        got = mod.process({"generated_at": now.isoformat(), "jobs": [live]}, {"jobs": [reserve]})
        self.assertEqual([x["id"] for x in got["jobs"]], ["live", "reserve"])
        self.assertEqual(got["candidate_reserve_max_days"], 14)
        self.assertEqual(got["candidate_verification_status_version"], 1)
        self.assertTrue(got["candidate_requires_recent_rediscovery"])
        self.assertEqual(got["jobs"][0]["verification_status"], "live-search-hit")
        self.assertEqual(got["jobs"][0]["verification_age_days"], 0)

    def test_pool_caps_at_150(self):
        now = datetime.now(timezone.utc)
        rows = [row(str(i), company=f"Company {i}", title=f"Role {i}") for i in range(180)]
        capped = mod.process({"generated_at": now.isoformat(), "candidate_display_target": 100, "jobs": rows}, None)
        self.assertEqual(mod.POOL_LIMIT, 150)
        self.assertEqual(len(capped["jobs"]), 150)
        self.assertEqual(capped["candidate_pool_size"], 150)
        self.assertEqual(capped["candidate_postprocess_pool_limit"], 150)
        self.assertFalse(capped["pool_under_display_target"])


if __name__ == "__main__":
    unittest.main()
