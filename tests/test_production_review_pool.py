import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

path = SCRIPTS / "acquisition_remote.py"
spec = importlib.util.spec_from_file_location("acquisition_remote_test", path)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def scores(*, automation=22, remote=68, risk=0, reasons=None, remote_reasons=None):
    return mod.acquisition.legacy.Scores(
        remote=remote,
        automation=automation,
        freshness=90,
        risk=risk,
        overall=60,
        tier="hidden",
        remote_reasons=list(remote_reasons or ["Google Jobs:在宅勤務フィルタ"]),
        automation_reasons=list(reasons or ["事務"]),
        risk_reasons=[],
    )


class ProductionReviewPoolTests(unittest.TestCase):
    def test_one_real_automation_signal_can_enter_next_best_review(self):
        self.assertTrue(mod.production_review_fallback(scores(), datetime.now(timezone.utc)))

    def test_no_automation_signal_is_not_kept_for_count_padding(self):
        row = scores()
        row.automation_reasons = []
        self.assertFalse(mod.production_review_fallback(row, datetime.now(timezone.utc)))

    def test_high_human_or_physical_risk_is_not_kept(self):
        self.assertFalse(mod.production_review_fallback(scores(automation=90, risk=70), datetime.now(timezone.utc)))

    def test_remote_contradiction_is_not_kept(self):
        self.assertFalse(
            mod.production_review_fallback(
                scores(remote=30, remote_reasons=["Google Jobs:在宅勤務フィルタ", "注意:週2出社"]),
                datetime.now(timezone.utc),
            )
        )


if __name__ == "__main__":
    unittest.main()
