import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

path = SCRIPTS / "validate_feed.py"
spec = importlib.util.spec_from_file_location("validate_feed_capacity_test", path)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class FeedCapacityTests(unittest.TestCase):
    def _payload(self, count: int) -> dict:
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "jobs": [{} for _ in range(count)],
        }

    def test_validator_capacity_matches_server_reserve(self):
        self.assertEqual(mod.MAX_JOBS, 150)
        errors = mod.validate(self._payload(101))
        self.assertFalse(any(error.startswith("jobs exceeds limit") for error in errors))

    def test_validator_still_rejects_above_server_reserve(self):
        errors = mod.validate(self._payload(151))
        self.assertIn("jobs exceeds limit: 151", errors)


if __name__ == "__main__":
    unittest.main()
