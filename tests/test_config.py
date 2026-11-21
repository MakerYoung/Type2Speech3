import json
import tempfile
import unittest
from pathlib import Path

from app.config import ConfigManager


class ConfigManagerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "conf" / "config.json"

    def tearDown(self):
        self._tmp.cleanup()

    def test_defaults_presets_text_is_list(self):
        config = ConfigManager(self.path).load()
        self.assertEqual(config["presets_text"], [])
        self.assertIsInstance(config["sys_hotkeys"], dict)

    def test_legacy_dict_presets_are_coerced(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(
            json.dumps({"presets_text": {"旧预设": 1}, "tts_volume": 3}),
            encoding="utf-8",
        )
        config = ConfigManager(self.path).load()
        self.assertEqual(config["presets_text"], ["旧预设"])
        self.assertEqual(config["tts_volume"], 1.0)

    def test_save_and_reload(self):
        manager = ConfigManager(self.path)
        manager.load()
        manager.save({"rate": "+50%", "presets_text": ["a"]})

        reloaded = ConfigManager(self.path).load()
        self.assertEqual(reloaded["rate"], "+50%")
        self.assertEqual(reloaded["presets_text"], ["a"])
        self.assertTrue(self.path.exists())
        self.assertFalse((self.path.parent / ".config-x.json").exists())

    def test_corrupt_file_falls_back_to_defaults(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{not json", encoding="utf-8")
        config = ConfigManager(self.path).load()
        self.assertEqual(config["presets_text"], [])
        self.assertEqual(config["last_engine"], "PyTTSX3")


if __name__ == "__main__":
    unittest.main()
