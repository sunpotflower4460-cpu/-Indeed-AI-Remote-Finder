import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

path = SCRIPTS / "acquisition.py"
spec = importlib.util.spec_from_file_location("acquisition_budget_pacing_test", path)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class AcquisitionBudgetPacingTests(unittest.TestCase):
    def test_days_remaining_are_inclusive_and_cross_year_safely(self):
        self.assertEqual(
            mod.month_days_remaining(datetime(2026, 8, 20, 4, tzinfo=timezone.utc)),
            12,
        )
        self.assertEqual(
            mod.month_days_remaining(datetime(2026, 8, 31, 23, tzinfo=timezone.utc)),
            1,
        )
        self.assertEqual(
            mod.month_days_remaining(datetime(2026, 12, 31, 23, tzinfo=timezone.utc)),
            1,
        )

    def test_current_august_usage_is_paced_to_four_requests(self):
        now = datetime(2026, 8, 20, 4, tzinfo=timezone.utc)
        self.assertEqual(mod.paced_monthly_request_limit(165, 220, now), 4)

    def test_pacing_does_not_reduce_healthy_early_month_daily_budget(self):
        now = datetime(2026, 8, 1, 4, tzinfo=timezone.utc)
        # 220 / 31 = 7, so the normal seven-request production cap still fits.
        self.assertEqual(mod.paced_monthly_request_limit(0, 220, now), 7)

    def test_last_day_can_use_remaining_quota(self):
        now = datetime(2026, 8, 31, 4, tzinfo=timezone.utc)
        self.assertEqual(mod.paced_monthly_request_limit(217, 220, now), 3)

    def test_small_remaining_quota_degrades_to_one_instead_of_burning_all_at_once(self):
        now = datetime(2026, 8, 20, 4, tzinfo=timezone.utc)
        self.assertEqual(mod.paced_monthly_request_limit(215, 220, now), 1)

    def test_exhausted_budget_returns_zero(self):
        now = datetime(2026, 8, 20, 4, tzinfo=timezone.utc)
        self.assertEqual(mod.paced_monthly_request_limit(220, 220, now), 0)
        self.assertEqual(mod.paced_monthly_request_limit(230, 220, now), 0)


if __name__ == "__main__":
    unittest.main()
