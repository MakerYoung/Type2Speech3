# core/engines/pyttsx3_engine.py
import logging

import pyttsx3

from core.engines.tts_engine import TTSEngine, TTSEngineError, parse_rate_multiplier


class PyTTSX3Engine(TTSEngine):
    """本地 SAPI5 TTS 引擎。"""

    file_suffix = ".wav"
    supports_rate = True

    @property
    def name(self):
        return 'PyTTSX3 (本地)'

    def get_supported_voices(self):
        engine = None
        try:
            engine = pyttsx3.init()
            voices = engine.getProperty('voices')
            return [{"id": v.id, "name": v.name} for v in voices]
        except Exception as exc:
            logging.error("PyTTSX3 获取音色失败: %s", exc)
            return []
        finally:
            if engine is not None:
                try:
                    engine.stop()
                except Exception:
                    pass

    def generate_speech(self, text: str, output_path: str, rate: str):
        engine = None
        try:
            engine = pyttsx3.init()
            if self.voice_id:
                engine.setProperty('voice', self.voice_id)
            if rate:
                # pyttsx3/SAPI5 的 rate 单位是 words-per-minute，默认 200
                wpm = int(round(200 * parse_rate_multiplier(rate)))
                engine.setProperty('rate', max(50, min(600, wpm)))
            engine.save_to_file(text, output_path)
            engine.runAndWait()
        except Exception as exc:
            raise TTSEngineError(f"本地语音合成失败: {exc}") from exc
        finally:
            if engine is not None:
                try:
                    engine.stop()
                except Exception:
                    pass
