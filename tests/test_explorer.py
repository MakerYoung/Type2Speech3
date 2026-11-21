import tempfile
import unittest
from pathlib import Path

from utils.explorer import target_folder


class ExplorerTargetTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_file_returns_parent(self):
        file_path = self.root / "audio.mp3"
        file_path.write_bytes(b"x")
        self.assertEqual(target_folder(file_path), self.root)

    def test_directory_returns_itself(self):
        self.assertEqual(target_folder(self.root), self.root)

    def test_missing_file_returns_existing_parent(self):
        self.assertEqual(target_folder(self.root / "gone.mp3"), self.root)

    def test_missing_parent_returns_none(self):
        missing = self.root / "no" / "such" / "file.mp3"
        self.assertIsNone(target_folder(missing))

    def test_empty_returns_none(self):
        self.assertIsNone(target_folder(None))
        self.assertIsNone(target_folder(""))


if __name__ == "__main__":
    unittest.main()
