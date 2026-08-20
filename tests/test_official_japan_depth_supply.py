import importlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

mod = importlib.import_module("supplement_official_japan_depth")

DATAANNOTATION_TEXT = (
    "募集中 AIトレーナー 日本語 フルリモート 今すぐ応募。"
    "人工知能によって生成された回答をレビュー、評価、改善します。"
    "翻訳、文章作成、ファクトチェック、品質評価を自分のスケジュールで行います。"
)

ONEFORMA_TEXT = (
    "Bilingual Translation Quality Rater. Japan Remote. Open Accepting applications. "
    "Compare source sentences with translations and score translation quality using a defined scale. "
    "Perform language annotation and structured quality evaluation independently online."
)


class OfficialJapanDepthSupplyTests(unittest.TestCase):
    def setUp(self):
        mod.acquisition._production_quality_policy_configured = False
        mod.acquisition._production_remote_policy_configured = False
        mod.acquisition.build_row = mod.acquisition_precision._ORIGINAL_ACQUISITION_BUILD_ROW
        mod.acquisition.legacy.score_job = mod.acquisition_quality.GENERIC_SCORE_JOB

    def test_dataannotation_official_page_uses_existing_production_builder(self):
        out = mod.supplement(
            {"jobs": []},
            {},
            fetched_pages={"dataannotation-japanese": DATAANNOTATION_TEXT},
        )
        self.assertFalse(out["candidate_official_japan_depth_uses_serpapi"])
        self.assertTrue(out["candidate_official_japan_depth_quality_gate_unchanged"])
        self.assertGreaterEqual(out["candidate_official_japan_depth_deterministic_accepted"], 1)
        rows = [x for x in out["jobs"] if x.get("official_provider") == "DataAnnotation"]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["quality_gate"], "async-ai-remote-v2")
        self.assertEqual(row["autonomy_attention_risk"], "low")
        self.assertEqual(row["apply_source"], "DataAnnotation")
        self.assertEqual(row["apply_source_kind"], "trusted-provider")
        self.assertIsNot(row.get("remote_search_only"), True)

    def test_oneforma_japan_translation_quality_page_is_admitted(self):
        out = mod.supplement(
            {"jobs": []},
            {},
            fetched_pages={"oneforma-bilingual-translation-quality-japan": ONEFORMA_TEXT},
        )
        rows = [x for x in out["jobs"] if x.get("official_provider") == "OneForma"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["apply_source"], "OneForma")
        self.assertEqual(rows[0]["discovery_source"], "official-provider-page-japan-depth")

    def test_closed_media_or_automation_banned_pages_are_rejected(self):
        data_spec = next(x for x in mod.SOURCES if x.key == "dataannotation-japanese")
        oneforma_spec = next(x for x in mod.SOURCES if x.key == "oneforma-bilingual-translation-quality-japan")
        self.assertFalse(mod._live_text(data_spec, DATAANNOTATION_TEXT + " 現在募集していません。"))
        self.assertFalse(mod._live_text(oneforma_spec, ONEFORMA_TEXT + " You must record your voice."))
        self.assertFalse(mod._live_text(oneforma_spec, ONEFORMA_TEXT + " Bots or scripts are not allowed for task completion."))

    def test_japan_signal_is_required_for_oneforma(self):
        spec = next(x for x in mod.SOURCES if x.key == "oneforma-bilingual-translation-quality-japan")
        self.assertTrue(mod._live_text(spec, ONEFORMA_TEXT))
        self.assertFalse(mod._live_text(spec, ONEFORMA_TEXT.replace("Japan", "")))

    def test_pre_final_target_skips_source_work(self):
        existing = [{"id": f"existing-{i}"} for i in range(120)]
        out = mod.supplement({"jobs": existing}, {}, fetched_pages={})
        self.assertEqual(len(out["jobs"]), 120)
        self.assertEqual(out["candidate_official_japan_depth_skipped"], "pool-at-or-above-pre-final-target")


if __name__ == "__main__":
    unittest.main()
