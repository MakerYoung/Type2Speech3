# app/config.py
"""配置读写：单实例、带默认值校正、原子写入。"""

import copy
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

DEFAULT_SYS_HOTKEYS = {
    "sys_toggle_window": "ctrl+num_dot",
    "sys_stop_play": "ctrl+num0",
    "sys_toggle_mic": "ctrl+enter",
    "sys_repeat_play": "ctrl+num_add",
    "sys_float_window": "alt+num_dot",
}

DEFAULT_CONFIG: dict[str, Any] = {
    "last_device_name": None,
    "presets_text": [],
    "presets_audio": {},
    "linked_audio": {},
    "last_engine": "PyTTSX3",
    "last_voice_id": None,
    "rate": "+10%",
    "tts_volume": 1.0,
    "preset_audio_volume": 0.5,
    "speak_key": "pagedown",
    "games": [
        "Counter-Strike 2",
        "Counter-Strike",
        "VALORANT",
        "League of Legends",
        "LeagueClient",
        "Dota 2",
        "DOTA 2",
        "Overwatch",
        "Apex Legends",
        "Fortnite",
        "PUBG",
        "Rocket League",
    ],
    "auto_clear_history": False,
    "audio_hotkeys": {},
    "text_hotkeys": {},
    "sys_hotkeys": dict(DEFAULT_SYS_HOTKEYS),
}


def _as_dict(value: Any) -> dict:
    # 返回副本，避免配置与服务层共享同一个可变对象
    return dict(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, dict):
        # 旧版本默认值把 presets_text 写成了 {}，这里做兼容转换
        return list(value.keys())
    return []


def _clamp(value: Any, low: float, high: float, fallback: float) -> float:
    try:
        return max(low, min(high, float(value)))
    except (TypeError, ValueError):
        return fallback


class ConfigManager:
    def __init__(self, config_file: Path | str, defaults: dict | None = None):
        self.config_file = Path(config_file)
        self.defaults = copy.deepcopy(DEFAULT_CONFIG if defaults is None else defaults)
        self.config: dict[str, Any] = copy.deepcopy(self.defaults)

    # ------------------------------------------------------------------
    def load(self) -> dict:
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    self.config = self._normalize(loaded)
            except (OSError, ValueError) as exc:
                logging.error("配置加载失败，使用默认配置: %s", exc)
                self.config = dict(self.defaults)
        else:
            self.config = self._normalize({})
        return self.config

    def _normalize(self, loaded: dict) -> dict:
        merged = dict(self.defaults)
        merged.update(loaded)
        merged["presets_text"] = _as_list(merged.get("presets_text"))
        merged["presets_audio"] = _as_dict(merged.get("presets_audio"))
        merged["linked_audio"] = _as_dict(merged.get("linked_audio"))
        merged["audio_hotkeys"] = _as_dict(merged.get("audio_hotkeys"))
        merged["text_hotkeys"] = _as_dict(merged.get("text_hotkeys"))
        merged["sys_hotkeys"] = {**DEFAULT_SYS_HOTKEYS, **_as_dict(merged.get("sys_hotkeys"))}
        merged["games"] = _as_list(merged.get("games")) or list(self.defaults.get("games", []))
        merged["tts_volume"] = _clamp(merged.get("tts_volume"), 0.0, 1.0, 1.0)
        merged["preset_audio_volume"] = _clamp(
            merged.get("preset_audio_volume"), 0.0, 1.0, 0.5
        )
        merged["auto_clear_history"] = bool(merged.get("auto_clear_history", False))
        return merged

    # ------------------------------------------------------------------
    def get(self, key: str, default=None):
        return self.config.get(key, default)

    def set(self, key: str, value) -> None:
        self.config[key] = value
        self.save()

    def save(self, updates: dict | None = None) -> None:
        if updates:
            self.config.update(updates)

        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_name = None
        try:
            fd, tmp_name = tempfile.mkstemp(
                prefix=".config-", suffix=".json", dir=str(self.config_file.parent)
            )
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=4)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_name, self.config_file)
            tmp_name = None
        except OSError as exc:
            logging.error("保存配置失败: %s", exc)
        finally:
            if tmp_name:
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass
