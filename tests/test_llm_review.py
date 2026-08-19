import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

path = Path(__file__).resolve().parents[1] / "scripts" / "llm_review.py"
spec = importlib.util.spec_from_file_location("llm_review", path)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def job(jid="abc123", snippet="データ入力と転記を行う完全在宅業務"):
    return {
        "id": jid,
        "title": "完全在宅 データ入力",
        "company": "Example",
        "location": "日本 / フルリモート",
        "snippet": snippet,
        "tier": "high",
        "automation_confidence": 95,
        "remote_confidence": 100,
        "freshness_confidence": 90,
        "human_dependency_risk": 0,
        "automation_reasons": ["データ入力", "転記"],
        "risk_reasons": [],
        "tags": ["完全リモート", "データ"],
    }


def good_review():
    return {
        "verdict": "strong",
        "automatable_fraction": 95,
        "confidence": 90,
        "human_dependency": "low",
        "physical_presence_required": False,
        "synchronous_human_interaction": "none",
        "data_sensitivity_risk": "unknown",
        "automation_summary": "定型デジタル処理中心",
        "automation_plan": ["入力を取得", "AIで処理", "結果を出力"],
        "blockers": [],
        "questions_to_confirm": ["生成AI利用が許可されるか"],
    }


class LlmReviewTests(unittest.TestCase):
    def test_default_paid_review_cap_is_eight(self):
        self.assertEqual(mod.DEFAULT_MAX_NEW_REVIEWS, 8)

    def test_monthly_attempt_cap_has_headroom(self):
        self.assertEqual(mod.DEFAULT_MAX_PAID_ATTEMPTS_PER_MONTH, 700)

    def test_request_uses_no_reasoning_for_classifier(self):
        body = mod.request_body(job(), "gpt-5.6-luna")
        self.assertEqual(body["reasoning"], {"effort": "none"})
        self.assertFalse(body["store"])
        self.assertEqual(body["max_output_tokens"], 900)
        self.assertNotIn("freshness_confidence", body["input"])

    def test_input_hash_changes_with_material_text(self):
        a = mod.input_hash(job(snippet="データ入力と転記"))
        b = mod.input_hash(job(snippet="電話営業と顧客対応"))
        self.assertNotEqual(a, b)

    def test_input_hash_ignores_freshness_only_changes(self):
        a = job()
        b = job()
        a["freshness_confidence"] = 98
        b["freshness_confidence"] = 52
        self.assertEqual(mod.input_hash(a), mod.input_hash(b))

    def test_input_hash_changes_when_review_policy_changes(self):
        row = job()
        a = mod.input_hash(row)
        with patch.object(mod, "REASONING_EFFORT", "low"):
            b = mod.input_hash(row)
        self.assertNotEqual(a, b)

    def test_extract_output_text_from_response_shape(self):
        payload = {
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": '{"verdict":"strong"}'}],
                }
            ]
        }
        self.assertEqual(mod.extract_output_text(payload), '{"verdict":"strong"}')

    def test_normalize_strict_pass(self):
        review = mod.normalize_review(good_review())
        self.assertTrue(review["strict_pass"])

    def test_strict_pass_rejects_occasional_sync(self):
        raw = good_review()
        raw["synchronous_human_interaction"] = "occasional"
        review = mod.normalize_review(raw)
        self.assertFalse(review["strict_pass"])

    def test_reuses_same_hash_without_api(self):
        row = job()
        digest = mod.input_hash(row)
        previous_row = dict(row)
        previous_row.update(
            {
                "llm_input_hash": digest,
                "llm_model": "test-model",
                "llm_review": {**good_review(), "strict_pass": True},
            }
        )
        payload = {"jobs": [dict(row)]}
        previous = {"jobs": [previous_row]}
        got = mod.enrich(payload, previous, api_key="", model="test-model")
        self.assertEqual(got["llm_reviewed_jobs"], 1)
        self.assertEqual(got["llm_reused_reviews"], 1)
        self.assertTrue(got["jobs"][0]["llm_strict_pass"])

    def test_freshness_change_reuses_previous_review_without_api(self):
        previous_row = job()
        previous_row["freshness_confidence"] = 98
        digest = mod.input_hash(previous_row)
        previous_row.update(
            {
                "llm_input_hash": digest,
                "llm_model": "test-model",
                "llm_review": {**good_review(), "strict_pass": True},
            }
        )
        current_row = job()
        current_row["freshness_confidence"] = 70
        with patch.object(mod, "call_openai", side_effect=AssertionError("must reuse cache")):
            got = mod.enrich(
                {"jobs": [current_row]},
                {"jobs": [previous_row]},
                api_key="fake-key",
                model="test-model",
            )
        self.assertEqual(got["llm_new_reviews"], 0)
        self.assertEqual(got["llm_reused_reviews"], 1)

    def test_model_change_does_not_reuse_old_review_when_api_enabled(self):
        row = job()
        digest = mod.input_hash(row)
        previous_row = dict(row)
        previous_row.update(
            {
                "llm_input_hash": digest,
                "llm_model": "old-model",
                "llm_review": {**good_review(), "strict_pass": True},
            }
        )
        with patch.object(mod, "call_openai", return_value=mod.normalize_review(good_review())) as call:
            got = mod.enrich(
                {"jobs": [dict(row)]},
                {"jobs": [previous_row]},
                api_key="fake-key",
                model="new-model",
            )
        self.assertEqual(call.call_count, 1)
        self.assertEqual(got["jobs"][0]["llm_model"], "new-model")

    def test_review_tier_never_spends_on_new_llm_call(self):
        row = job()
        row["tier"] = "review"
        with patch.object(mod, "call_openai", side_effect=AssertionError("should not call OpenAI")):
            got = mod.enrich({"jobs": [row]}, {}, api_key="fake-key", model="test-model")
        self.assertEqual(got["llm_new_reviews"], 0)
        self.assertEqual(got["llm_skipped_non_high"], 1)
        self.assertNotIn("llm_review", got["jobs"][0])

    def test_monthly_cap_blocks_manual_overrun(self):
        month = mod.month_key(datetime.now(timezone.utc))
        previous = {
            "llm_budget_month": month,
            "llm_paid_attempts_month": 700,
            "jobs": [],
        }
        with patch.object(mod, "call_openai", side_effect=AssertionError("budget should block call")):
            got = mod.enrich(
                {"jobs": [job()]},
                previous,
                api_key="fake-key",
                model="test-model",
            )
        self.assertEqual(got["llm_new_reviews"], 0)
        self.assertEqual(got["llm_paid_attempts_month"], 700)
        self.assertTrue(got["llm_monthly_budget_exhausted"])

    def test_old_month_budget_resets(self):
        previous = {
            "llm_budget_month": "2000-01",
            "llm_paid_attempts_month": 700,
            "jobs": [],
        }
        with patch.object(mod, "call_openai", return_value=mod.normalize_review(good_review())):
            got = mod.enrich(
                {"jobs": [job()]},
                previous,
                api_key="fake-key",
                model="test-model",
            )
        self.assertEqual(got["llm_paid_attempts_month"], 1)
        self.assertEqual(got["llm_new_reviews"], 1)

    def test_fatal_4xx_stops_additional_paid_calls(self):
        rows = [job("a"), job("b"), job("c")]
        fatal = mod.OpenAIRequestError(401, "invalid key")
        with patch.object(mod, "call_openai", side_effect=fatal) as call:
            got = mod.enrich(
                {"jobs": rows},
                {},
                api_key="fake-key",
                model="test-model",
            )
        self.assertEqual(call.call_count, 1)
        self.assertEqual(got["llm_paid_attempts_month"], 1)
        self.assertEqual(got["llm_review_failures"], 1)
        self.assertIn("401", got["llm_fatal_error"])


if __name__ == "__main__":
    unittest.main()
