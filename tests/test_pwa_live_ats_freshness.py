import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PWALiveATSFreshnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = (ROOT / "app.js").read_text(encoding="utf-8")

    def test_recent_live_ats_verification_overrides_old_publish_age_only_for_ats(self):
        self.assertIn("const ATS_LIVE_MAX_DAYS=3", self.app)
        self.assertIn("function isLiveATSVerified(j)", self.app)
        self.assertIn("source==='public-employer-ats'", self.app)
        self.assertIn("source==='targeted-public-employer-ats'", self.app)
        self.assertIn("liveAge<=ATS_LIVE_MAX_DAYS", self.app)
        self.assertIn("if(!liveATS&&age!==null&&age>30)return'expired'", self.app)
        self.assertIn("isLiveATSVerified(j)||published===null||published<=30", self.app)

    def test_ui_still_has_thirty_row_window_and_reports_readiness(self):
        self.assertIn("const DEFAULT_VISIBLE=30", self.app)
        self.assertIn("rows.slice(0,state.displayLimit)", self.app)
        self.assertIn("available>=DEFAULT_VISIBLE?'・30件表示可能':'・30件表示ライン未達'", self.app)

    def test_existing_quality_safe_cache_contract_is_preserved(self):
        self.assertIn("const LOCAL_CACHE_KEY='candidateCacheV5'", self.app)


if __name__ == "__main__":
    unittest.main()
