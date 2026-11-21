import tempfile
import unittest
from pathlib import Path

from app.config import ConfigManager
from app.presets import PresetService


class PresetServiceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.config = ConfigManager(root / "conf" / "config.json")
        self.config.load()
        self.audio_dir = root / "preset_audio"
        self.service = PresetService(self.config, self.audio_dir)

    def tearDown(self):
        self._tmp.cleanup()

    def test_add_text_no_duplicates(self):
        self.assertTrue(self.service.add_text("你好"))
        self.assertFalse(self.service.add_text("你好"))
        self.assertEqual(self.service.text_presets, ["你好"])

    def test_rename_text_migrates_hotkey(self):
        self.service.add_text("旧文本")
        self.config.save({"text_hotkeys": {"旧文本": "ctrl+num1"}})

        self.assertTrue(self.service.rename_text("旧文本", "新文本"))

        self.assertEqual(self.service.text_presets, ["新文本"])
        hotkeys = self.config.get("text_hotkeys")
        self.assertNotIn("旧文本", hotkeys)
        self.assertEqual(hotkeys["新文本"], "ctrl+num1")

    def test_remove_text_clears_hotkey(self):
        self.service.add_text("待删除")
        self.config.save({"text_hotkeys": {"待删除": "alt+num2"}})
        self.assertTrue(self.service.remove_text("待删除"))
        self.assertEqual(self.service.text_presets, [])
        self.assertNotIn("待删除", self.config.get("text_hotkeys"))

    def test_audio_presets_prunes_dead_links(self):
        self.config.save({"linked_audio": {"gone.mp3": str(Path(self._tmp.name) / "gone.mp3")}})
        self.assertEqual(self.service.audio_presets(), {})
        self.assertNotIn("gone.mp3", self.config.get("linked_audio"))

    def test_import_copy_and_link(self):
        source = Path(self._tmp.name) / "sample.mp3"
        source.write_bytes(b"audio")

        self.assertEqual(self.service.import_audio([str(source)], copy_files=True), 1)
        self.assertTrue((self.audio_dir / "sample.mp3").exists())

        other = Path(self._tmp.name) / "linked.wav"
        other.write_bytes(b"wav")
        self.assertEqual(self.service.import_audio([str(other)], copy_files=False), 1)
        self.assertIn("linked.wav", self.config.get("linked_audio"))

        presets = self.service.audio_presets()
        self.assertIn("sample.mp3", presets)
        self.assertIn("linked.wav", presets)

    def test_remove_audio_unlink_does_not_delete_file(self):
        source = Path(self._tmp.name) / "outer.mp3"
        source.write_bytes(b"audio")
        self.config.save({"linked_audio": {"outer.mp3": str(source)}})

        self.assertEqual(self.service.remove_audio("outer.mp3", str(source)), "unlinked")
        self.assertTrue(source.exists())


if __name__ == "__main__":
    unittest.main()
