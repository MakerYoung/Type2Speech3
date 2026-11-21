# app/playback.py
"""播放/合成任务调度。

同一时刻只跟踪一个“当前任务”；旧任务即使晚到完成信号也会被丢弃。
停止操作会立即释放 UI 的 busy 状态，不必等待后台合成结束。
"""

import logging

from PyQt5.QtCore import QObject, QThreadPool, pyqtSignal

from app.history import HistoryRecord
from core.engines.tts_engine import TTSEngine
from core.workers.tts_worker import TTSWorker


class PlaybackController(QObject):
    busy_changed = pyqtSignal(bool)
    error = pyqtSignal(str)
    converted = pyqtSignal(object)  # HistoryRecord
    played = pyqtSignal(str)        # 文件路径

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(4)
        self._seq = 0
        self._current_id: int | None = None
        self._worker: TTSWorker | None = None
        self._busy = False

    # ------------------------------------------------------------------
    def speak(
        self,
        *,
        text: str,
        engine: TTSEngine,
        voice_id: str | None,
        rate: str,
        output_path: str,
        device_index: int,
        volume: float,
        open_game_mic: bool,
        speak_key: str,
    ) -> bool:
        worker = TTSWorker(
            rate=rate,
            text=text,
            device_index=device_index,
            filename=output_path,
            tts_engine=engine.spawn(voice_id),
            volume=volume,
            open_game_mic=open_game_mic,
            speak_key=speak_key,
            is_history_play=False,
        )
        meta = {
            "text": text,
            "path": output_path,
            "rate": rate,
            "engine": engine.name,
            "voice_id": voice_id or "",
        }
        return self._start(worker, meta)

    def play_file(
        self,
        *,
        path: str,
        device_index: int,
        volume: float,
        open_game_mic: bool,
        speak_key: str,
    ) -> bool:
        worker = TTSWorker(
            rate="",
            text="",
            device_index=device_index,
            filename=path,
            tts_engine=None,
            volume=volume,
            open_game_mic=open_game_mic,
            speak_key=speak_key,
            is_history_play=True,
        )
        return self._start(worker, None)

    def stop(self) -> None:
        worker = self._worker
        if worker is not None:
            worker.stop()
            self._worker = None
        if self._current_id is not None:
            self._current_id = None
            self._set_busy(False)

    def shutdown(self) -> None:
        self.stop()
        self._pool.waitForDone(2000)

    def is_busy(self) -> bool:
        return self._busy

    # ------------------------------------------------------------------
    def _start(self, worker: TTSWorker, meta: dict | None) -> bool:
        self.stop()
        self._seq += 1
        seq = self._seq
        self._current_id = seq
        self._worker = worker

        worker.signals.finished_signal.connect(
            lambda text, path: self._on_finished(seq, meta, text, path)
        )
        worker.signals.error_signal.connect(lambda msg: self._on_error(seq, msg))
        worker.signals.stopped_signal.connect(lambda: self._on_stopped(seq))

        self._set_busy(True)
        self._pool.start(worker)
        return True

    def _on_finished(self, seq: int, meta: dict | None, text: str, path: str) -> None:
        if seq != self._current_id:
            return
        self._clear_current()
        if meta is None:
            self.played.emit(path)
            return
        record = HistoryRecord(
            text=meta.get("text", text),
            path=path,
            rate=meta.get("rate", ""),
            engine=meta.get("engine", ""),
            voice_id=meta.get("voice_id", ""),
        )
        self.converted.emit(record)

    def _on_error(self, seq: int, message: str) -> None:
        if seq != self._current_id:
            return
        self._clear_current()
        logging.error("播放任务错误: %s", message)
        self.error.emit(message)

    def _on_stopped(self, seq: int) -> None:
        if seq != self._current_id:
            return
        self._clear_current()

    def _clear_current(self) -> None:
        self._current_id = None
        self._worker = None
        self._set_busy(False)

    def _set_busy(self, busy: bool) -> None:
        if busy == self._busy:
            return
        self._busy = busy
        self.busy_changed.emit(busy)
