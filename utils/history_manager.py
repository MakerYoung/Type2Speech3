# utils/history_manager.py
import json
import os
from pathlib import Path
import logging


class HistoryManager:
    def __init__(self, history_path: str = "conf/history.json"):
        self.history_file = Path(history_path)
        self.history_data = []

    def load(self) -> list:
        """加载历史记录"""
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    self.history_data = json.load(f)
            except Exception as e:
                logging.info(f"历史记录加载错误，将初始化为空: {e}")
                self.history_data = []
        return self.history_data

    def save(self):
        """保存当前历史记录到文件"""
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.history_data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logging.info(f"保存历史记录失败: {e}")

    def add_record(self, text: str, path: str, rate: str, engine_name: str, voice_id: str):
        """添加一条新记录并保存"""
        record = {
            "text": text,
            "path": path,
            "rate": rate,
            "voice_engine": engine_name,
            "voice_id": voice_id
        }
        self.history_data.append(record)
        self.save()

    def clear_all(self) -> tuple[int, int]:
        """
        清空历史记录并尝试删除实体音频文件
        返回: (成功删除的文件数, 删除失败的文件数)
        """
        deleted_count = 0
        failed_count = 0

        for record in self.history_data:
            if "path" in record:
                file_path = Path(record["path"])
                if file_path.exists():
                    try:
                        file_path.unlink()  # 等同于 os.remove()
                        deleted_count += 1
                    except OSError:
                        failed_count += 1

        self.history_data = []
        self.save()
        return deleted_count, failed_count