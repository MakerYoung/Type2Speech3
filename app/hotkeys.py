# app/hotkeys.py
"""热键数据管理与监听线程的生命周期。"""

import logging

from PyQt5.QtCore import QObject, pyqtSignal

from app.config import ConfigManager
from utils.hotkey_manager import HotkeyManager


def make_action_id(item_type: str, name: str) -> str:
    return f"{item_type}_{name}"


class HotkeyRegistry:
    """按 sys_ / audio_ / text_ 三类管理热键字典，并负责持久化。"""

    def __init__(self, config: ConfigManager):
        self.config = config

    @property
    def sys_hotkeys(self) -> dict:
        return self.config.get("sys_hotkeys", {})

    @property
    def audio_hotkeys(self) -> dict:
        return self.config.get("audio_hotkeys", {})

    @property
    def text_hotkeys(self) -> dict:
        return self.config.get("text_hotkeys", {})

    def current_key(self, action_id: str) -> str:
        prefix, name = self._split(action_id)
        mapping = {
            "sys": self.sys_hotkeys,
            "audio": self.audio_hotkeys,
            "text": self.text_hotkeys,
        }.get(prefix, {})
        return mapping.get(name, "")

    def set(self, action_id: str, hotkey: str) -> bool:
        prefix, name = self._split(action_id)
        if prefix == "sys":
            target, dict_name, key = self.sys_hotkeys, "sys_hotkeys", name
        elif prefix == "audio":
            target, dict_name, key = self.audio_hotkeys, "audio_hotkeys", name
        elif prefix == "text":
            target, dict_name, key = self.text_hotkeys, "text_hotkeys", name
        else:
            logging.error("未知的热键类型: %s", action_id)
            return False

        if hotkey:
            target[key] = hotkey
        else:
            target.pop(key, None)
        self.config.save({dict_name: target})
        return True

    def clear_prefix(self, prefix: str) -> int:
        if prefix == "text_":
            target, dict_name = self.text_hotkeys, "text_hotkeys"
        elif prefix == "audio_":
            target, dict_name = self.audio_hotkeys, "audio_hotkeys"
        else:
            logging.error("未知的批量清除前缀: %s", prefix)
            return 0
        count = len(target)
        if count:
            target.clear()
            self.config.save({dict_name: target})
        return count

    def find_conflict(self, hotkey: str, exclude_action_id: str) -> str | None:
        for prefix, mapping in (
            ("", self.sys_hotkeys),
            ("audio_", self.audio_hotkeys),
            ("text_", self.text_hotkeys),
        ):
            for name, key in mapping.items():
                action_id = f"{prefix}{name}"
                if key == hotkey and action_id != exclude_action_id:
                    return action_id
        return None

    def all_bindings(self) -> list[tuple[str, str]]:
        bindings = list(self.sys_hotkeys.items())
        bindings += [(f"audio_{k}", v) for k, v in self.audio_hotkeys.items()]
        bindings += [(f"text_{k}", v) for k, v in self.text_hotkeys.items()]
        return bindings

    @staticmethod
    def _split(action_id: str) -> tuple[str, str]:
        # 系统热键在配置里保存的就是完整 action_id（sys_...）
        if action_id.startswith("sys_"):
            return "sys", action_id
        if action_id.startswith("audio_"):
            return "audio", action_id[len("audio_"):]
        if action_id.startswith("text_"):
            return "text", action_id[len("text_"):]
        return "", action_id


class HotkeyService(QObject):
    """管理监听线程：每次配置变化时重建线程，确保注册发生在监听线程内。"""

    triggered = pyqtSignal(str)

    def __init__(self, registry: HotkeyRegistry, parent=None):
        super().__init__(parent)
        self.registry = registry
        self._manager: HotkeyManager | None = None

    def rebuild(self) -> None:
        self.stop()
        self._manager = HotkeyManager()
        self._manager.hotkey_triggered.connect(self.triggered.emit)
        for action_id, hotkey in self.registry.all_bindings():
            if hotkey:
                self._manager.register_hotkey(action_id, hotkey)
        self._manager.start()

    def stop(self) -> None:
        if self._manager is not None:
            self._manager.stop()
            self._manager = None
