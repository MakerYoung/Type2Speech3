import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.paths import DataPaths


class DataPathsTests(unittest.TestCase):
    def test_migrates_legacy_config_and_preset_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "legacy"
            (base / "conf").mkdir(parents=True)
            (base / "conf" / "config.json").write_text(
                json.dumps({"rate": "+40%"}), encoding="utf-8"
            )
            (base / "conf" / "history.json").write_text("[]", encoding="utf-8")
            (base / "preset_audio").mkdir()
            (base / "preset_audio" / "clip.mp3").write_bytes(b"fake")

            paths = DataPaths(Path(tmp) / "data")
            with mock.patch.object(DataPaths, "legacy_bases", return_value=[base]):
                self.assertTrue(paths.migrate_if_needed())

            self.assertTrue(paths.config_file.exists())
            self.assertTrue(paths.history_file.exists())
            self.assertTrue((paths.preset_audio_dir / "clip.mp3").exists())

    def test_migration_is_one_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "legacy"
            (base / "conf").mkdir(parents=True)
            (base / "conf" / "config.json").write_text("{}", encoding="utf-8")
            paths = DataPaths(Path(tmp) / "data")
            with mock.patch.object(DataPaths, "legacy_bases", return_value=[base]):
                self.assertTrue(paths.migrate_if_needed())
                self.assertFalse(paths.migrate_if_needed())

    def test_ensure_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = DataPaths(Path(tmp) / "data")
            paths.ensure_dirs()
            self.assertTrue(paths.conf_dir.is_dir())
            self.assertTrue(paths.audios_dir.is_dir())
            self.assertTrue(paths.preset_audio_dir.is_dir())


if __name__ == "__main__":
    unittest.main()
