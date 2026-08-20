import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class QueueContractTests(unittest.TestCase):
    """Regression contract for the 150 -> 100 -> 30 candidate queue."""

    @classmethod
    def setUpClass(cls):
        cls.app = (ROOT / "app.js").read_text(encoding="utf-8")
        cls.postprocess = (ROOT / "scripts" / "postprocess_feed.py").read_text(encoding="utf-8")
        cls.acquisition_remote = (ROOT / "scripts" / "acquisition_remote.py").read_text(encoding="utf-8")

    def test_server_pool_is_hard_capped_at_150(self):
        self.assertIn("POOL_LIMIT = 150", self.postprocess)
        self.assertIn('visible = combined[:POOL_LIMIT]', self.postprocess)
        self.assertIn('current_payload["candidate_pool_size"] = len(visible)', self.postprocess)
        self.assertIn('current_payload["candidate_postprocess_pool_limit"] = POOL_LIMIT', self.postprocess)

    def test_acquisition_targets_100_user_rows_with_150_server_rows(self):
        self.assertIn("USER_DISPLAY_TARGET = 100", self.acquisition_remote)
        self.assertIn("SERVER_POOL_TARGET = 150", self.acquisition_remote)
        self.assertIn("acquisition.DISPLAY_TARGET = USER_DISPLAY_TARGET", self.acquisition_remote)
        self.assertIn("acquisition.POOL_TARGET = SERVER_POOL_TARGET", self.acquisition_remote)
        self.assertIn("acquisition.POOL_LIMIT = SERVER_POOL_TARGET", self.acquisition_remote)

    def test_client_keeps_at_most_150_eligible_rows(self):
        self.assertIn("const LOCAL_POOL_LIMIT=150", self.app)
        self.assertIn("rows.slice(0,LOCAL_POOL_LIMIT)", self.app)
        self.assertIn("const USER_STOCK_TARGET=100", self.app)

    def test_recommendation_window_starts_at_30_and_loads_in_30_row_batches(self):
        self.assertIn("const DEFAULT_VISIBLE=30", self.app)
        self.assertIn("displayLimit:DEFAULT_VISIBLE", self.app)
        self.assertIn("rows.slice(0,state.displayLimit)", self.app)
        self.assertIn("state.displayLimit+=DEFAULT_VISIBLE", self.app)

    def test_applied_and_declined_are_removed_before_the_30_row_slice(self):
        filter_marker = "if(isDeclined||isApplied)return false;"
        render_rows_marker = "const rows=currentRows();"
        slice_marker = "rows.slice(0,state.displayLimit)"
        self.assertIn(filter_marker, self.app)
        self.assertIn(render_rows_marker, self.app)
        self.assertIn(slice_marker, self.app)
        self.assertLess(self.app.index(filter_marker), self.app.index(render_rows_marker))
        self.assertLess(self.app.index(render_rows_marker), self.app.index(slice_marker))

    def test_apply_and_decline_re_render_without_resetting_window(self):
        # A render after mutating applied/declined means a 30-row window is filled
        # again from the already-filtered queue, so row 31 automatically moves in.
        decline = re.search(
            r"document\.querySelectorAll\('\.decline'\).*?\.onclick=.*?render\(\);\}\);",
            self.app,
            re.S,
        )
        applied = re.search(
            r"document\.querySelectorAll\('\.applied'\).*?\.onclick=.*?render\(\);\}\);",
            self.app,
            re.S,
        )
        self.assertIsNotNone(decline)
        self.assertIsNotNone(applied)
        self.assertNotIn("resetWindow()", decline.group(0))
        self.assertNotIn("resetWindow()", applied.group(0))

    def test_user_actions_are_persisted_separately_from_candidate_stock(self):
        for key in ("declinedJobs", "appliedJobs", "appliedAt", "savedJobs"):
            self.assertIn(key, self.app)
        # User actions must not delete the underlying server/local candidate stock;
        # they filter it from recommendations and allow the next queued row through.
        self.assertNotIn("splice(", self.app)


if __name__ == "__main__":
    unittest.main()
