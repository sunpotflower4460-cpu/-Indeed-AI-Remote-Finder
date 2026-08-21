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
        cls.source_presentation = (ROOT / "source-presentation.js").read_text(encoding="utf-8")
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
        self.assertIn("function seedEvidenceCounts()", self.source_tabs)
        self.assertIn("掲載元：${label}", self.source_tabs)
        self.assertIn("${label}で求人を見る →", self.source_tabs)
        self.assertIn("これはIndeed全体が0件という意味ではありません。", self.source_tabs)

    def test_verified_indeed_requires_exact_viewjob_url_and_discloses_body_status(self):
        for needle in ("apply_source_kind", "/viewjob", "searchParams.get('jk')"):
            self.assertIn(needle, self.source_tabs)
        self.assertIn("Indeed実URL＋会社照合済み・Indeed本文は未自動取得", self.source_tabs)
        self.assertNotIn("Indeedで同じ求人を探す", self.source_tabs)

    def test_indeed_live_search_uses_query_remote_intent_not_fake_location(self):
        for needle in (
            "Indeed本体から探す",
            "Indeed本体で検索 →",
            "candidate_indeed_index_seeds",
            "Indeed候補",
            "https://jp.indeed.com/jobs",
            "normalizeIndeedQuery",
            "探索語カバレッジ",
            "実URL確認済み・本文未自動取得",
        ):
            self.assertIn(needle, self.indeed_official)
        self.assertIn("url.searchParams.set('q',normalizeIndeedQuery(query))", self.indeed_official)
        self.assertNotIn("url.searchParams.set('l','在宅')", self.indeed_official)
        self.assertIn("DEFAULT_QUERY='AI 在宅'", self.indeed_official)
        self.assertIn("PRESETS", self.indeed_official)

    def test_vjk_leads_are_visibly_weaker_than_exact_urls(self):
        for needle in (
            "求人ID確認（vjk）",
            "candidate_indeed_index_search_vjk_seed_count",
            "求人ID（vjk）確認・個別URLはIDから生成・本文未確認",
            "Indeed求人ID候補",
            "seedKind(seed)==='search-vjk'",
            "実URL ${counts.exact} / 求人ID ${counts.vjk}",
        ):
            self.assertIn(needle, self.indeed_official)
        self.assertIn("「実URL確認」「求人ID確認」「AI代替適性まで確認」", self.source_tabs)

    def test_indeed_leads_are_rendered_in_the_main_list(self):
        for needle in (
            "function renderIndeedMain()",
            "Indeedで見つけた求人候補",
            "AI代替適性まで確認済み",
            "Indeed実URL確認済み",
            "求人ID確認済み（vjk）",
            "Indeedで求人を見る",
            "Indeedで候補本文を確認",
        ):
            self.assertIn(needle, self.source_presentation)
        self.assertIn("document.querySelector('#indeedSeedArea')?.classList.add('sourcePresentationDuplicateHidden')", self.source_presentation)
        self.assertIn("Indeed候補 ${raw.length}件（AI適性 ${verified} / 実URL ${exact} / 求人ID ${vjk}）", self.source_presentation)

    def test_other_sources_prioritize_japanese_and_use_japanese_role_titles(self):
        for needle in (
            "function japanesePriority(job)",
            "function japaneseRoleTitle(value,profile='')",
            "日本語AI言語評価スタッフ",
            "日本語・言語品質評価スタッフ",
            "AIトレーナー・評価スタッフ",
            "データアノテーションスタッフ",
            "その他の求人サイト（日本語・日本向けを優先）",
            "その他の求人サイト ${count}件（日本語優先）",
        ):
            self.assertIn(needle, self.source_presentation)
        self.assertIn("if(JAPANESE_RE.test(title))score+=100", self.source_presentation)
        self.assertIn("if(job.japan_eligibility_status==='japan-explicit')score+=60", self.source_presentation)

    def test_official_plugin_is_ready_but_disabled_until_partner_ids_are_supplied(self):
        self.assertIn("partnerAppId:''", self.indeed_config)
        self.assertIn("placementId:''", self.indeed_config)
        self.assertIn("searchWhat:'AI 在宅'", self.indeed_config)
        self.assertIn("https://plugins.indeed.com/publisher-plugin/main.js", self.indeed_official)
        self.assertIn("dataset.indeedPluginType='job-search'", self.indeed_official)
        self.assertIn("Indeed公式ライブ検索（アプリ内）", self.indeed_official)
        self.assertIn("publisher?.classList.toggle('uxHidden',!configured())", self.indeed_official)

    def test_final_source_presentation_is_last_in_pages_bundle_and_syntax_checked(self):
        self.assertIn(
            "cat integrity.js refill.js continuity.js ux.js source-tabs.js indeed-partner-config.js indeed-official.js source-presentation.js >> _site/app.js",
            self.pages,
        )
        for filename in (
            "ux.js",
            "source-tabs.js",
            "indeed-partner-config.js",
            "indeed-official.js",
            "source-presentation.js",
        ):
            self.assertIn(f"node --check {filename}", self.check)


if __name__ == "__main__":
    unittest.main()
