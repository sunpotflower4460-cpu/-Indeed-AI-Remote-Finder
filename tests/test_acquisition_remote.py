import importlib.util
import inspect
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

path = SCRIPTS / "acquisition_remote.py"
spec = importlib.util.spec_from_file_location("acquisition_remote_supply_test", path)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def job(description, jid="remote123", title="完全在宅 データ入力スタッフ"):
    return {
        "title": title,
        "company_name": "Example",
        "location": "日本",
        "description": description,
        "detected_extensions": {"posted_at": "1 day ago"},
        "apply_options": [
            {"title": "Indeed", "link": f"https://jp.indeed.com/viewjob?jk={jid}"}
        ],
    }


class ProductionRemoteAcquisitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        mod.configure_production_policy()

    def test_server_stays_in_replenishment_until_one_hundred(self):
        self.assertEqual(mod.SERVER_POOL_TARGET, 100)
        self.assertEqual(mod.acquisition.DISPLAY_TARGET, 100)
        self.assertEqual(mod.acquisition.POOL_TARGET, 100)
        self.assertEqual(mod.acquisition.POOL_LIMIT, 100)
        self.assertEqual(mod.acquisition.request_limit_for_pool(99), 30)
        self.assertEqual(mod.acquisition.request_limit_for_pool(100), 2)

    def test_shallow_pool_can_sweep_all_profiles_and_page_deeper(self):
        self.assertGreaterEqual(
            mod.acquisition.MAX_REQUESTS_PER_RUN,
            len(mod.acquisition.QUERY_PROFILES),
        )
        self.assertGreater(
            mod.acquisition.MAX_REQUESTS_PER_RUN,
            len(mod.acquisition.QUERY_PROFILES),
        )

    def test_production_fetch_supports_next_page_token(self):
        params = inspect.signature(mod.acquisition.serpapi_fetch).parameters
        self.assertIn("next_page_token", params)

    def test_generated_serpapi_next_url_is_preferred_for_page_two(self):
        calls = []
        responses = [
            {
                "jobs_results": [],
                "serpapi_pagination": {
                    "next_page_token": "TOKEN123",
                    "next": (
                        "https://serpapi.com/search.json?engine=google_jobs&q=test"
                        "&next_page_token=TOKEN123&uds=SERVER_FILTER&api_key=OLD_KEY"
                    ),
                },
            },
            {"jobs_results": []},
        ]

        def fake_urlopen(request, timeout=30):
            calls.append(request.full_url)
            return FakeResponse(responses.pop(0))

        with patch.object(mod.urllib.request, "urlopen", side_effect=fake_urlopen):
            mod.acquisition.serpapi_fetch("test", "NEW_SECRET")
            mod.acquisition.serpapi_fetch(
                "test", "NEW_SECRET", next_page_token="TOKEN123"
            )

        self.assertEqual(len(calls), 2)
        self.assertIn("ltype=1", calls[0])
        self.assertIn("uds=SERVER_FILTER", calls[1])
        self.assertIn("next_page_token=TOKEN123", calls[1])
        self.assertNotIn("ltype=1", calls[1])
        self.assertNotIn("OLD_KEY", calls[1])
        self.assertIn("api_key=NEW_SECRET", calls[1])

    def test_provider_budget_reserves_hourly_headroom(self):
        account = {
            "account_rate_limit_per_hour": 50,
            "this_hour_searches": 45,
            "total_searches_left": 100,
        }
        self.assertEqual(mod.provider_request_budget(account), 3)

    def test_provider_budget_never_exceeds_monthly_searches_left(self):
        account = {
            "account_rate_limit_per_hour": 50,
            "this_hour_searches": 5,
            "total_searches_left": 2,
        }
        self.assertEqual(mod.provider_request_budget(account), 2)

    def test_provider_budget_returns_zero_when_hour_is_full(self):
        account = {
            "account_rate_limit_per_hour": 50,
            "this_hour_searches": 50,
            "total_searches_left": 100,
        }
        self.assertEqual(mod.provider_request_budget(account), 0)

    def test_provider_month_usage_uses_account_source_of_truth(self):
        self.assertEqual(mod.provider_month_usage({"this_month_usage": 108}), 108)
        self.assertIsNone(mod.provider_month_usage({"this_month_usage": "bad"}))

    def test_account_api_request_is_read_only_and_not_persisted(self):
        calls = []

        def fake_urlopen(request, timeout=15):
            calls.append((request.full_url, timeout))
            return FakeResponse(
                {
                    "this_month_usage": 108,
                    "this_hour_searches": 48,
                    "account_rate_limit_per_hour": 50,
                    "total_searches_left": 142,
                    "account_email": "private@example.com",
                    "api_key": "SECRET",
                }
            )

        with patch.object(mod.urllib.request, "urlopen", side_effect=fake_urlopen):
            account = mod.fetch_serpapi_account("SECRET")

        self.assertEqual(account["this_month_usage"], 108)
        self.assertEqual(len(calls), 1)
        self.assertIn("/account.json?", calls[0][0])
        self.assertIn("api_key=SECRET", calls[0][0])
        self.assertEqual(calls[0][1], 15)

    def test_synchronous_customer_contact_is_hard_excluded(self):
        row = mod.acquisition.build_row(
            job("完全在宅。データ入力、転記、問い合わせ対応をリアルタイムで行います。"),
            "structured_data",
            {},
        )
        self.assertIsNone(row)

    def test_live_monitoring_is_hard_excluded(self):
        row = mod.acquisition.build_row(
            job("完全在宅。データチェックと常時監視、異常時の即時対応を行います。"),
            "testing",
            {},
        )
        self.assertIsNone(row)

    def test_meeting_and_coordination_role_is_hard_excluded(self):
        row = mod.acquisition.build_row(
            job("完全在宅。データ集計、定例会議参加、進行管理、スケジュール調整。"),
            "backoffice",
            {},
        )
        self.assertIsNone(row)

    def test_negated_phone_requirement_is_not_false_excluded(self):
        row = mod.acquisition.build_row(
            job("完全在宅。電話対応なし。データ入力、転記、データ整理を行います。"),
            "structured_data",
            {},
        )
        self.assertIsNotNone(row)
        self.assertEqual(row["autonomy_attention_risk"], "low")
        self.assertIn("張り付きリスク低", row["tags"])

    def test_structured_work_from_home_is_review_evidence_not_high_proof(self):
        row = mod.acquisition.build_row(
            job(
                "データ入力と転記、Excelでのデータ整理を担当します。",
                title="データ入力スタッフ",
            ),
            "structured_data",
            {},
        )
        self.assertIsNotNone(row)
        self.assertEqual(row["tier"], "review")
        self.assertTrue(row["remote_search_only"])
        self.assertIn("在宅要確認", row["tags"])
        self.assertEqual(row["autonomy_attention_risk"], "low")
        self.assertTrue(any("本文要確認" in reason for reason in row["remote_reasons"]))

    def test_explicit_full_remote_review_does_not_need_warning_label(self):
        row = mod.acquisition.build_row(
            job("完全在宅でデータ入力を担当します。", jid="remote456"),
            "structured_data",
            {},
        )
        self.assertIsNotNone(row)
        self.assertFalse(row.get("remote_search_only"))
        self.assertNotIn("在宅要確認", row.get("tags") or [])
        self.assertEqual(row["autonomy_attention_risk"], "low")


if __name__ == "__main__":
    unittest.main()
