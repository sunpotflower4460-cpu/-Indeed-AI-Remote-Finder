import importlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

mod = importlib.import_module("apply_llm_quality_gate")


def row(review=None, *, snippet="", title="完全在宅 データ評価"):
    item = {
        "id": "a",
        "title": title,
        "location": "日本",
        "snippet": snippet,
        "tier": "review",
        "carryover": False,
        "remote_search_only": False,
    }
    if review is not None:
        item["llm_review"] = review
    return item


def review(**overrides):
    base = {
        "verdict": "strong",
        "automatable_fraction": 95,
        "confidence": 90,
        "human_dependency": "low",
        "physical_presence_required": False,
        "synchronous_human_interaction": "none",
        "blockers": [],
    }
    base.update(overrides)
    return base


class LlmQualityGateTests(unittest.TestCase):
    def test_missing_llm_review_never_causes_removal(self):
        self.assertIsNone(mod.reject_reason(row()))

    def test_clear_human_or_sync_mismatch_is_rejected(self):
        self.assertEqual(mod.reject_reason(row(review(verdict="reject"))), "verdict-reject")
        self.assertEqual(mod.reject_reason(row(review(human_dependency="high"))), "high-human-dependency")
        self.assertEqual(mod.reject_reason(row(review(synchronous_human_interaction="frequent"))), "frequent-sync")
        self.assertEqual(mod.reject_reason(row(review(physical_presence_required=True))), "physical-presence")

    def test_high_confidence_medium_human_dependency_is_rejected(self):
        self.assertEqual(
            mod.reject_reason(row(review(verdict="uncertain", human_dependency="medium", confidence=88))),
            "confirmed-medium-human-dependency",
        )

    def test_low_confidence_uncertainty_is_not_over_vetoed(self):
        self.assertIsNone(
            mod.reject_reason(
                row(
                    review(
                        verdict="uncertain",
                        human_dependency="medium",
                        confidence=65,
                        automatable_fraction=80,
                    )
                )
            )
        )

    def test_continuous_online_presence_is_rejected_without_llm(self):
        for text in (
            "完全在宅。勤務時間中は常にオンラインで待機してください。",
            "完全在宅ですが常時ログインが必要です。",
            "在宅でオンライン待機を行う業務です。",
            "Work from home; online throughout the shift.",
        ):
            self.assertEqual(
                mod.reject_reason(row(snippet=text)),
                "continuous-human-presence",
                text,
            )

    def test_short_human_response_sla_is_rejected(self):
        for text in (
            "完全在宅。依頼受信後10分以内に返信してください。",
            "Fully remote. Respond within 15 minutes when a task arrives.",
        ):
            self.assertEqual(
                mod.reject_reason(row(snippet=text)),
                "continuous-human-presence",
                text,
            )

    def test_fixed_schedule_alone_is_not_rejected(self):
        self.assertIsNone(
            mod.reject_reason(
                row(snippet="完全在宅。勤務時間は9:00〜18:00。データをまとめて処理します。")
            )
        )

    def test_negated_presence_requirement_is_not_false_rejected(self):
        for text in (
            "完全在宅。常時ログイン不要。納期までにデータを提出すればOKです。",
            "完全在宅。オンライン待機なし。好きな時間に作業できます。",
            "Fully remote; no need to stay online. Work asynchronously.",
        ):
            self.assertIsNone(mod.reject_reason(row(snippet=text)), text)

    def test_llm_presence_blocker_is_rejected_even_with_high_automation(self):
        self.assertEqual(
            mod.reject_reason(
                row(
                    review(
                        automatable_fraction=95,
                        confidence=82,
                        blockers=["リアルタイム待機が業務要件として明記されている"],
                    )
                )
            ),
            "confirmed-continuous-presence",
        )

    def test_reviewed_job_below_seventy_five_percent_is_too_weak(self):
        self.assertEqual(
            mod.reject_reason(row(review(automatable_fraction=74, confidence=90))),
            "confirmed-low-automation",
        )
        self.assertIsNone(
            mod.reject_reason(row(review(automatable_fraction=75, confidence=90)))
        )

    def test_apply_updates_pool_and_presence_metadata(self):
        bad = row(review(verdict="reject"))
        presence = {**row(snippet="常時ログイン必須"), "id": "presence"}
        good = {
            "id": "b",
            "title": "完全在宅 データ入力",
            "snippet": "納期までに非同期でデータ入力",
            "tier": "review",
            "carryover": True,
            "remote_search_only": False,
        }
        payload = {"candidate_display_target": 100, "jobs": [bad, presence, good]}
        got = mod.apply(payload)
        self.assertEqual([x["id"] for x in got["jobs"]], ["b"])
        self.assertEqual(got["candidate_pool_size"], 1)
        self.assertEqual(got["quality_gate_dropped"], 2)
        self.assertEqual(got["llm_quality_dropped"], 1)
        self.assertEqual(got["presence_quality_dropped"], 1)
        self.assertEqual(got["candidate_presence_gate_version"], 1)
        self.assertTrue(got["candidate_requires_no_continuous_human_presence"])
        self.assertEqual(got["jobs"][0]["continuous_presence_risk"], "low")
        self.assertEqual(got["jobs"][0]["presence_gate_version"], 1)
        self.assertEqual(got["carryover_jobs"], 1)
        self.assertTrue(got["pool_under_display_target"])


if __name__ == "__main__":
    unittest.main()
