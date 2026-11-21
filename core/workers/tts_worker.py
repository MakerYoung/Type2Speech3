# core/workers/tts_worker.py
"""单个语音任务的合成 + 播放 Worker。"""

import logging
import os
import threading
import time

import sounddevice as sd
import soundfile as sf
from PyQt5.QtCore import QObject, QRunnable, pyqtSignal

from core.engines.tts_engine import TTSEngine
from utils.keyboard_injector import KeyboardInjector


class TTSWorker(QRunnable):
    """在 QThreadPool 中执行：生成音频（可选）→ 输出到指定设备。"""

    # 严格保证同一时刻只有一个线程操作声卡和开麦按键
    _hardware_lock = threading.Lock()

    class WorkerSignals(QObject):
        finished_signal = pyqtSignal(str, str)  # 文本, 音频路径
        error_signal = pyqtSignal(str)
        stopped_signal = pyqtSignal()

    def __init__(
        self,
        rate: str,
        text: str,
        device_index: int,
        filename: str,
        tts_engine: TTSEngine | None,
        volume: float = 1.0,
        open_game_mic: bool = False,
        speak_key: str = "pagedown",
        is_history_play: bool = False,
    ):
        super().__init__()
        self.signals = self.WorkerSignals()
        self.text = text
        self.device_index = device_index
        self.filename = filename
        self.is_history_play = is_history_play
        self.tts_engine = tts_engine
        self.rate = rate
        self.volume = float(volume)
        self.open_game_mic = open_game_mic
        self.speak_key = speak_key
        self.is_stopped = False
        self.setAutoDelete(True)

    def run(self):
        try:
            if self.is_stopped:
                return
            if not self.is_history_play:
                self.tts_engine.generate_speech(self.text, self.filename, self.rate)

            if self.is_stopped:
                return

            if not os.path.exists(self.filename) or os.path.getsize(self.filename) == 0:
                raise RuntimeError(f"语音合成失败：音频文件为空或未创建 ({self.filename})")

            with self._hardware_lock:
                if self.is_stopped:
                    return
                sd.stop()
                if self.open_game_mic:
                    self._play_with_mic_key()
                else:
                    self._play_audio_file()

            if not self.is_stopped:
                self.signals.finished_signal.emit(self.text, self.filename)
        except Exception as exc:
            if not self.is_stopped:
                logging.error("TTS 任务失败: %s", exc)
                self.signals.error_signal.emit(f"处理失败: {exc}")
        finally:
            if self.is_stopped:
                self.signals.stopped_signal.emit()

    def _play_with_mic_key(self):
        try:
            KeyboardInjector.v_press(self.speak_key)
            if self._interruptible_sleep(0.1):
                self._play_audio_file()
            if not self.is_stopped:
                self._interruptible_sleep(0.1)
        finally:
            KeyboardInjector.v_release(self.speak_key)

    def _play_audio_file(self):
        try:
            data, sample_rate = sf.read(self.filename, always_2d=True)
        except Exception as exc:
            raise RuntimeError(f"读取音频失败: {exc}") from exc

        if self.volume != 1.0:
            data = data * self.volume

        duration = len(data) / sample_rate
        sd.play(data, sample_rate, device=self.device_index)
        start_time = time.time()
        while time.time() - start_time < duration:
            if self.is_stopped:
                sd.stop()
                return
            time.sleep(0.05)
        sd.wait()

    def _interruptible_sleep(self, duration: float) -> bool:
        start_time = time.time()
        while time.time() - start_time < duration:
            if self.is_stopped:
                return False
            time.sleep(0.01)
        return True

    def stop(self):
        self.is_stopped = True
