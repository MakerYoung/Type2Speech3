# utils/config_manager.py
import json
from pathlib import Path
import logging

class ConfigManager:
    def __init__(self, config_path: str = "conf/config.json"):
        self.config_file = Path(config_path)
        # 预设默认配置，防止首次运行或文件损坏时报错
        self.config = {
            "last_device_name": None,
            "presets_text": {},
            "presets_audio": {},
            "last_engine": "PyTTSX3",
            "last_voice_id": None,
            "rate": "+10%",
            "games": ["Counter-Strike 2"]
        }

    def load(self) -> dict:
        """加载配置文件，如果不存在则返回默认配置"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                    # 更新默认字典，确保缺失的键也能保留默认值
                    self.config.update(loaded_config)
            except Exception as e:
                logging.info(f"配置加载错误，将使用默认配置: {e}")
        return self.config

    def save(self, new_data: dict):
        """更新并保存配置"""
        self.config.update(new_data)
        # 确保目录存在
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logging.info(f"保存配置失败: {e}")

    def get(self, key, default=None):
        """便捷获取单个配置项"""
        return self.config.get(key, default)