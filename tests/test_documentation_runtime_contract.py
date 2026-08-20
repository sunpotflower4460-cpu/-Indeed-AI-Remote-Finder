import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DocumentationRuntimeContractTests(unittest.TestCase):
    def test_readme_uses_single_main_push_post_merge_path(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        contract = (ROOT / "docs/REFRESH_CONTRACT.md").read_text(encoding="utf-8")

        self.assertFalse((ROOT / ".github/workflows/refresh-after-merge.yml").exists())
        self.assertNotIn("trusted main-branch refresh dispatcher", readme)
        self.assertNotIn("`.github/workflows/refresh-after-merge.yml`", readme)
        self.assertIn("唯一の自動post-merge refresh経路", readme)
        self.assertIn("single automatic post-merge refresh path", contract)

    def test_readme_documents_remaining_month_pacing(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("深掘り上限は**1回7検索**", readme)
        self.assertIn("実効検索数を7未満へ自動ペーシング", readme)
        self.assertIn("月間ハード上限を緩めない", readme)

    def test_readme_does_not_promote_review_tier_after_llm_strict_pass(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("PWA上で「◎ LLM二重審査通過」", readme)
        self.assertIn("`tier` 自体を `high` へ昇格させるわけではありません", readme)

    def test_quality_policy_matches_pacing_and_single_trigger_runtime(self):
        policy = (ROOT / "docs/QUALITY_POLICY.md").read_text(encoding="utf-8")

        self.assertIn("nominal deep-search ceiling is seven SerpApi requests per run", policy)
        self.assertIn("can lower the effective request count below seven", policy)
        self.assertIn("single automatic post-merge refresh path", policy)
        self.assertIn("there is intentionally no second merged-PR dispatcher", policy)
        self.assertNotIn("Relevant merges dispatch a main-branch refresh", policy)

    def test_supply_module_documents_actual_150_row_taper_and_pacing(self):
        supply = (ROOT / "scripts/acquisition_supply.py").read_text(encoding="utf-8")

        self.assertIn("remaining-month pacing and provider guards may lower", supply)
        self.assertIn("50..149 candidates: 4 searches/run", supply)
        self.assertIn("150+ candidates: 2 searches/run", supply)
        self.assertNotIn("100 candidates: 2 searches/run", supply)


if __name__ == "__main__":
    unittest.main()
