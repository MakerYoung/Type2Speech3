# app/jsonio.py
"""JSON 文件原子读写。"""

import json
import logging
import os
import tempfile
from pathlib import Path


def read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as exc:
        logging.error("读取 %s 失败: %s", path, exc)
        return default


def write_json_atomic(path: Path, data) -> bool:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_name = None
    try:
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{path.stem}-", suffix=".json", dir=str(path.parent)
        )
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
        return True
    except OSError as exc:
        logging.error("写入 %s 失败: %s", path, exc)
        return False
    finally:
        if tmp_name:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
