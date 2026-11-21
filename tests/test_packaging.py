import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class PackagingTests(unittest.TestCase):
    def test_icon_files_exist(self):
        self.assertTrue((ROOT / "resources" / "icon.png").is_file())
        self.assertTrue((ROOT / "resources" / "icon.ico").is_file())

    def test_spec_uses_ico_for_executable(self):
        spec = (ROOT / "main.spec").read_text(encoding="utf-8")
        self.assertIn("icon.ico", spec)
        self.assertIn("('resources/icon.png', 'resources')", spec)


if __name__ == "__main__":
    unittest.main()
