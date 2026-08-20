import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

path = SCRIPTS / "apply_llm_quality_gate.py"
spec = importlib.util.spec_from_file_location("final_new_jobs_metadata_test", path)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def row(job_id: str, *, seen_count: int = 1, carryover: bool = False, reject: bool = False):
    value = {
        "id": job_id,
        "title": "完全在宅 データ入力",
        "location": "日本",
        "snippet": "完全在宅でデータ入力と分類を行います。",
        "seen_count": seen_count,
        "first_seen": "2026-08-20T05:00:00+00:00",
        "last_seen": "2026-08-20T05:00:00+00:00" if seen_count == 1 else "2026-08-20T06:00:00+00:00",
        "carryover": carryover,
    }
    if reject:
        value["llm_review"] = {
            "verdict": "strong",
            "automatable_fraction": 90,
            "confidence": 95,
            "human_dependency": "low",
            "physical_presence_required": False,
            "synchronous_human_interaction": "occasional",
            "blockers": [],
        }
    return value


class FinalNewJobsMetadataTests(unittest.TestCase):
    def test_new_row_removed_by_llm_veto_no_longer_counts_as_new(self):
        payload = {
            "candidate_display_target": 100,
            "new_jobs": 1,
            "live_jobs": 1,
            "carryover_jobs": 1,
            "candidate_pool_size": 2,
            "jobs": [
                row("new", reject=True),
                row("reserve", carryover=True),
            ],
        }

        result = mod.apply(payload)

        self.assertEqual([item["id"] for item in result["jobs"]], ["reserve"])
        self.assertEqual(result["new_jobs"], 0)
        self.assertEqual(result["live_jobs"], 0)
        self.assertEqual(result["carryover_jobs"], 1)
        self.assertEqual(result["candidate_pool_size"], 1)
        self.assertEqual(result["llm_quality_dropped"], 1)

    def test_surviving_first_seen_live_row_counts_as_new(self):
        result = mod.apply({"candidate_display_target": 100, "jobs": [row("new")]})
        self.assertEqual(result["new_jobs"], 1)
        self.assertEqual(result["live_jobs"], 1)

    def test_rediscovered_live_row_is_not_counted_as_new(self):
        result = mod.apply(
            {"candidate_display_target": 100, "jobs": [row("existing", seen_count=2)]}
        )
        self.assertEqual(result["new_jobs"], 0)
        self.assertEqual(result["live_jobs"], 1)

    def test_carryover_seen_once_is_not_counted_as_new(self):
        result = mod.apply(
            {"candidate_display_target": 100, "jobs": [row("reserve", carryover=True)]}
        )
        self.assertEqual(result["new_jobs"], 0)
        self.assertEqual(result["carryover_jobs"], 1)


if __name__ == "__main__":
    unittest.main()
