import importlib
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

mod = importlib.import_module("llm_review_quality")
base = importlib.import_module("llm_review")


def review_job(jid="r1"):
    return {
        "id": jid,
        "title": "完全在宅 データ入力",
        "company": "Example",
        "location": "日本",
        "snippet": "完全在宅でデータ入力と転記を行うデジタル業務",
        "tier": "review",
        "automation_confidence": 80,
        "remote_confidence": 100,
        "freshness_confidence": 90,
        "human_dependency_risk": 0,
        "automation_reasons": ["データ入力", "転記"],
        "risk_reasons": [],
        "tags": ["完全リモート", "データ"],
        "autonomy_attention_risk": "low",
        "quality_policy_version": 2,
        "quality_gate": "async-ai-remote-v2",
        "remote_search_only": False,
    }


def strong_review():
    return base.normalize_review({
        "verdict": "strong",
        "automatable_fraction": 96,
        "confidence": 92,
        "human_dependency": "low",
        "physical_presence_required": False,
        "synchronous_human_interaction": "none",
        "data_sensitivity_risk": "unknown",
        "automation_summary": "定型デジタル処理中心",
        "automation_plan": ["取得", "処理", "出力"],
        "blockers": [],
        "questions_to_confirm": ["AI利用可否"],
    })


class ReviewTierLlmTests(unittest.TestCase):
    def test_only_v2_review_candidates_are_eligible(self):
        self.assertTrue(mod.eligible(review_job()))
        high = review_job(); high["tier"] = "high"
        self.assertFalse(mod.eligible(high))
        old = review_job(); old["quality_policy_version"] = 1
        self.assertFalse(mod.eligible(old))

    def test_uses_only_unused_share_of_eight_attempt_run_cap(self):
        month = base.month_key(datetime.now(timezone.utc))
        previous = {"llm_budget_month": month, "llm_paid_attempts_month": 10, "jobs": []}
        payload = {
            "llm_budget_month": month,
            "llm_paid_attempts_month": 16,
            "llm_new_reviews": 6,
            "llm_review_failures": 0,
            "jobs": [review_job("a"), review_job("b"), review_job("c")],
        }
        with patch.object(base, "call_openai", return_value=strong_review()) as call:
            got = mod.enrich_review_tier(payload, previous, api_key="fake", model="test")
        self.assertEqual(call.call_count, 2)
        self.assertEqual(got["llm_review_tier_new_reviews"], 2)
        self.assertEqual(got["llm_paid_attempts_month"], 18)
        self.assertFalse(got["llm_review_tier_skipped_after_primary_failure"])

    def test_no_extra_call_when_primary_used_all_eight(self):
        month = base.month_key(datetime.now(timezone.utc))
        previous = {"llm_budget_month": month, "llm_paid_attempts_month": 20, "jobs": []}
        payload = {"llm_budget_month": month, "llm_paid_attempts_month": 28, "jobs": [review_job()]}
        with patch.object(base, "call_openai", side_effect=AssertionError("must not call")):
            got = mod.enrich_review_tier(payload, previous, api_key="fake", model="test")
        self.assertEqual(got["llm_review_tier_new_reviews"], 0)
        self.assertEqual(got["llm_paid_attempts_month"], 28)

    def test_primary_failure_stops_spare_calls(self):
        month = base.month_key(datetime.now(timezone.utc))
        previous = {"llm_budget_month": month, "llm_paid_attempts_month": 30, "jobs": []}
        payload = {
            "llm_budget_month": month,
            "llm_paid_attempts_month": 31,
            "llm_review_failures": 1,
            "llm_errors": ["x: provider error"],
            "jobs": [review_job()],
        }
        with patch.object(base, "call_openai", side_effect=AssertionError("must not call")):
            got = mod.enrich_review_tier(payload, previous, api_key="fake", model="test")
        self.assertEqual(got["llm_review_tier_attempts"], 0)
        self.assertTrue(got["llm_review_tier_skipped_after_primary_failure"])
        self.assertEqual(got["llm_paid_attempts_month"], 31)

    def test_uncertain_attempt_accounting_stops_spare_calls(self):
        month = base.month_key(datetime.now(timezone.utc))
        previous = {"llm_budget_month": month, "llm_paid_attempts_month": 40, "jobs": []}
        payload = {
            "llm_budget_month": month,
            "llm_paid_attempts_month": 48,
            "llm_attempts_uncertain": True,
            "jobs": [review_job()],
        }
        with patch.object(base, "call_openai", side_effect=AssertionError("must not call")):
            got = mod.enrich_review_tier(payload, previous, api_key="fake", model="test")
        self.assertEqual(got["llm_review_tier_attempts"], 0)
        self.assertTrue(got["llm_review_tier_skipped_after_primary_failure"])

    def test_monthly_cap_still_wins(self):
        month = base.month_key(datetime.now(timezone.utc))
        previous = {"llm_budget_month": month, "llm_paid_attempts_month": 699, "jobs": []}
        payload = {"llm_budget_month": month, "llm_paid_attempts_month": 699, "jobs": [review_job("a"), review_job("b")]}
        with patch.object(base, "call_openai", return_value=strong_review()) as call:
            got = mod.enrich_review_tier(payload, previous, api_key="fake", model="test", max_paid_attempts_per_month=700)
        self.assertEqual(call.call_count, 1)
        self.assertEqual(got["llm_paid_attempts_month"], 700)
        self.assertTrue(got["llm_monthly_budget_exhausted"])


if __name__ == "__main__":
    unittest.main()
