# core/workers/voice_loader_worker.py

import logging

from PyQt5.QtCore import QObject, QRunnable, pyqtSignal

from core.engines.tts_engine import TTSEngine


class VoiceLoaderSignals(QObject):
    finished = pyqtSignal(int, list)  # request_id, voices
    error = pyqtSignal(int, str)      # request_id, message


class VoiceLoaderWorker(QRunnable):
    """在后台线程加载音色；request_id 用于丢弃过期的加载结果。"""

    def __init__(self, engine: TTSEngine, request_id: int = 0):
        super().__init__()
        self.signals = VoiceLoaderSignals()
        self.engine = engine
        self.request_id = request_id
        self.setAutoDelete(True)

    def run(self):
        try:
            voices = self.engine.get_supported_voices()
            self.signals.finished.emit(self.request_id, voices)
        except Exception as exc:
            logging.error("加载 %s 音色失败: %s", self.engine.name, exc)
            self.signals.error.emit(self.request_id, f"加载 {self.engine.name} 音色失败: {exc}")
