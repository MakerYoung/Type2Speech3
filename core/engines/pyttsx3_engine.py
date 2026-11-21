# pyttsx3_engine.py
import pyttsx3
from core.engines.tts_engine import TTSEngine
import logging

class PyTTSX3Engine(TTSEngine):
    """
    使用 pyttsx3 库实现本地 TTS 转换的引擎。
    """

    @property
    def name(self):
        return 'PyTTSX3 (本地)'

    def get_supported_voices(self):
        """返回 pyttsx3 支持的音色列表"""
        try:
            logging.info(f'pyttsx3 开始获取音色')
            engine = pyttsx3.init()
            voices = engine.getProperty('voices')
            # 释放引擎资源
            del engine

            voice_list = []
            for v in voices:
                # v.name 通常包含语言和性别信息，例如 'Microsoft David Desktop - English (United States)'
                display_name = f"{v.name}"

                voice_list.append({"id": v.id, "name": display_name})

            return voice_list
        except Exception as e:
            logging.info(f"PyTTSX3 初始化或获取音色失败: {e}")
            return []

    def generate_speech(self, text: str, output_path: str, rate:str):
        """
        使用 pyttsx3 将文本保存为 WAV 文件。
        注意：pyttsx3 可能会将 WAV 文件保存到临时位置再移动，
        因此 runAndWait 必须在 save_to_file 之后调用。
        """
        engine = pyttsx3.init()

        if self.voice_id:
            engine.setProperty('voice', self.voice_id)

        # 注意：此方法在 runAndWait() 执行时才真正完成文件写入
        engine.save_to_file(text, output_path)
        engine.runAndWait()

        # 释放引擎资源
        del engine