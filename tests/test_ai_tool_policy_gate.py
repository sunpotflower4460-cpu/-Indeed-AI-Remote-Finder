import importlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

mod = importlib.import_module("apply_ai_tool_policy_gate")


def row(snippet: str, *, jid="a") -> dict:
    return {
        "id": jid,
        "title": "完全在宅 AI評価",
        "location": "日本",
        "snippet": snippet,
        "tier": "review",
        "carryover": False,
        "seen_count": 1,
    }


class AiToolPolicyGateTests(unittest.TestCase):
    def test_explicit_japanese_ai_bans_are_rejected(self):
        samples = (
            "完全在宅。生成AIの使用は禁止です。",
            "完全在宅。AIツールの利用は不可です。",
            "完全在宅。ChatGPTを使用しないで作業してください。",
            "完全在宅。外部AIの使用は禁止。",
            "完全在宅。ボットの使用は禁止です。",
            "完全在宅。自動化ツールの利用は不可です。",
        )
        for text in samples:
            status, signal = mod.policy_signal(row(text))
            self.assertEqual(status, "prohibited", text)
            self.assertTrue(signal, text)

    def test_explicit_english_ai_or_automation_bans_are_rejected(self):
        for text in (
            "Fully remote. AI tools are prohibited for this assignment.",
            "Fully remote. Complete the work without AI assistance.",
            "Fully remote. You must not use generative AI.",
            "Fully remote. Bots or scripts are not allowed for task completion.",
            "Complete all tasks by yourself without seeking assistance from technological automation such as bots or scripts.",
            "AI Trainers avoid using generated content for training.",
        ):
            self.assertEqual(mod.policy_signal(row(text))[0], "prohibited", text)

    def test_explicit_permission_is_retained_and_stamped(self):
        payload = {"jobs": [row("完全在宅。生成AIの利用可。必要に応じてAIツールを使用できます。")]}
        got = mod.apply(payload)
        self.assertEqual(len(got["jobs"]), 1)
        item = got["jobs"][0]
        self.assertEqual(item["ai_tool_policy_status"], "explicitly-allowed")
        self.assertFalse(item["ai_tool_use_permission_confirm_required"])
        self.assertEqual(got["candidate_ai_tool_policy_explicitly_allowed"], 1)

    def test_unstated_permission_is_not_over_rejected(self):
        payload = {"jobs": [row("完全在宅。AIモデルの回答を比較・評価する仕事です。")]}
        got = mod.apply(payload)
        self.assertEqual(len(got["jobs"]), 1)
        item = got["jobs"][0]
        self.assertEqual(item["ai_tool_policy_status"], "not-stated")
        self.assertTrue(item["ai_tool_use_permission_confirm_required"])
        self.assertEqual(got["candidate_ai_tool_policy_confirmation_required"], 1)

    def test_prohibited_rows_are_removed_and_final_counts_recomputed(self):
        payload = {
            "jobs": [
                row("完全在宅。生成AI使用禁止。", jid="ban"),
                row("完全在宅。AI回答を評価します。", jid="keep"),
            ]
        }
        got = mod.apply(payload)
        self.assertEqual([x["id"] for x in got["jobs"]], ["keep"])
        self.assertEqual(got["candidate_ai_tool_policy_dropped"], 1)
        self.assertTrue(got["candidate_rejects_explicit_ai_tool_bans"])
        self.assertTrue(got["candidate_rejects_explicit_automation_bans"])
        self.assertEqual(got["candidate_pool_size"], 1)
        self.assertEqual(got["live_jobs"], 1)
        self.assertEqual(got["new_jobs"], 1)


if __name__ == "__main__":
    unittest.main()
