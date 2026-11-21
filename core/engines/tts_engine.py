# tts_engine.py
from abc import ABC, abstractmethod

class TTSEngine(ABC):
    """
    TTS 引擎的抽象基类，定义了所有具体引擎必须实现的方法。
    """
    def __init__(self, voice_id=None):
        self.voice_id = voice_id

    @abstractmethod
    def get_supported_voices(self):
        """返回支持的音色列表，格式为 [{"id": "...", "name": "..."}]"""
        pass

    @abstractmethod
    def generate_speech(self, text: str, output_path: str, rate:str):
        """
        将文本合成语音并保存到指定路径。
        :param rate: 语音速率
        :param text: 要合成的文本。
        :param output_path: WAV 文件保存路径。
        """
        pass

    def set_voice(self, voice_id: str):
        """设置当前使用的音色ID"""
        self.voice_id = voice_id

    @property
    @abstractmethod
    def name(self):
        """返回引擎的名称 (例如: 'PyTTSX3', 'EdgeTTS', 'OnlineAPI')"""
        pass