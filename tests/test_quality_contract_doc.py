import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class QualityContractDocTests(unittest.TestCase):
    def test_quality_contract_matches_runtime_thresholds(self):
        text = (ROOT / "docs" / "QUALITY_POLICY.md").read_text(encoding="utf-8")
        quality = (ROOT / "scripts" / "acquisition_quality.py").read_text(encoding="utf-8")
        self.assertIn("automation_confidence >= 64", text)
        self.assertIn("human_dependency_risk <= 18", text)
        self.assertIn("at least two distinct automation signals", text)
        self.assertIn("REVIEW_AUTOMATION_MIN = 64", quality)
        self.assertIn("REVIEW_HUMAN_RISK_MAX = 18", quality)
        self.assertIn("REVIEW_AUTOMATION_SIGNAL_MIN = 2", quality)
        self.assertIn("quantity never overrides", text)


if __name__ == "__main__":
    unittest.main()
