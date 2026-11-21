# app/paths.py
"""统一管理运行时路径，避免依赖当前工作目录。"""

import os
import shutil
import sys
from pathlib import Path

APP_NAME = "Type2Speech3"
DATA_DIR_ENV = "TYPE2SPEECH_DATA_DIR"

AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a", ".wma"}


def app_base_dir() -> Path:
    """程序自身所在目录：打包后为 exe 目录，源码运行为项目根目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_path(relative: str) -> Path:
    """读取随程序分发的资源（图标等）。"""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass) / relative
    return app_base_dir() / relative


class DataPaths:
    """用户数据目录（配置、历史、生成音频、预设音频）。

    默认放在 %APPDATA%\\Type2Speech3，避免重新打包时被清空；
    可通过环境变量 TYPE2SPEECH_DATA_DIR 覆盖。
    """

    def __init__(self, root: Path | str | None = None):
        self.root = Path(root) if root else self._default_root()
        self.conf_dir = self.root / "conf"
        self.config_file = self.conf_dir / "config.json"
        self.history_file = self.conf_dir / "history.json"
        self.audios_dir = self.root / "audios"
        self.preset_audio_dir = self.root / "preset_audio"

    @staticmethod
    def _default_root() -> Path:
        env_dir = os.environ.get(DATA_DIR_ENV)
        if env_dir:
            return Path(env_dir).expanduser()
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / APP_NAME
        return app_base_dir() / "userdata"

    def ensure_dirs(self) -> None:
        for directory in (self.conf_dir, self.audios_dir, self.preset_audio_dir):
            directory.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 旧版本数据迁移
    # ------------------------------------------------------------------
    @staticmethod
    def legacy_bases() -> list[Path]:
        """旧版本把 conf/、preset_audio/ 放在 exe 或当前工作目录旁边。"""
        bases = [app_base_dir()]
        if getattr(sys, "frozen", False):
            # 常见 PyInstaller 布局：dist/main/main.exe → dist → 项目根目录
            exe_dir = app_base_dir()
            bases.extend([exe_dir.parent, exe_dir.parent.parent])
        try:
            cwd = Path.cwd()
            if cwd not in bases:
                bases.append(cwd)
        except OSError:
            pass

        unique: list[Path] = []
        for base in bases:
            if base not in unique:
                unique.append(base)
        return unique

    def migrate_if_needed(self) -> bool:
        """首次运行到新数据目录时，从旧位置复制配置/历史/预设音频。

        只在目标配置不存在时迁移一次；返回是否发生了迁移。
        """
        self.ensure_dirs()
        if self.config_file.exists():
            return False

        for base in self.legacy_bases():
            legacy_config = base / "conf" / "config.json"
            if not legacy_config.is_file():
                continue

            try:
                shutil.copy2(legacy_config, self.config_file)
                legacy_history = base / "conf" / "history.json"
                if legacy_history.is_file() and not self.history_file.exists():
                    shutil.copy2(legacy_history, self.history_file)
            except OSError:
                continue

            self._migrate_preset_audio(base / "preset_audio")
            return True

        # 没有配置文件，但可能只有预设音频
        for base in self.legacy_bases():
            legacy_audio = base / "preset_audio"
            if legacy_audio.is_dir() and any(legacy_audio.iterdir()):
                self._migrate_preset_audio(legacy_audio)
                break
        return False

    def _migrate_preset_audio(self, source: Path) -> None:
        if not source.is_dir():
            return
        for item in source.iterdir():
            if not item.is_file() or item.suffix.lower() not in AUDIO_EXTENSIONS:
                continue
            target = self.preset_audio_dir / item.name
            if target.exists():
                continue
            try:
                shutil.copy2(item, target)
            except OSError:
                continue
