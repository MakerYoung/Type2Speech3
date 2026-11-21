# api_engine.py
from core.engines.tts_engine import TTSEngine


class OnlineAPIEngine(TTSEngine):
    """
    基于在线 API (例如 Google, Microsoft, Baidu) 的 TTS 引擎骨架。
    用户需自行实现 API 调用逻辑。
    """

    @property
    def name(self):
        return 'Online API (骨架)'

    def get_supported_voices(self):
        """
        返回支持的音色列表。
        TODO: 根据实际 API 实现，获取音色列表。
        """
        # 仅返回一个示例音色
        return [
            {"id": "api-voice-default", "name": "API 默认音色 (请配置)"}
        ]

    def generate_speech(self, text: str, output_path: str):
        """
        将文本通过在线 API 合成语音并保存到指定路径。
        TODO: 根据实际 API 实现，调用 API 并将返回的音频流写入 WAV 文件。
        """
        # 这是一个占位符实现，实际应用中应调用 API
        import time
        time.sleep(1)  # 模拟网络延迟

        # 抛出异常提醒用户实现
        raise NotImplementedError("OnlineAPIEngine 尚未实现。请配置您的 API 密钥和调用逻辑。")