import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ActionRefillContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = (ROOT / "app.js").read_text(encoding="utf-8")
        cls.integrity = (ROOT / "integrity.js").read_text(encoding="utf-8")
        cls.refill = (ROOT / "refill.js").read_text(encoding="utf-8")
        cls.continuity = (ROOT / "continuity.js").read_text(encoding="utf-8")
        cls.pages = (ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8")

    def test_existing_queue_replaces_actioned_row_immediately(self):
        self.assertIn("if(isDeclined||isApplied)return false;", self.app)
        self.assertIn("rows.slice(0,state.displayLimit)", self.app)
        self.assertIn("document.querySelectorAll('.decline')", self.app)
        self.assertIn("document.querySelectorAll('.applied')", self.app)

    def test_low_stock_refill_runs_after_apply_or_decline(self):
        # 60 = the visible 30 plus another complete 30-row reserve batch.
        self.assertIn("const ACTION_REFILL_TRIGGER=60", self.refill)
        self.assertIn(".applied,.decline", self.refill)
        self.assertIn("setTimeout(()=>{void reloadLatestIfLow();},0)", self.refill)
        self.assertIn("available>=ACTION_REFILL_TRIGGER", self.refill)
        self.assertIn("window.loadFeed", self.refill)

    def test_refill_is_throttled_and_never_calls_authenticated_or_search_endpoints(self):
        self.assertIn("const REFILL_COOLDOWN_MS=30_000", self.refill)
        self.assertIn("if(inFlight||", self.refill)
        self.assertNotIn("serpapi.com", self.refill.lower())
        self.assertNotIn("api.github.com", self.refill.lower())
        self.assertNotIn("authorization:", self.refill.lower())
        self.assertNotIn("github_token", self.refill.lower())

    def test_foreground_recheck_keeps_static_feed_fresh(self):
        self.assertIn("visibilitychange", self.refill)
        self.assertIn("const FOREGROUND_RECHECK_MS=5*60_000", self.refill)
        self.assertIn("window.setInterval", self.refill)

    def test_pages_bundles_integrity_refill_and_continuity_after_core_app(self):
        self.assertIn("cp index.html app.js sw.js manifest.webmanifest icon.svg _site/", self.pages)
        self.assertIn("cat integrity.js refill.js continuity.js >> _site/app.js", self.pages)

    def test_browser_layers_have_no_authenticated_or_search_api_calls(self):
        for source in (self.integrity, self.refill, self.continuity):
            lower = source.lower()
            self.assertNotIn("serpapi.com", lower)
            self.assertNotIn("api.github.com", lower)
            self.assertNotIn("authorization:", lower)
            self.assertNotIn("github_token", lower)


if __name__ == "__main__":
    unittest.main()
