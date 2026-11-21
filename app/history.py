# app/history.py
"""历史记录模型与存储。"""

import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

from app.jsonio import read_json, write_json_atomic


@dataclass
class HistoryRecord:
    text: str = ""
    path: str = ""
    rate: str = ""
    engine: str = ""
    voice_id: str = ""
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "HistoryRecord":
        data = data if isinstance(data, dict) else {}
        known = {"text", "path", "rate", "engine", "voice_engine", "voice_id"}
        return cls(
            text=str(data.get("text", "")),
            path=str(data.get("path", "")),
            rate=str(data.get("rate", "")),
            engine=str(data.get("engine", data.get("voice_engine", ""))),
            voice_id=str(data.get("voice_id", "")),
            extra={k: v for k, v in data.items() if k not in known},
        )

    def to_dict(self) -> dict:
        data = asdict(self)
        extra = data.pop("extra", {}) or {}
        # 保持旧字段名 voice_engine，兼容已有 history.json
        data["voice_engine"] = data.pop("engine")
        return {**data, **extra}


class HistoryStore:
    def __init__(self, history_file: Path | str):
        self.history_file = Path(history_file)
        self.records: list[HistoryRecord] = []

    def load(self) -> list[HistoryRecord]:
        raw = read_json(self.history_file, [])
        if not isinstance(raw, list):
            raw = []
        self.records = [HistoryRecord.from_dict(item) for item in raw]
        return self.records

    def save(self) -> bool:
        return write_json_atomic(self.history_file, [r.to_dict() for r in self.records])

    def add(self, record: HistoryRecord) -> None:
        self.records.append(record)
        self.save()

    def remove(self, record: HistoryRecord) -> None:
        try:
            self.records.remove(record)
        except ValueError:
            return
        self.save()

    def find(self, text: str, rate: str, engine: str, voice_id: str) -> HistoryRecord | None:
        for record in self.records:
            if (
                record.text == text
                and record.rate == rate
                and record.engine == engine
                and record.voice_id == voice_id
            ):
                return record
        return None

    def clear_all(self) -> tuple[int, int]:
        """清空记录并删除关联音频，返回 (成功, 失败)。"""
        deleted = failed = 0
        for record in self.records:
            if not record.path:
                continue
            file_path = Path(record.path)
            if not file_path.exists():
                continue
            try:
                file_path.unlink()
                deleted += 1
            except OSError:
                failed += 1
        self.records = []
        self.save()
        return deleted, failed

    def clear_non_presets(self, keep_texts: set[str]) -> tuple[int, int]:
        """删除不在文本预设白名单中的历史记录及文件。"""
        kept: list[HistoryRecord] = []
        removed = deleted = 0
        for record in self.records:
            if record.text in keep_texts:
                kept.append(record)
                continue
            removed += 1
            if record.path and Path(record.path).exists():
                try:
                    Path(record.path).unlink()
                    deleted += 1
                except OSError as exc:
                    logging.error("删除历史音频失败 %s: %s", record.path, exc)
        if removed:
            self.records = kept
            self.save()
        return removed, deleted
