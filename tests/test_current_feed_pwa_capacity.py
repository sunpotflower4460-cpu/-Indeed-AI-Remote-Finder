import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FEED = ROOT / "data" / "jobs.json"


def parse_iso(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def age_days(value, now):
    dt = parse_iso(value)
    if not dt:
        return None
    return max(0.0, (now - dt).total_seconds() / 86400)


def live_ats(row, now):
    source = str(row.get("discovery_source") or "")
    is_ats = (
        source in {"public-employer-ats", "targeted-public-employer-ats"}
        or int(row.get("public_ats_supplement_version") or 0) > 0
        or int(row.get("targeted_public_ats_version") or 0) > 0
    )
    live_age = age_days(row.get("ats_live_verified_at"), now)
    return bool(is_ats and live_age is not None and live_age <= 3)


def pwa_eligible(row, now):
    if not isinstance(row, dict):
        return False
    seen = age_days(row.get("last_seen"), now)
    published = age_days(row.get("search_published_at"), now)
    live = live_ats(row, now)
    if seen is not None and seen > 14:
        return False
    if published is not None and published > 30 and not live:
        return False
    if int(row.get("quality_policy_version") or 0) != 2:
        return False
    if row.get("quality_gate") != "async-ai-remote-v2":
        return False
    if row.get("autonomy_attention_risk") != "low" or row.get("remote_search_only") is True:
        return False
    if row.get("full_listing_presence_screened") is not True:
        return False
    if int(row.get("presence_gate_version") or 0) != 1 or row.get("continuous_presence_risk") != "low":
        return False
    if int(row.get("ai_tool_policy_gate_version") or 0) != 1:
        return False
    if row.get("ai_tool_policy_status") not in {"explicitly-allowed", "not-stated"}:
        return False
    if row.get("tier") not in {"high", "review"}:
        return False
    if row.get("tier") == "review":
        if int(row.get("automation_confidence") or 0) < 64:
            return False
        if int(row.get("human_dependency_risk") or 0) > 18:
            return False
        reasons = {str(x or "").strip().lower() for x in row.get("automation_reasons") or [] if str(x or "").strip()}
        if len(reasons) < 2:
            return False
    return True


class CurrentFeedPWACapacityTests(unittest.TestCase):
    def test_server_30_plus_pool_is_not_hidden_below_30_by_pwa_freshness(self):
        payload = json.loads(FEED.read_text(encoding="utf-8"))
        server_pool = int(payload.get("candidate_pool_size") or len(payload.get("jobs") or []))
        if server_pool < 30:
            self.skipTest("external strict supply is currently below the 30-row product target")
        now = parse_iso(payload.get("generated_at")) or datetime.now(timezone.utc)
        visible_stock = sum(1 for row in payload.get("jobs") or [] if pwa_eligible(row, now))
        self.assertGreaterEqual(
            visible_stock,
            30,
            f"server pool={server_pool} but PWA-eligible stock={visible_stock}",
        )


if __name__ == "__main__":
    unittest.main()
