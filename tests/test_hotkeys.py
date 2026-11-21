import tempfile
import unittest
from pathlib import Path

from app.config import ConfigManager
from app.hotkeys import HotkeyRegistry, make_action_id
from utils.hotkey_manager import MOD_CONTROL, parse_hotkey_string


class HotkeyRegistryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.config = ConfigManager(Path(self._tmp.name) / "conf" / "config.json")
        self.config.load()
        self.registry = HotkeyRegistry(self.config)

    def tearDown(self):
        self._tmp.cleanup()

    def test_current_key_and_set(self):
        action_id = make_action_id("text", "你好")
        self.assertEqual(self.registry.current_key(action_id), "")
        self.registry.set(action_id, "ctrl+num1")
        self.assertEqual(self.registry.current_key(action_id), "ctrl+num1")
        persisted = ConfigManager(self.config.config_file).load()
        self.assertEqual(persisted["text_hotkeys"]["你好"], "ctrl+num1")

        self.registry.set(action_id, "")
        self.assertEqual(self.registry.current_key(action_id), "")

    def test_find_conflict_across_categories(self):
        self.registry.set("sys_stop_play", "ctrl+num0")
        conflict = self.registry.find_conflict("ctrl+num0", "text_abc")
        self.assertEqual(conflict, "sys_stop_play")
        self.assertIsNone(self.registry.find_conflict("ctrl+num0", "sys_stop_play"))

    def test_clear_prefix(self):
        self.registry.set("text_a", "ctrl+num1")
        self.registry.set("text_b", "ctrl+num2")
        self.registry.set("audio_x.mp3", "alt+num1")
        self.assertEqual(self.registry.clear_prefix("text_"), 2)
        self.assertEqual(self.registry.text_hotkeys, {})
        self.assertEqual(self.registry.audio_hotkeys, {"x.mp3": "alt+num1"})


class ParseHotkeyTests(unittest.TestCase):
    def test_parse(self):
        mod, vk = parse_hotkey_string("ctrl+num1")
        self.assertEqual(mod, MOD_CONTROL)
        self.assertEqual(vk, 0x61)

    def test_parse_pageup(self):
        _, vk = parse_hotkey_string("pagedown")
        self.assertEqual(vk, 0x22)
        _, vk = parse_hotkey_string("pageup")
        self.assertEqual(vk, 0x21)

    def test_invalid_part(self):
        self.assertEqual(parse_hotkey_string("ctrl+unknown"), (0, 0))


if __name__ == "__main__":
    unittest.main()
