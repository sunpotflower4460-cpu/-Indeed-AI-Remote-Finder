import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ClientDualPassParityTests(unittest.TestCase):
    def test_review_dual_pass_uses_current_server_quality_envelope(self):
        app = (ROOT / "app.js").read_text(encoding="utf-8")

        self.assertIn("function reviewStrictContextValid(j)", app)
        self.assertIn("j?.tier!=='review'", app)
        for needle in (
            "Number(j.quality_policy_version||0)===QUALITY_POLICY_VERSION",
            "j.quality_gate===QUALITY_GATE",
            "j.autonomy_attention_risk==='low'",
            "j.remote_search_only!==true",
            "Number(j.automation_confidence||0)>=REVIEW_AUTOMATION_MIN",
            "Number(j.human_dependency_risk||0)<=REVIEW_HUMAN_RISK_MAX",
            "reasons.size>=REVIEW_AUTOMATION_SIGNAL_MIN",
            "j.full_listing_presence_screened===true",
            "Number(j.presence_gate_version||0)===PRESENCE_GATE_VERSION",
            "j.continuous_presence_risk==='low'",
        ):
            self.assertIn(needle, app)

    def test_dual_pass_no_longer_requires_high_tier_but_still_requires_strict_review(self):
        app = (ROOT / "app.js").read_text(encoding="utf-8")

        self.assertNotIn(
            "function hasDualPass(j){return effectiveTier(j)==='high'&&j.llm_strict_pass===true;}",
            app,
        )
        self.assertIn("j?.llm_strict_pass!==true", app)
        self.assertIn("j?.llm_review?.strict_pass!==true", app)
        self.assertIn("effectiveTier(j)==='expired'", app)
        self.assertIn("if(j.tier==='high')return true;", app)
        self.assertIn("return reviewStrictContextValid(j);", app)

    def test_filter_badge_sorting_and_panel_share_dual_pass_function(self):
        app = (ROOT / "app.js").read_text(encoding="utf-8")

        self.assertIn("if(state.mode==='dual')return hasDualPass(j);", app)
        self.assertIn("dual=hasDualPass(j)", app)
        self.assertIn("return(hasDualPass(b)?1:0)-(hasDualPass(a)?1:0)", app)
        self.assertIn("strict=hasDualPass(j);", app)
        self.assertIn("${dual?'◎ 二重審査通過':verdictText(tier)}", app)

    def test_html_escaping_and_existing_date_format_are_unchanged(self):
        app = (ROOT / "app.js").read_text(encoding="utf-8")

        self.assertIn("'\"':'&quot;'", app)
        self.assertIn("month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'", app)


if __name__ == "__main__":
    unittest.main()
