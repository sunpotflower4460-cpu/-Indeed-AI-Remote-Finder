import importlib.util
import sys
import unittest
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "scripts" / "validate_remote_feed.py"
spec = importlib.util.spec_from_file_location("remote_validator_quality_test", path)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def row(**overrides):
    base = {
        "id": "a",
        "title": "完全在宅 データ入力",
        "location": "日本",
        "snippet": "完全在宅でデータ入力と転記を行います。",
        "tier": "review",
        "remote_reasons": ["完全在宅"],
        "remote_search_only": False,
        "tags": ["完全リモート", "データ", "張り付きリスク低"],
        "automation_confidence": 80,
        "human_dependency_risk": 0,
        "autonomy_attention_risk": "low",
        "quality_gate": "async-ai-remote",
    }
    base.update(overrides)
    return base


def payload(job_row):
    return {"candidate_quality_policy_version": 1, "jobs": [job_row]}


class RemoteQualityValidatorTests(unittest.TestCase):
    def test_valid_quality_row_passes(self):
        self.assertEqual(mod.validate(payload(row())), [])

    def test_partial_remote_wording_fails(self):
        errors = mod.validate(
            payload(row(snippet="完全在宅ではなく、慣れたら在宅勤務週1～2日です。"))
        )
        self.assertTrue(any("partial/hybrid" in error for error in errors))

    def test_remote_search_only_fails_when_quality_policy_active(self):
        errors = mod.validate(payload(row(remote_search_only=True, tags=["在宅要確認"])))
        self.assertTrue(any("remote-search-only" in error for error in errors))

    def test_low_automation_review_fails(self):
        errors = mod.validate(payload(row(automation_confidence=54)))
        self.assertTrue(any("review automation" in error for error in errors))

    def test_high_human_dependency_review_fails(self):
        errors = mod.validate(payload(row(human_dependency_risk=26)))
        self.assertTrue(any("review human risk" in error for error in errors))

    def test_legacy_feed_without_quality_metadata_remains_backward_compatible(self):
        legacy = row()
        legacy.pop("quality_gate")
        legacy.pop("autonomy_attention_risk")
        self.assertEqual(mod.validate({"jobs": [legacy]}), [])


if __name__ == "__main__":
    unittest.main()
