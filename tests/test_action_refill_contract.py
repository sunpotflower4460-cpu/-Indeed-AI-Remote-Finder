import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ActionRefillContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = (ROOT / "app.js").read_text(encoding="utf-8")
        cls.refill = (ROOT / "refill.js").read_text(encoding="utf-8")
        cls.pages = (ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8")

    def test_existing_queue_replaces_actioned_row_immediately(self):
        self.assertIn("if(isDeclined||isApplied)return false;", self.app)
        self.assertIn("rows.slice(0,state.displayLimit)", self.app)
        self.assertIn("document.querySelectorAll('.decline')", self.app)
        self.assertIn("document.querySelectorAll('.applied')", self.app)

    def test_low_stock_refill_runs_after_apply_or_decline(self):
        self.assertIn("const ACTION_REFILL_TRIGGER=45", self.refill)
        self.assertIn(".applied,.decline", self.refill)
        self.assertIn("setTimeout(()=>{void reloadLatestIfLow();},0)", self.refill)
        self.assertIn("available>=ACTION_REFILL_TRIGGER", self.refill)
        self.assertIn("window.loadFeed", self.refill)

    def test_refill_is_throttled_and_never_calls_search_api(self):
        self.assertIn("const REFILL_COOLDOWN_MS=30_000", self.refill)
        self.assertIn("if(inFlight||", self.refill)
        self.assertNotIn("serpapi", self.refill.lower())
        self.assertNotIn("api.github.com", self.refill.lower())
        self.assertNotIn("authorization", self.refill.lower())

    def test_foreground_recheck_keeps_static_feed_fresh(self):
        self.assertIn("visibilitychange", self.refill)
        self.assertIn("const FOREGROUND_RECHECK_MS=5*60_000", self.refill)
        self.assertIn("window.setInterval", self.refill)

    def test_pages_bundles_refill_after_core_app(self):
        self.assertIn("cp index.html app.js sw.js manifest.webmanifest icon.svg _site/", self.pages)
        self.assertIn("cat refill.js >> _site/app.js", self.pages)


if __name__ == "__main__":
    unittest.main()
