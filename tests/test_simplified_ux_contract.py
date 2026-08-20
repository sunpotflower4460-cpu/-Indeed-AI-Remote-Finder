import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SimplifiedUXContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ux = (ROOT / "ux.js").read_text(encoding="utf-8")
        cls.pages = (ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8")
        cls.check = (ROOT / ".github/workflows/check.yml").read_text(encoding="utf-8")

    def test_default_surface_is_japanese_and_hides_internal_jargon(self):
        for needle in (
            "AI在宅求人ナビ",
            "今日見るべき求人だけ、分かりやすく",
            "英語の原文や細かな判定は「詳しく見る」に収納",
            "AI評価",
            "文章・翻訳",
            "データ作業",
            "技術・専門",
        ):
            self.assertIn(needle, self.ux)
        self.assertIn("['high','dual','review']", self.ux)
        self.assertIn("classList.add('uxHidden')", self.ux)

    def test_similar_jobs_are_grouped_instead_of_flattened(self):
        self.assertIn("function jobFamily(job)", self.ux)
        self.assertIn("function groupRows(rows)", self.ux)
        self.assertIn("似た求人があと", self.ux)
        self.assertIn("`${groups.length}種類 / ${rows.length}件`", self.ux)

    def test_english_source_text_is_opt_in_only(self):
        self.assertIn("求人原文を見る（英語の場合あり）", self.ux)
        self.assertIn("function titleJa(job)", self.ux)
        self.assertIn("function jobDetails(job)", self.ux)
        self.assertNotIn('class="snippet"', self.ux)

    def test_indeed_is_primary_and_exact_listing_is_used_when_verified(self):
        self.assertIn("function directIndeedUrl(job)", self.ux)
        self.assertIn("/viewjob", self.ux)
        self.assertIn("job?.apply_source_kind==='indeed'?job?.url:''", self.ux)
        self.assertIn("Indeedで求人を見る", self.ux)
        self.assertIn("Indeedで同じ求人を探す", self.ux)
        self.assertIn("https://jp.indeed.com/jobs", self.ux)
        self.assertIn("会社名＋求人名の検索結果", self.ux)
        self.assertIn("公式求人", self.ux)

    def test_ux_layer_is_last_in_pages_bundle_and_syntax_checked(self):
        self.assertIn("cat integrity.js refill.js continuity.js ux.js >> _site/app.js", self.pages)
        self.assertIn("node --check ux.js", self.check)


if __name__ == "__main__":
    unittest.main()
