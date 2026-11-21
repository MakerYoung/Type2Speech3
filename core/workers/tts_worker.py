
# tts_worker.py
import os
import time
import threading
import soundfile as sf
import sounddevice as sd
from PyQt5.QtCore import QObject, QRunnable, pyqtSignal
from core.engines.tts_engine import TTSEngine
from utils.hotkey_manager import HotkeyManager
from utils.keyboard_injector import KeyboardInjector
import logging

class TTSWorker(QRunnable):
    """
    Runnable 类用于在 QThreadPool 中执行 TTS 转换和播放任务。
    采用 sounddevice 根据传入的 device_index 实现精准设备路由。
    """
    # 严格保证同一时刻只有 1 个线程能操作键盘和声卡
    _hardware_lock = threading.Lock()

    class WorkerSignals(QObject):
        finished_signal = pyqtSignal(str, str)  # 文本, 音频文件路径
        error_signal = pyqtSignal(str)          # 错误信息

    def __init__(self, rate, text, device_index, filename, tts_engine: TTSEngine, is_history_play=False):
        super().__init__()
        self.signals = self.WorkerSignals()

        self.text = text
        self.device_index = device_index  # 【保留】：接收来自 UI 的设备索引
        self.filename = filename
        self.is_history_play = is_history_play
        self.tts_engine = tts_engine
        self.rate = rate
        self.window_name = "Counter-Strike 2"

        self.is_stopped = False
        self.preset_audio_volume = 1.0
        self.tts_volume = 1.0

        # 游戏内开麦控制
        self.open_game_mic = True
        self.speak_key = 'pagedown'
        self.hotkey_manager = HotkeyManager()

    def run(self):
        try:
            # 1. 耗时的文本转语音不加锁，允许后台并发生成
            if not self.is_history_play:
                self.tts_engine.generate_speech(self.text, self.filename, self.rate)

            # 如果生成中途被掐断，直接退出
            if self.is_stopped:
                return

            if not os.path.exists(self.filename) or os.path.getsize(self.filename) == 0:
                raise RuntimeError(f"语音合成失败：音频文件 {self.filename} 为空或未创建。")

            # ==========================================
            # 【核心区：加锁！】严格防止多线程抢占声卡和热键
            # ==========================================
            with self._hardware_lock:
                if self.is_stopped:
                    return

                logging.info(f"DEBUG: TTS Worker 准备播放文件：{self.filename} (设备索引: {self.device_index})")

                # 每次播放前，主动清空一下底层的音频缓冲区，防止前一个声音残音
                sd.stop()

                if self.open_game_mic:
                    logging.info("开麦播放，游戏内可听见")
                    try:
                        KeyboardInjector.v_press(self.speak_key)

                        if self._interruptible_sleep(0.1):
                            self._play_audio_file(self.filename, self.device_index)

                        if not self.is_stopped:
                            self._interruptible_sleep(0.1)
                    finally:
                        # 核心保障：只要进来了，出去时必定松开按键，绝不卡键！
                        KeyboardInjector.v_release(self.speak_key)
                else:
                    logging.info("闭麦播放，游戏内不可听见")
                    self._play_audio_file(self.filename, self.device_index)

            # 锁释放后，发送完成信号
            if not self.is_stopped:
                self.signals.finished_signal.emit(self.text, self.filename)
                logging.info('DEBUG: TTS Worker finished!')

        except Exception as e:
            error_msg = f"处理失败: {e}"
            logging.error(f"DEBUG: Error in tts_worker: {error_msg}")
            self.signals.error_signal.emit(error_msg)

    def _play_audio_file(self, filename, device_index):
        """
        使用 sounddevice 根据指定设备索引播放音频
        """

        try:
            # 读取音频数据
            data, sample_rate = sf.read(filename, always_2d=True)

            # 区分预设音频和 TTS 语音的音量
            parent_folder = os.path.basename(os.path.dirname(os.path.abspath(filename)))
            if parent_folder == 'preset_audio':
                data = data * self.preset_audio_volume
            else:
                data = data * self.tts_volume

            duration = len(data) / sample_rate

            # 【核心保留】：将音频流推送到用户在 UI 选中的具体设备索引
            sd.play(data, sample_rate, device=device_index)
            start_time = time.time()

            # 基于时长的安全轮询，支持随时打断
            try:
                while time.time() - start_time < duration:
                    if self.is_stopped:
                        sd.stop()  # 瞬间掐断声卡输出
                        logging.info("DEBUG: 播放已被用户中断。")
                        return False
                    time.sleep(0.05)  # 50ms 检查一次，降低 CPU 轮询占用
            except Exception as e:
                logging.info(f"DEBUG: 尝试停止播放时发生异常: {e}")

            # 确保音频流干净地结束
            sd.wait()
            logging.info("DEBUG: 播放顺利完成。")
            return True

        except Exception as e:
            logging.error(f"播放音频时出错: {e}")
            raise RuntimeError(f"播放音频失败: {e}")

    def _interruptible_sleep(self, duration):
        """支持随时打断的毫秒级休眠"""
        start_time = time.time()
        while time.time() - start_time < duration:
            if self.is_stopped:
                return False
            time.sleep(0.01)
        return True

    # ================= 属性设置 =================
    def set_preset_audio_volume(self, volume):
        self.preset_audio_volume = float(volume)

    def set_tts_volume(self, volume):
        self.tts_volume = float(volume)

    def stop(self):
        self.is_stopped = True

    def set_open_game_mic(self, open_game_mic):
        self.open_game_mic = open_game_mic

    def set_speak_key(self, key):
        self.speak_key = key