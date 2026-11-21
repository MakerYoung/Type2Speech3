# app/presets.py
"""文本预设 / 音频预设的业务逻辑。"""

import logging
import shutil
from pathlib import Path

from app.config import ConfigManager
from app.paths import AUDIO_EXTENSIONS


class PresetService:
    def __init__(self, config: ConfigManager, preset_audio_dir: Path | str):
        self.config = config
        self.preset_audio_dir = Path(preset_audio_dir)
        self.preset_audio_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 文本预设
    # ------------------------------------------------------------------
    @property
    def text_presets(self) -> list[str]:
        return self.config.get("presets_text", [])

    def add_text(self, text: str) -> bool:
        text = text.strip()
        if not text or text in self.text_presets:
            return False
        self.text_presets.insert(0, text)
        self.config.save({"presets_text": self.text_presets})
        return True

    def rename_text(self, old_text: str, new_text: str) -> bool:
        new_text = new_text.strip()
        if not new_text or new_text == old_text:
            return False

        presets = self.text_presets
        if old_text in presets:
            presets[presets.index(old_text)] = new_text
        else:
            presets.append(new_text)

        text_hotkeys = dict(self.config.get("text_hotkeys", {}))
        if old_text in text_hotkeys:
            text_hotkeys[new_text] = text_hotkeys.pop(old_text)

        self.config.save({"presets_text": presets, "text_hotkeys": text_hotkeys})
        return True

    def remove_text(self, text: str) -> bool:
        presets = self.text_presets
        if text not in presets:
            return False
        presets.remove(text)
        text_hotkeys = dict(self.config.get("text_hotkeys", {}))
        text_hotkeys.pop(text, None)
        self.config.save({"presets_text": presets, "text_hotkeys": text_hotkeys})
        return True

    # ------------------------------------------------------------------
    # 音频预设
    # ------------------------------------------------------------------
    @property
    def linked_audio(self) -> dict[str, str]:
        return self.config.get("linked_audio", {})

    def audio_presets(self) -> dict[str, str]:
        """扫描内置音频目录，合并外部引用，并清理失效引用。"""
        presets: dict[str, str] = {}
        if self.preset_audio_dir.is_dir():
            for item in self.preset_audio_dir.iterdir():
                if item.is_file() and item.suffix.lower() in AUDIO_EXTENSIONS:
                    presets[item.name] = str(item.resolve())

        linked = dict(self.linked_audio)
        changed = False
        for name, path in list(linked.items()):
            if Path(path).exists():
                presets[name] = path
            else:
                linked.pop(name, None)
                changed = True
        if changed:
            self.config.save({"linked_audio": linked})
        return presets

    def import_audio(self, paths: list[str], copy_files: bool) -> int:
        """导入音频；copy_files=True 复制进软件目录，否则只记录外部路径。"""
        imported = 0
        for raw_path in paths:
            source = Path(raw_path)
            if not source.is_file():
                continue
            if copy_files:
                try:
                    shutil.copy2(source, self.preset_audio_dir / source.name)
                except OSError as exc:
                    logging.error("复制音频失败 %s: %s", source, exc)
                    continue
                linked = dict(self.linked_audio)
                if source.name in linked:
                    linked.pop(source.name, None)
                    self.config.save({"linked_audio": linked})
            else:
                linked = dict(self.linked_audio)
                linked[source.name] = str(source.resolve())
                self.config.save({"linked_audio": linked})
            imported += 1
        return imported

    def remove_audio(self, name: str, path: str) -> str:
        """移除音频预设，返回 'unlinked' / 'deleted' / 'missing' / 'failed'。"""
        audio_hotkeys = dict(self.config.get("audio_hotkeys", {}))
        had_hotkey = name in audio_hotkeys
        if had_hotkey:
            audio_hotkeys.pop(name, None)

        linked = dict(self.linked_audio)
        if name in linked:
            linked.pop(name, None)
            self.config.save({"linked_audio": linked, "audio_hotkeys": audio_hotkeys})
            return "unlinked"

        target = Path(path) if path else self.preset_audio_dir / name
        if not target.exists():
            if had_hotkey:
                self.config.save({"audio_hotkeys": audio_hotkeys})
            return "missing"
        try:
            target.unlink()
        except OSError as exc:
            logging.error("删除音频失败 %s: %s", target, exc)
            return "failed"
        if had_hotkey:
            self.config.save({"audio_hotkeys": audio_hotkeys})
        return "deleted"
