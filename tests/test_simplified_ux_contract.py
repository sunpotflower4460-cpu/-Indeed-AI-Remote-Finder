import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SimplifiedUXContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ux = (ROOT / "ux.js").read_text(encoding="utf-8")
        cls.source_tabs = (ROOT / "source-tabs.js").read_text(encoding="utf-8")
        cls.indeed_config = (ROOT / "indeed-partner-config.js").read_text(encoding="utf-8")
        cls.indeed_official = (ROOT / "indeed-official.js").read_text(encoding="utf-8")
        cls.pages = (ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8")
        cls.check = (ROOT / ".github/workflows/check.yml").read_text(encoding="utf-8")

    def test_default_surface_is_japanese_and_hides_internal_jargon(self):
        for needle in (
            "AI在宅求人ナビ",
            "今日見るべき求人だけ、分かりやすく",
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

    def test_indeed_and_other_sources_are_separate(self):
        self.assertIn("let sourceMode='indeed'", self.source_tabs)
        self.assertIn("function isVerifiedIndeed(job)", self.source_tabs)
        self.assertIn("sourceMode==='indeed'?isVerifiedIndeed(job):!isVerifiedIndeed(job)", self.source_tabs)
        self.assertIn("Indeed ${counts.indeed}件", self.source_tabs)
        self.assertIn("その他の求人サイト ${counts.other}件", self.source_tabs)
        self.assertIn("掲載元：${label}", self.source_tabs)
        self.assertIn("${label}で求人を見る →", self.source_tabs)
        self.assertIn("現在、Indeed掲載を確認できた候補はありません。", self.source_tabs)

    def test_verified_indeed_requires_exact_viewjob_url(self):
        for needle in ("apply_source_kind", "/viewjob", "searchParams.get('jk')"):
            self.assertIn(needle, self.source_tabs)
        self.assertNotIn("Indeedで同じ求人を探す", self.source_tabs)

    def test_official_plugin_is_disabled_until_partner_ids_are_supplied(self):
        self.assertIn("partnerAppId:''", self.indeed_config)
        self.assertIn("placementId:''", self.indeed_config)
        self.assertIn("https://plugins.indeed.com/publisher-plugin/main.js", self.indeed_official)
        self.assertIn("data.indeedPluginType='job-search'", self.indeed_official)
        self.assertIn("Indeed公式検索", self.indeed_official)
        self.assertIn("!configured()||!indeedMode", self.indeed_official)

    def test_official_indeed_adapter_is_last_in_pages_bundle_and_syntax_checked(self):
        self.assertIn(
            "cat integrity.js refill.js continuity.js ux.js source-tabs.js indeed-partner-config.js indeed-official.js >> _site/app.js",
            self.pages,
        )
        for filename in ("ux.js", "source-tabs.js", "indeed-partner-config.js", "indeed-official.js"):
            self.assertIn(f"node --check {filename}", self.check)


if __name__ == "__main__":
    unittest.main()
