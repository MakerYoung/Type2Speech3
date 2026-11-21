# voice_loader_worker.py

from PyQt5.QtCore import QObject, QRunnable, pyqtSignal
from core.engines.tts_engine import TTSEngine
import logging


class VoiceLoaderSignals(QObject):
    """用于音色加载Worker的信号"""
    finished = pyqtSignal(list)  # 成功时发送音色列表 [{"id": "...", "name": "..."}]
    error = pyqtSignal(str)  # 失败时发送错误信息


class VoiceLoaderWorker(QRunnable):
    """
    QRunnable 子类，用于在 QThreadPool 中异步加载 TTS 引擎的音色。
    这解决了 EdgeTTS (asyncio) 在主线程中阻塞和清理错误的问题。
    """

    def __init__(self, engine_instance: TTSEngine):
        super().__init__()
        self.signals = VoiceLoaderSignals()
        self.engine = engine_instance
        self.setAutoDelete(True)

    def run(self):
        try:
            # 在后台线程中同步调用耗时的音色获取方法
            voices = self.engine.get_supported_voices()

            # 操作成功，将结果发回主线程
            self.signals.finished.emit(voices)

        except Exception as e:
            # 捕获任何加载错误，包括 EdgeTTS 内部的失败
            error_msg = f"加载 {self.engine.name} 音色失败: {e}"
            logging.info(error_msg)
            self.signals.error.emit(error_msg)