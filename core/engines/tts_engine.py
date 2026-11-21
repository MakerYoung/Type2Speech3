# core/engines/tts_engine.py
"""TTS 引擎抽象接口。"""

from abc import ABC, abstractmethod


class TTSEngineError(RuntimeError):
    """引擎层的统一异常，UI 可以直接展示其信息。"""


def parse_rate_multiplier(rate) -> float:
    """把 '+50%' / '-20%' / '1.5' 统一转换成倍率。"""
    if rate is None:
        return 1.0
    text = str(rate).strip()
    if not text:
        return 1.0
    try:
        if text.endswith('%'):
            return max(0.1, 1.0 + float(text[:-1]) / 100.0)
        return max(0.1, float(text))
    except ValueError:
        return 1.0


class TTSEngine(ABC):
    #: 生成文件的默认后缀（EdgeTTS 实际输出 mp3）
    file_suffix = ".wav"
    #: 是否支持 rate 参数
    supports_rate = False

    def __init__(self, voice_id=None):
        self.voice_id = voice_id

    @abstractmethod
    def get_supported_voices(self) -> list[dict]:
        """返回 [{"id": "...", "name": "..."}]。"""

    @abstractmethod
    def generate_speech(self, text: str, output_path: str, rate: str):
        """合成语音并写入 output_path。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """引擎显示名称。"""

    def set_voice(self, voice_id: str):
        self.voice_id = voice_id

    def spawn(self, voice_id=None) -> "TTSEngine":
        """创建一个只用于本次合成的独立实例，避免多线程共享 voice_id。"""
        return type(self)(voice_id if voice_id is not None else self.voice_id)
