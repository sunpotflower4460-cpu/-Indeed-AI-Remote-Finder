import json
import struct
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def png_size(path: Path) -> tuple[int, int]:
    raw = path.read_bytes()
    if raw[:8] != b"\x89PNG\r\n\x1a\n":
        raise AssertionError(f"{path.name} is not a PNG")
    return struct.unpack(">II", raw[16:24])


class PWAInstallContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((ROOT / "manifest.webmanifest").read_text(encoding="utf-8"))
        cls.sw = (ROOT / "sw.js").read_text(encoding="utf-8")
        cls.pages = (ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8")

    def test_manifest_has_stable_mobile_install_identity(self):
        self.assertEqual(self.manifest["id"], "./")
        self.assertEqual(self.manifest["lang"], "ja")
        self.assertEqual(self.manifest["display"], "standalone")
        self.assertEqual(self.manifest["orientation"], "portrait-primary")
        self.assertEqual(self.manifest["start_url"], "./")
        self.assertEqual(self.manifest["scope"], "./")

    def test_manifest_has_mobile_png_icons_and_svg_fallback(self):
        icons = {(x["src"], x["sizes"], x["type"]) for x in self.manifest["icons"]}
        self.assertIn(("./icon-180.png", "180x180", "image/png"), icons)
        self.assertIn(("./icon-192.png", "192x192", "image/png"), icons)
        self.assertIn(("./icon-512.png", "512x512", "image/png"), icons)
        self.assertIn(("./icon.svg", "any", "image/svg+xml"), icons)
        maskable = [x for x in self.manifest["icons"] if "maskable" in x.get("purpose", "")]
        self.assertTrue(maskable)

    def test_png_files_have_the_dimensions_their_names_claim(self):
        self.assertEqual(png_size(ROOT / "icon-180.png"), (180, 180))
        self.assertEqual(png_size(ROOT / "icon-192.png"), (192, 192))
        self.assertEqual(png_size(ROOT / "icon-512.png"), (512, 512))

    def test_service_worker_precaches_all_install_icons(self):
        self.assertIn("ai-remote-finder-v13", self.sw)
        for name in ("icon-180.png", "icon-192.png", "icon-512.png"):
            self.assertIn(name, self.sw)

    def test_pages_artifact_contains_all_install_icons(self):
        self.assertIn("cp icon-180.png icon-192.png icon-512.png _site/", self.pages)


if __name__ == "__main__":
    unittest.main()
