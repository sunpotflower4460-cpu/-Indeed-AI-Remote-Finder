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
        "automation_reasons": ["データ入力", "転記"],
        "human_dependency_risk": 0,
        "autonomy_attention_risk": "low",
        "quality_policy_version": 2,
        "quality_gate": "async-ai-remote-v2",
    }
    base.update(overrides)
    return base


def payload(job_row):
    return {
        "candidate_quality_policy_version": 2,
        "candidate_quality_gate": "async-ai-remote-v2",
        "candidate_review_automation_min": 64,
        "candidate_review_human_risk_max": 18,
        "candidate_review_automation_signal_min": 2,
        "candidate_requires_explicit_full_remote": True,
        "candidate_provider_wfh_filter_used": False,
        "jobs": [job_row],
    }


class RemoteQualityValidatorTests(unittest.TestCase):
    def test_valid_quality_row_passes(self):
        self.assertEqual(mod.validate(payload(row())), [])

    def test_partial_or_conditional_remote_wording_fails(self):
        for text in (
            "完全在宅ではなく、慣れたら在宅勤務週1～2日です。",
            "ほぼフルリモートですが月1回出社です。",
            "フルリモート相談可です。",
        ):
            errors = mod.validate(payload(row(snippet=text)))
            self.assertTrue(any("partial/hybrid" in error for error in errors), text)

    def test_remote_search_only_fails_when_quality_policy_active(self):
        errors = mod.validate(payload(row(remote_search_only=True)))
        self.assertTrue(any("remote-search-only" in error for error in errors))

    def test_low_automation_or_high_human_risk_fails(self):
        errors = mod.validate(payload(row(automation_confidence=63)))
        self.assertTrue(any("review automation" in error for error in errors))
        errors = mod.validate(payload(row(human_dependency_risk=19)))
        self.assertTrue(any("review human risk" in error for error in errors))

    def test_single_automation_signal_fails(self):
        errors = mod.validate(payload(row(automation_reasons=["データ入力"])))
        self.assertTrue(any("automation signals" in error for error in errors))

    def test_llm_veto_cannot_survive_final_validator(self):
        bad_review = {
            "verdict": "reject",
            "automatable_fraction": 40,
            "confidence": 90,
            "human_dependency": "high",
            "physical_presence_required": False,
            "synchronous_human_interaction": "frequent",
            "blockers": [],
        }
        errors = mod.validate(payload(row(llm_review=bad_review)))
        self.assertTrue(any("LLM quality veto" in error for error in errors))

    def test_v1_feed_remains_backward_compatible_during_rollout(self):
        legacy = row()
        legacy.pop("quality_gate")
        legacy.pop("quality_policy_version")
        legacy.pop("autonomy_attention_risk")
        self.assertEqual(mod.validate({"candidate_quality_policy_version": 1, "jobs": [legacy]}), [])


if __name__ == "__main__":
    unittest.main()
