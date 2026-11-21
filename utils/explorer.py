# utils/explorer.py
"""在资源管理器中定位文件或打开文件夹（Windows）。"""

import logging
import os
import subprocess
from pathlib import Path


def target_folder(path: str | Path | None) -> Path | None:
    """返回用于打开/定位的目录；无法确定时返回 None。"""
    if not path:
        return None
    target = Path(path)
    if target.is_file():
        return target.parent
    if target.is_dir():
        return target
    parent = target.parent
    return parent if parent.is_dir() else None


def reveal_in_explorer(path: str | Path | None) -> bool:
    """文件存在则选中它；否则打开其所在文件夹。"""
    if not path:
        return False
    target = Path(path)
    try:
        if target.exists():
            subprocess.Popen(["explorer", f"/select,{target}"])
            return True
        folder = target_folder(target)
        if folder is not None:
            os.startfile(str(folder))
            return True
    except OSError as exc:
        logging.error("打开资源管理器失败 %s: %s", target, exc)
    return False
