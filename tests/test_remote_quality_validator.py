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
        "snippet": "完全在宅でデータ入力と転記を非同期で行います。",
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
        "continuous_presence_risk": "low",
        "presence_gate_version": 1,
    }
    base.update(overrides)
    return base


def payload(job_row, *, presence_active=True):
    data = {
        "candidate_quality_policy_version": 2,
        "candidate_quality_gate": "async-ai-remote-v2",
        "candidate_review_automation_min": 64,
        "candidate_review_human_risk_max": 18,
        "candidate_review_automation_signal_min": 2,
        "candidate_requires_explicit_full_remote": True,
        "candidate_provider_wfh_filter_used": False,
        "jobs": [job_row],
    }
    if presence_active:
        data["candidate_presence_gate_version"] = 1
        data["candidate_requires_no_continuous_human_presence"] = True
    return data


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

    def test_continuous_presence_text_cannot_survive_active_gate(self):
        errors = mod.validate(
            payload(row(snippet="完全在宅ですが勤務時間中は常にオンラインで待機します。"))
        )
        self.assertTrue(any("continuous human presence" in error for error in errors))

    def test_presence_stamp_is_required_when_gate_is_active(self):
        errors = mod.validate(payload(row(continuous_presence_risk=None)))
        self.assertTrue(any("continuous presence risk" in error for error in errors))
        errors = mod.validate(payload(row(presence_gate_version=0)))
        self.assertTrue(any("presence-gate stamp" in error for error in errors))

    def test_presence_gate_metadata_must_be_consistent(self):
        data = payload(row())
        data["candidate_presence_gate_version"] = 2
        errors = mod.validate(data)
        self.assertTrue(any("presence-gate version" in error for error in errors))

    def test_pre_presence_feed_remains_backward_compatible_during_rollout(self):
        old = row()
        old.pop("continuous_presence_risk")
        old.pop("presence_gate_version")
        self.assertEqual(mod.validate(payload(old, presence_active=False)), [])

    def test_v1_feed_remains_backward_compatible_during_rollout(self):
        legacy = row()
        for key in (
            "quality_gate",
            "quality_policy_version",
            "autonomy_attention_risk",
            "continuous_presence_risk",
            "presence_gate_version",
        ):
            legacy.pop(key, None)
        self.assertEqual(mod.validate({"candidate_quality_policy_version": 1, "jobs": [legacy]}), [])


if __name__ == "__main__":
    unittest.main()
