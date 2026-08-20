import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CandidateContinuityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "continuity.js").read_text(encoding="utf-8")

    def test_actions_are_persisted_by_company_title_fingerprint(self):
        for marker in (
            "appliedJobFingerprintsV1",
            "declinedJobFingerprintsV1",
            "candidateFingerprint",
            "normalizedIdentity",
            "job?.company",
            "job?.title",
            "reconcileCurrentActionIds",
        ):
            self.assertIn(marker, self.source)

    def test_existing_id_history_is_migrated_not_discarded(self):
        self.assertIn("for(const id of state.applied)", self.source)
        self.assertIn("for(const id of state.declined)", self.source)
        self.assertIn("loadCachedJobs()", self.source)
        self.assertIn("persistSet('appliedJobs',state.applied)", self.source)
        self.assertIn("persistSet('declinedJobs',state.declined)", self.source)

    def test_source_id_change_is_reconciled_before_render(self):
        self.assertIn("const coreRender=render", self.source)
        self.assertIn("render=function()", self.source)
        self.assertIn("reconcileCurrentActionIds();", self.source)
        self.assertIn("state.applied.add(id)", self.source)
        self.assertIn("state.declined.add(id)", self.source)

    def test_today_count_uses_unique_stable_opportunities(self):
        self.assertIn("todayAppliedCount=function()", self.source)
        self.assertIn("appliedFingerprintAt", self.source)
        self.assertIn("appliedFingerprints.has(fp)", self.source)

    def test_direct_official_live_verification_uses_three_day_window(self):
        self.assertIn("official-provider-page", self.source)
        self.assertIn("official-provider-page-japan-depth", self.source)
        self.assertIn("official_live_verified_at", self.source)
        self.assertIn("liveAge<=ATS_LIVE_MAX_DAYS", self.source)
        self.assertIn("isLiveATSVerified=function(job)", self.source)
        self.assertIn("freshnessReference=function(job)", self.source)

    def test_direct_official_verification_is_not_mislabeled_as_ats_in_ui(self):
        self.assertIn("公式掲載確認済み", self.source)
        self.assertIn("公式掲載確認:", self.source)


if __name__ == "__main__":
    unittest.main()
