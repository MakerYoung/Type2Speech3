# core/engines/api_engine.py
from core.engines.tts_engine import TTSEngine


class OnlineAPIEngine(TTSEngine):
    """第三方在线 API 引擎骨架，供二次开发。"""

    file_suffix = ".wav"
    supports_rate = False

    @property
    def name(self):
        return 'Online API (骨架)'

    def get_supported_voices(self):
        return [{"id": "api-voice-default", "name": "API 默认音色 (请配置)"}]

    def generate_speech(self, text: str, output_path: str, rate: str):
        raise NotImplementedError(
            "OnlineAPIEngine 尚未实现，请在此处接入你的语音 API。"
        )
