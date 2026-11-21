# ui/main_window.py
"""主窗口：只负责界面构建与信号绑定，业务逻辑在 app/ 服务层。"""

import logging
import time
import uuid
from pathlib import Path

from PyQt5.QtCore import Qt, QEvent, QThreadPool, QTimer, QPropertyAnimation
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog,
    QGraphicsOpacityEffect, QHBoxLayout, QInputDialog, QLabel,
    QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox,
    QPushButton, QSplitter, QTextEdit, QVBoxLayout, QWidget,
)

from app.config import ConfigManager
from app.history import HistoryRecord, HistoryStore
from app.hotkeys import HotkeyRegistry, HotkeyService, make_action_id
from app.paths import DataPaths, resource_path
from app.playback import PlaybackController
from app.presets import PresetService
from core.audio_manager import AudioManager
from core.engines.api_engine import OnlineAPIEngine
from core.engines.edge_tts_engine import EdgeTTSEngine
from core.engines.pyttsx3_engine import PyTTSX3Engine
from core.engines.tts_engine import parse_rate_multiplier
from core.workers.voice_loader_worker import VoiceLoaderWorker
from ui.components.float_input_window import FloatInputWindow
from ui.components.hotkey_dialog import HotkeyBindDialog, SystemHotkeyDialog
from ui.components.list_delegate import HotkeyItemDelegate
from utils.explorer import reveal_in_explorer
from utils.window_manager import WindowManager
from version import APP_VERSION


class MainWindow(QMainWindow):
    DISPLAY_SEP = '--|--'

    AVAILABLE_ENGINES = {
        'PyTTSX3': PyTTSX3Engine,
        'EdgeTTS': EdgeTTSEngine,
        'OnlineAPI': OnlineAPIEngine,
    }

    def __init__(self):
        super().__init__()

        # ---------- 数据与服务 ----------
        self.paths = DataPaths()
        self.paths.migrate_if_needed()

        self.config_manager = ConfigManager(self.paths.config_file)
        self.config = self.config_manager.load()

        self.history_store = HistoryStore(self.paths.history_file)
        self.history_store.load()

        self.presets = PresetService(self.config_manager, self.paths.preset_audio_dir)
        self.hotkey_registry = HotkeyRegistry(self.config_manager)
        self.hotkey_service = HotkeyService(self.hotkey_registry, parent=self)
        self.playback = PlaybackController(self)
        self.window_manager = WindowManager(self.config.get("games") or [])

        self.voice_pool = QThreadPool(self)
        self.voice_pool.setMaxThreadCount(2)
        self._voice_request_id = 0

        # ---------- 运行状态 ----------
        self.current_engine_name = self.config.get("last_engine")
        self.current_voice_id = self.config.get("last_voice_id")
        self.active_engine = None
        self.rate = self.config.get("rate", "+10%")
        self.tts_volume = float(self.config.get("tts_volume", 1.0))
        self.preset_audio_volume = float(self.config.get("preset_audio_volume", 0.5))
        self.speak_key = self.config.get("speak_key", "pagedown")
        self.mic_statu = False
        self.auto_clear_history = bool(self.config.get("auto_clear_history", False))

        self.float_window = None
        self.presets_audio: dict[str, str] = {}
        self.last_play_type = None
        self.last_play_content = None
        self._no_audio_devices = False

        self.perform_auto_clear_history()

        # ---------- UI ----------
        self._init_ui()
        self.game_status_timer = QTimer(self)
        self.game_status_timer.setInterval(1000)
        self.game_status_timer.timeout.connect(self._poll_game_status)
        self.game_status_timer.start()
        self._poll_game_status()

        self.load_presets_text()
        self.load_preset_audio()
        self.load_history_ui()
        self.init_engine_and_voices()

        self._connect_playback()
        self.hotkey_service.rebuild()

    # ==================================================================
    # UI 构建
    # ==================================================================
    def _init_ui(self):
        self.setWindowTitle(f"我是你的嘴 v{APP_VERSION}")
        self.setGeometry(100, 100, 550, 750)
        icon_file = resource_path("resources/icon.png")
        if icon_file.exists():
            self.setWindowIcon(QIcon(str(icon_file)))

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(12)

        self.setStyleSheet("""
            QLabel#headerLabel { font-weight: bold; font-size: 14px; }
            QPushButton#primaryBtn {
                background-color: #0078D4; color: white; font-weight: bold;
                font-size: 14px; border-radius: 6px;
            }
            QPushButton#primaryBtn:hover { background-color: #106EBE; }
            QPushButton#primaryBtn:pressed { background-color: #005A9E; }
            QPushButton#primaryBtn:disabled { background-color: #A0CBE8; }
            QPushButton#dangerBtn {
                color: #D13438; font-weight: bold; border-radius: 6px;
            }
        """)

        self.main_splitter = QSplitter(Qt.Vertical)
        self.main_splitter.setHandleWidth(6)
        root_layout.addWidget(self.main_splitter)

        self.top_container = QWidget()
        self.top_layout = QVBoxLayout(self.top_container)
        self.top_layout.setContentsMargins(8, 8, 8, 12)
        self.main_splitter.addWidget(self.top_container)

        self.preset_container = QWidget()
        self.preset_layout = QVBoxLayout(self.preset_container)
        self.preset_layout.setContentsMargins(8, 8, 8, 12)
        self.preset_layout.setSpacing(10)
        self.main_splitter.addWidget(self.preset_container)

        self.history_container = QWidget()
        self.history_layout = QVBoxLayout(self.history_container)
        self.history_layout.setContentsMargins(8, 8, 8, 8)
        self.history_layout.setSpacing(10)
        self.main_splitter.addWidget(self.history_container)

        self.main_layout = self.top_layout
        self._init_engine_voice_ui()
        self._init_device_ui()
        self._init_settings_ui()
        self._init_text_input_ui()
        self._init_control_buttons_ui()

        self.main_layout = self.preset_layout
        self._init_preset_lists_ui()

        self.main_layout = self.history_layout
        self._init_history_ui()

        self.main_layout = root_layout
        self.main_splitter.setSizes([380, 320, 250])

        if self._no_audio_devices:
            self.convert_btn.setEnabled(False)

    def _init_engine_voice_ui(self):
        layout = QHBoxLayout()
        layout.addWidget(QLabel("引擎:"))
        self.engine_combo = QComboBox()
        self.engine_combo.setMinimumWidth(150)
        self.engine_combo.currentIndexChanged.connect(self.engine_selection_changed)
        layout.addWidget(self.engine_combo)

        layout.addWidget(QLabel("音色:"))
        self.voice_combo = QComboBox()
        self.voice_combo.setMinimumWidth(350)
        self.voice_combo.currentIndexChanged.connect(self.save_current_config)
        layout.addWidget(self.voice_combo)

        layout.addStretch(1)
        self.main_layout.addLayout(layout)

    def _init_settings_ui(self):
        layout = QHBoxLayout()
        layout.addWidget(QLabel('速度'))
        self.settings_voice_speed_box = QDoubleSpinBox()
        self.settings_voice_speed_box.setRange(0.5, 2.0)
        self.settings_voice_speed_box.setSingleStep(0.1)
        self.settings_voice_speed_box.setDecimals(1)
        self.settings_voice_speed_box.setValue(
            max(0.5, min(2.0, parse_rate_multiplier(self.rate)))
        )
        self.settings_voice_speed_box.valueChanged.connect(self.on_voice_speed_changed)
        layout.addWidget(self.settings_voice_speed_box)

        layout.addWidget(QLabel("置顶"))
        self.settings_always_on_top_box = QCheckBox()
        self.settings_always_on_top_box.setChecked(False)
        self.settings_always_on_top_box.toggled.connect(self.on_always_on_top_changed)
        layout.addWidget(self.settings_always_on_top_box)

        layout.addWidget(QLabel(" TTS音量:"))
        self.tts_volume_box = QDoubleSpinBox()
        self.tts_volume_box.setRange(0.0, 1.0)
        self.tts_volume_box.setSingleStep(0.1)
        self.tts_volume_box.setDecimals(1)
        self.tts_volume_box.setValue(self.tts_volume)
        self.tts_volume_box.valueChanged.connect(self.on_tts_volume_changed)
        layout.addWidget(self.tts_volume_box)

        layout.addWidget(QLabel(" 预设音量:"))
        self.preset_volume_box = QDoubleSpinBox()
        self.preset_volume_box.setRange(0.0, 1.0)
        self.preset_volume_box.setSingleStep(0.1)
        self.preset_volume_box.setDecimals(1)
        self.preset_volume_box.setValue(self.preset_audio_volume)
        self.preset_volume_box.valueChanged.connect(self.on_preset_audio_volume_changed)
        layout.addWidget(self.preset_volume_box)

        layout.addWidget(QLabel("开游戏麦:"))
        self.open_game_mic_box = QCheckBox()
        self.open_game_mic_box.setChecked(self.mic_statu)
        self.open_game_mic_box.toggled.connect(self.on_open_game_mic_box_changed)
        layout.addWidget(self.open_game_mic_box)

        self.btn_set_mic_key = QPushButton(f"[{self.speak_key}]")
        self.btn_set_mic_key.setFixedWidth(80)
        self.btn_set_mic_key.setToolTip("点击设置游戏内语音按键")
        self.btn_set_mic_key.clicked.connect(self.set_mic_key_dialog)
        layout.addWidget(self.btn_set_mic_key)

        layout.addStretch(1)
        self.main_layout.addLayout(layout)

        game_layout = QHBoxLayout()
        game_layout.addWidget(QLabel("游戏检测:"))
        self.game_status_label = QLabel("未命中")
        self.game_status_label.setMinimumWidth(160)
        self.game_status_label.setStyleSheet("color: #777;")
        game_layout.addWidget(self.game_status_label)
        self.btn_games = QPushButton("游戏列表")
        self.btn_games.setFixedWidth(80)
        self.btn_games.setToolTip("编辑游戏窗口关键词（匹配标题或进程名，每行一个）")
        self.btn_games.clicked.connect(self.open_games_dialog)
        game_layout.addWidget(self.btn_games)
        game_layout.addStretch(1)
        self.main_layout.addLayout(game_layout)

    def _init_device_ui(self):
        layout = QHBoxLayout()
        layout.addWidget(QLabel("输出设备:"))
        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(250)
        self.populate_audio_devices()
        self.device_combo.currentIndexChanged.connect(self.save_current_config)
        layout.addWidget(self.device_combo)
        layout.addStretch(1)
        self.main_layout.addLayout(layout)

    def _init_text_input_ui(self):
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)

        lbl_input = QLabel("输入文本:")
        lbl_input.setObjectName("headerLabel")
        header_layout.addWidget(lbl_input)
        header_layout.addStretch(1)

        btn_float_input_box = QPushButton("打开悬浮输入框")
        btn_float_input_box.clicked.connect(self.open_float_window)
        header_layout.addWidget(btn_float_input_box)

        btn_add_text = QPushButton("存为预设")
        btn_add_text.clicked.connect(self.add_current_text_to_presets)
        header_layout.addWidget(btn_add_text)

        btn_sys_hotkeys = QPushButton("全局快捷键")
        btn_sys_hotkeys.clicked.connect(self.open_sys_hotkey_dialog)
        header_layout.addWidget(btn_sys_hotkeys)

        self.main_layout.addLayout(header_layout)

        self.text_input = QTextEdit()
        self.text_input.installEventFilter(self)
        self.text_input.setMaximumHeight(60)
        self.main_layout.addWidget(self.text_input)

    def _init_control_buttons_ui(self):
        layout = QHBoxLayout()
        layout.addStretch(1)

        self.convert_btn = QPushButton("开始转换和播放")
        self.convert_btn.setObjectName("primaryBtn")
        self.convert_btn.setFixedSize(220, 42)
        self.convert_btn.clicked.connect(self.convert_text)

        self.stop_btn = QPushButton("停止播放")
        self.stop_btn.setObjectName("dangerBtn")
        self.stop_btn.setFixedSize(220, 42)
        self.stop_btn.clicked.connect(self.stop_playback)

        layout.addWidget(self.convert_btn)
        layout.addSpacing(20)
        layout.addWidget(self.stop_btn)
        layout.addStretch(1)
        self.main_layout.addLayout(layout)

    def _init_preset_lists_ui(self):
        label_layout = QHBoxLayout()

        text_header_widget = QWidget()
        text_header_layout = QHBoxLayout(text_header_widget)
        text_header_layout.setContentsMargins(0, 0, 0, 0)
        lbl_text_preset = QLabel("预设文本:")
        lbl_text_preset.setObjectName("headerLabel")
        text_header_layout.addWidget(lbl_text_preset)
        btn_clear_text = QPushButton("清除快捷键")
        btn_clear_text.setFixedWidth(80)
        btn_clear_text.clicked.connect(self.clear_text_hotkeys)
        text_header_layout.addWidget(btn_clear_text)
        text_header_layout.addStretch(1)

        audio_header_widget = QWidget()
        audio_header_layout = QHBoxLayout(audio_header_widget)
        audio_header_layout.setContentsMargins(0, 0, 0, 0)
        lbl_audio_preset = QLabel("预设音频:")
        lbl_audio_preset.setObjectName("headerLabel")
        audio_header_layout.addWidget(lbl_audio_preset)
        btn_import_audio = QPushButton("导入音频")
        btn_import_audio.setFixedWidth(80)
        btn_import_audio.clicked.connect(self.import_preset_audio)
        audio_header_layout.addWidget(btn_import_audio)
        btn_clear_audio = QPushButton("清除快捷键")
        btn_clear_audio.setFixedWidth(80)
        btn_clear_audio.clicked.connect(self.clear_audio_hotkeys)
        audio_header_layout.addWidget(btn_clear_audio)
        audio_header_layout.addStretch(1)

        label_layout.addWidget(text_header_widget)
        label_layout.addWidget(audio_header_widget)
        self.main_layout.addLayout(label_layout)

        list_layout = QHBoxLayout()

        self.preset_text_list = QListWidget()
        self.preset_text_list.setUniformItemSizes(True)
        self.preset_text_list.setItemDelegate(HotkeyItemDelegate(self.preset_text_list))
        self.preset_text_list.itemDoubleClicked.connect(self.on_preset_text_double_clicked)
        self.preset_text_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.preset_text_list.customContextMenuRequested.connect(
            lambda pos: self.show_list_context_menu(pos, self.preset_text_list, "text")
        )
        list_layout.addWidget(self.preset_text_list)

        self.preset_audio_list = QListWidget()
        self.preset_audio_list.setUniformItemSizes(True)
        self.preset_audio_list.setItemDelegate(HotkeyItemDelegate(self.preset_audio_list))
        self.preset_audio_list.itemDoubleClicked.connect(self.on_preset_audio_double_clicked)
        self.preset_audio_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.preset_audio_list.customContextMenuRequested.connect(
            lambda pos: self.show_list_context_menu(pos, self.preset_audio_list, "audio")
        )
        list_layout.addWidget(self.preset_audio_list)

        self.main_layout.addLayout(list_layout)

    def _init_history_ui(self):
        history_header_widget = QWidget()
        history_header_layout = QHBoxLayout(history_header_widget)
        history_header_layout.setContentsMargins(0, 0, 0, 0)

        lbl_history = QLabel("历史记录 (双击播放 / 右键):")
        lbl_history.setObjectName("headerLabel")
        history_header_layout.addWidget(lbl_history)
        history_header_layout.addStretch(1)

        self.auto_clear_history_box = QCheckBox("每次启动时自动清理")
        self.auto_clear_history_box.setChecked(self.auto_clear_history)
        self.auto_clear_history_box.toggled.connect(self.on_auto_clear_history_changed)
        history_header_layout.addWidget(self.auto_clear_history_box)

        self.main_layout.addWidget(history_header_widget)

        self.history_list = QListWidget()
        self.history_list.itemDoubleClicked.connect(self.play_history)
        self.history_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.history_list.customContextMenuRequested.connect(self.show_history_context_menu)
        self.main_layout.addWidget(self.history_list)

        layout = QHBoxLayout()
        layout.addStretch(1)
        self.clear_btn = QPushButton("清空所有历史记录和文件")
        self.clear_btn.setFixedWidth(250)
        self.clear_btn.clicked.connect(self.clear_all_data)
        layout.addWidget(self.clear_btn)
        layout.addStretch(1)
        self.main_layout.addLayout(layout)

    # ==================================================================
    # 播放信号
    # ==================================================================
    def _connect_playback(self):
        self.playback.busy_changed.connect(self._on_busy_changed)
        self.playback.error.connect(self._on_playback_error)
        self.playback.converted.connect(self._on_converted)
        self.hotkey_service.triggered.connect(self.handle_hotkey)

    def _on_busy_changed(self, busy: bool):
        self.convert_btn.setEnabled(not busy and not self._no_audio_devices)

    def _on_playback_error(self, message: str):
        QMessageBox.critical(self, "TTS 错误", message)

    def _on_converted(self, record: HistoryRecord):
        self.history_store.add(record)
        self._insert_history_item(record)

    # ==================================================================
    # 设备与音色
    # ==================================================================
    def populate_audio_devices(self):
        self.device_combo.clear()
        devices = AudioManager.get_output_devices()
        if not devices:
            self._no_audio_devices = True
            self.device_combo.addItem("未找到输出设备", -1)
            return

        self._no_audio_devices = False
        for device in devices:
            self.device_combo.addItem(device['name'], device['index'])

        last_name = self.config_manager.get("last_device_name")
        target_row = AudioManager.find_device_row_by_name(devices, last_name)
        self.device_combo.setCurrentIndex(max(0, target_row))

    def _current_device(self) -> int | None:
        data = self.device_combo.currentData()
        if data is None or data == -1:
            return None
        return int(data)

    def save_current_config(self):
        if not hasattr(self, 'device_combo'):
            return

        device_name = self.device_combo.currentText()
        if device_name == "未找到输出设备" or self.device_combo.currentData() == -1:
            device_name = None

        updates = {
            "last_device_name": device_name,
            "last_engine": self.current_engine_name,
            "rate": self.rate,
            "tts_volume": self.tts_volume,
            "preset_audio_volume": self.preset_audio_volume,
            "speak_key": self.speak_key,
        }
        voice_id = self.voice_combo.currentData()
        if voice_id:
            updates["last_voice_id"] = voice_id
            self.current_voice_id = voice_id
        self.config_manager.save(updates)

    def init_engine_and_voices(self):
        self.engine_combo.blockSignals(True)
        self.engine_combo.clear()
        for name in self.AVAILABLE_ENGINES:
            self.engine_combo.addItem(name)

        names = list(self.AVAILABLE_ENGINES)
        if self.current_engine_name in self.AVAILABLE_ENGINES:
            self.engine_combo.setCurrentIndex(names.index(self.current_engine_name))
        else:
            self.current_engine_name = names[0]
            self.engine_combo.setCurrentIndex(0)
        self.engine_combo.blockSignals(False)
        self.engine_selection_changed()

    def engine_selection_changed(self):
        name = self.engine_combo.currentText()
        engine_class = self.AVAILABLE_ENGINES.get(name)
        if engine_class is None:
            self.voice_combo.clear()
            self.voice_combo.addItem("请先选择引擎", None)
            return
        self.active_engine = engine_class()
        self.current_engine_name = name
        self.populate_voices_async()
        self.config_manager.save({"last_engine": name})

    def populate_voices_async(self):
        if self.active_engine is None:
            return
        self._voice_request_id += 1
        request_id = self._voice_request_id

        self.voice_combo.clear()
        self.voice_combo.addItem(f"加载 {self.active_engine.name} 音色中...", None)
        self.voice_combo.setEnabled(False)

        worker = VoiceLoaderWorker(self.active_engine, request_id)
        worker.signals.finished.connect(self.handle_voices_loaded)
        worker.signals.error.connect(self.handle_voices_error)
        self.voice_pool.start(worker)

    def handle_voices_loaded(self, request_id: int, voices: list):
        if request_id != self._voice_request_id:
            return  # 过期结果
        cached_voice_id = self.current_voice_id
        self.voice_combo.blockSignals(True)
        self.voice_combo.clear()
        self.voice_combo.setEnabled(True)

        target_index = -1
        if not voices:
            self.voice_combo.addItem("无可用音色", None)
            self.current_voice_id = None
        else:
            for i, voice in enumerate(voices):
                self.voice_combo.addItem(voice["name"], voice["id"])
                if cached_voice_id == voice["id"]:
                    target_index = i
            if target_index != -1:
                self.voice_combo.setCurrentIndex(target_index)
            else:
                self.voice_combo.setCurrentIndex(0)
                self.current_voice_id = self.voice_combo.currentData()

        self.voice_combo.blockSignals(False)
        self.save_current_config()

    def handle_voices_error(self, request_id: int, message: str):
        if request_id != self._voice_request_id:
            return
        self.voice_combo.clear()
        self.voice_combo.addItem("加载失败", None)
        self.voice_combo.setEnabled(True)
        self.current_voice_id = None
        self.save_current_config()
        QMessageBox.critical(self, "音色加载错误", message)

    # ==================================================================
    # 预设列表
    # ==================================================================
    def load_presets_text(self):
        self.preset_text_list.clear()
        hotkeys = self.hotkey_registry.text_hotkeys
        sorted_texts = sorted(
            self.presets.text_presets,
            key=lambda t: self._get_hotkey_sort_weight(t, hotkeys),
        )
        for text in sorted_texts:
            display_name = text.replace('\n', ' ')
            if len(display_name) > 30:
                display_name = display_name[:28] + "..."

            item = QListWidgetItem(display_name)
            item.setToolTip(text)
            item.setData(Qt.UserRole, text)
            item.setData(Qt.UserRole + 1, text)
            item.setData(Qt.UserRole + 2, hotkeys.get(text, ""))
            self.preset_text_list.addItem(item)

    def load_preset_audio(self):
        self.presets_audio = self.presets.audio_presets()
        self.preset_audio_list.clear()
        hotkeys = self.hotkey_registry.audio_hotkeys

        sorted_names = sorted(
            self.presets_audio.keys(),
            key=lambda name: self._get_hotkey_sort_weight(name, hotkeys),
        )
        for name in sorted_names:
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, self.presets_audio[name])
            item.setData(Qt.UserRole + 1, name)
            item.setData(Qt.UserRole + 2, hotkeys.get(name, ""))
            self.preset_audio_list.addItem(item)

    def _get_hotkey_sort_weight(self, item_name: str, hotkeys_dict: dict) -> tuple:
        hotkey_str = hotkeys_dict.get(item_name, "")
        if not hotkey_str:
            return (1, 0, 0, "", item_name)

        parts = hotkey_str.lower().split('+')
        modifiers = [p for p in parts if p in ('ctrl', 'alt', 'shift', 'win')]
        main_keys = [p for p in parts if p not in ('ctrl', 'alt', 'shift', 'win')]
        main_key = main_keys[0] if main_keys else ""

        mod_score = 0
        if 'ctrl' in modifiers:
            mod_score += 1
        if 'alt' in modifiers:
            mod_score += 2
        if 'shift' in modifiers:
            mod_score += 4
        if 'win' in modifiers:
            mod_score += 8

        if main_key.isdigit() or (main_key.startswith('num') and main_key.replace('num', '').isdigit()):
            category = 1
        elif len(main_key) == 1 and main_key.isalpha():
            category = 2
        else:
            category = 3
        return (0, mod_score, category, main_key, item_name)

    def add_current_text_to_presets(self):
        text = self.text_input.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "提示", "请先在下方输入需要保存的文本。")
            return
        if self.presets.add_text(text):
            self.load_presets_text()
            QMessageBox.information(self, "成功", "已成功保存为预设文本！")
        else:
            QMessageBox.information(self, "提示", "该预设已存在。")

    # ==================================================================
    # 预设右键菜单 / 快捷键
    # ==================================================================
    def show_list_context_menu(self, pos, list_widget, item_type):
        item = list_widget.itemAt(pos)
        if not item:
            return

        name = item.data(Qt.UserRole + 1)
        action_id = make_action_id(item_type, name)
        current_key = self.hotkey_registry.current_key(action_id)

        menu = QMenu()
        bind_text = f"🎯 修改快捷键 (当前: {current_key})" if current_key else "🎯 分配快捷键"
        bind_action = menu.addAction(bind_text)
        unbind_action = menu.addAction("❌ 取消快捷键")
        menu.addSeparator()

        if item_type == "text":
            edit_action = menu.addAction("📝 编辑此文本")
            open_action = menu.addAction("📂 打开数据文件夹")
            delete_action = menu.addAction("🗑️ 删除此预设")
        else:
            edit_action = None
            open_action = menu.addAction("📂 打开所在文件夹")
            delete_action = menu.addAction("🗑️ 删除此音频文件")

        action = menu.exec_(list_widget.mapToGlobal(pos))

        if action == bind_action:
            self._bind_hotkey(action_id, current_key)
        elif action == unbind_action:
            self._apply_hotkey(action_id, "")
        elif edit_action is not None and action == edit_action:
            self._edit_preset_text(item)
        elif action == open_action:
            if item_type == "text":
                self._open_path(self.paths.conf_dir)
            else:
                self._open_path(item.data(Qt.UserRole))
        elif action == delete_action:
            if item_type == "text":
                self._delete_preset_text(item)
            else:
                self._delete_preset_audio(item)

    def _bind_hotkey(self, action_id: str, current_key: str):
        self.hotkey_service.stop()
        dialog = HotkeyBindDialog(current_key, self)
        if dialog.exec_() != QDialog.Accepted:
            self.hotkey_service.rebuild()
            return

        new_key = dialog.get_hotkey()
        if not new_key or new_key == current_key:
            self.hotkey_service.rebuild()
            return

        conflict_id = self.hotkey_registry.find_conflict(new_key, action_id)
        if conflict_id:
            reply = QMessageBox.warning(
                self, "快捷键冲突",
                f"快捷键 [{new_key}] 已被分配。\n是否强制覆盖？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if reply == QMessageBox.No:
                self.hotkey_service.rebuild()
                return
            self.hotkey_registry.set(conflict_id, "")

        self._apply_hotkey(action_id, new_key)

    def _apply_hotkey(self, action_id: str, new_key: str):
        self.hotkey_registry.set(action_id, new_key)
        self.hotkey_service.rebuild()
        if action_id.startswith("text_"):
            self._animate_widget_update(self.preset_text_list, self.load_presets_text)
        elif action_id.startswith("audio_"):
            self._animate_widget_update(self.preset_audio_list, self.load_preset_audio)

    def update_single_hotkey(self, action_id: str, new_key_str: str):
        """兼容旧调用点的公开方法。"""
        self._apply_hotkey(action_id, new_key_str)

    def _edit_preset_text(self, item: QListWidgetItem):
        old_text = item.data(Qt.UserRole)
        new_text, ok = QInputDialog.getMultiLineText(self, "编辑预设文本", "请输入新的文本:", old_text)
        if not ok:
            return
        new_text = new_text.strip()
        if not new_text or new_text == old_text:
            return

        self.presets.rename_text(old_text, new_text)
        self.hotkey_service.rebuild()
        self.load_presets_text()

    def _delete_preset_text(self, item: QListWidgetItem):
        text = item.data(Qt.UserRole)
        reply = QMessageBox.question(
            self, "确认删除", "确定要删除此预设文本吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self.presets.remove_text(text)
        self.hotkey_service.rebuild()
        self.load_presets_text()

    def _delete_preset_audio(self, item: QListWidgetItem):
        path = item.data(Qt.UserRole)
        name = item.data(Qt.UserRole + 1)
        reply = QMessageBox.question(
            self, "确认删除", "确定要删除此预设音频吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        result = self.presets.remove_audio(name, path)
        if result == "unlinked":
            QMessageBox.information(self, "成功", "已移除该音频的引用记录（您的原文件未被删除）。")
        elif result == "deleted":
            QMessageBox.information(self, "成功", "音频文件已从软件库中彻底删除。")
        elif result == "failed":
            QMessageBox.critical(self, "错误", "删除失败，文件可能被占用。")
        self.hotkey_service.rebuild()
        self.load_preset_audio()

    def clear_text_hotkeys(self):
        self._bulk_clear_hotkeys("text_", "文本", self.load_presets_text)

    def clear_audio_hotkeys(self):
        self._bulk_clear_hotkeys("audio_", "音频", self.load_preset_audio)

    def _bulk_clear_hotkeys(self, prefix: str, type_str: str, refresh):
        mapping = (
            self.hotkey_registry.text_hotkeys if prefix == "text_"
            else self.hotkey_registry.audio_hotkeys
        )
        if not mapping:
            QMessageBox.information(self, "提示", f"当前分类下没有绑定任何{type_str}快捷键。")
            return

        count = len(mapping)
        reply = QMessageBox.question(
            self, "确认清除",
            f"确定要清除所有预设{type_str}的快捷键吗？\n(将清除 {count} 个按键绑定，不会删除文件)",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self.hotkey_registry.clear_prefix(prefix)
        self.hotkey_service.rebuild()
        refresh()
        logging.info("已批量清除 %d 个 %s 快捷键", count, prefix)

    def open_sys_hotkey_dialog(self):
        self.hotkey_service.stop()
        dialog = SystemHotkeyDialog(self.hotkey_registry.sys_hotkeys, self)
        if dialog.exec_() == QDialog.Accepted:
            changed = False
            for action_id, new_key in dialog.get_new_hotkeys().items():
                if new_key != self.hotkey_registry.current_key(action_id):
                    self.hotkey_registry.set(action_id, new_key)
                    changed = True
            if changed:
                QMessageBox.information(self, "成功", "全局系统快捷键已更新！")
        self.hotkey_service.rebuild()

    def open_games_dialog(self):
        games = self.config.get("games", [])
        text, ok = QInputDialog.getMultiLineText(
            self,
            "游戏窗口匹配列表",
            "每行一个关键词，匹配窗口标题或进程名（不区分大小写）：",
            "\n".join(games),
        )
        if not ok:
            return

        seen = set()
        new_games = []
        for line in text.splitlines():
            game = line.strip()
            if game and game.lower() not in seen:
                seen.add(game.lower())
                new_games.append(game)
        if not new_games:
            QMessageBox.warning(self, "提示", "至少保留一个游戏关键词。")
            return

        self.config_manager.save({"games": new_games})
        self.window_manager.set_target_games(new_games)
        self._poll_game_status()
        QMessageBox.information(self, "成功", f"已保存 {len(new_games)} 个游戏关键词。")

    def _poll_game_status(self):
        match = self.window_manager.foreground_match()
        if match is not None:
            self.game_status_label.setText(f"✅ 已命中：{match.keyword}")
            self.game_status_label.setStyleSheet("color: #107C10; font-weight: bold;")
            detail = match.title
            if match.exe_name:
                detail += f"\n{match.exe_name}"
            self.game_status_label.setToolTip(detail)
        else:
            self.game_status_label.setText("未命中")
            self.game_status_label.setStyleSheet("color: #777;")
            self.game_status_label.setToolTip("当前前台窗口不在游戏列表中")

    def _open_path(self, path):
        if not path:
            QMessageBox.information(self, "提示", "该记录没有关联文件。")
            return
        if not reveal_in_explorer(path):
            QMessageBox.warning(self, "无法打开", f"路径不存在：{path}")

    def handle_hotkey(self, action_id: str):
        logging.info("触发热键动作: %s", action_id)

        if action_id == 'sys_toggle_window':
            self.toggle_visibility()
        elif action_id == 'sys_stop_play':
            self.stop_playback()
        elif action_id == 'sys_toggle_mic':
            self.toggle_mic()
        elif action_id == 'sys_repeat_play':
            self.repeat_last_play()
        elif action_id == 'sys_float_window':
            self.toggle_float_window()
        elif action_id.startswith('audio_'):
            item_name = action_id[6:]
            if item_name in self.presets_audio:
                self.play_preset_audio(self.presets_audio[item_name])
        elif action_id.startswith('text_'):
            item_name = action_id[5:]
            if item_name in self.presets.text_presets:
                self.text_input.setText(item_name)
                self.convert_text()

    # ==================================================================
    # 历史记录
    # ==================================================================
    def _history_display(self, record: HistoryRecord) -> str:
        return (
            f'{record.text}{self.DISPLAY_SEP}{record.engine or "Unknown"}'
            f'{self.DISPLAY_SEP}{record.rate}'
            f'{self.DISPLAY_SEP}{record.voice_id or "Default"}'
        )

    def _insert_history_item(self, record: HistoryRecord, at_top: bool = True):
        item = QListWidgetItem(self._history_display(record))
        item.setData(Qt.UserRole, record)
        if at_top:
            self.history_list.insertItem(0, item)
        else:
            self.history_list.addItem(item)

    def load_history_ui(self):
        self.history_list.clear()
        for record in self.history_store.records:
            self._insert_history_item(record, at_top=True)

    def play_history(self, item: QListWidgetItem):
        scrollbar = self.history_list.verticalScrollBar()
        current_pos = scrollbar.value()
        record = item.data(Qt.UserRole)
        if isinstance(record, HistoryRecord):
            self._play_history_record(record)
        self.qlist_scrollbar_recover_pos(scrollbar, current_pos)

    def _play_history_record(self, record: HistoryRecord):
        if not record.path or not Path(record.path).exists():
            QMessageBox.warning(self, "警告", "音频文件未找到，可能已被删除。")
            return
        device = self._current_device()
        if device is None:
            QMessageBox.warning(self, "警告", "请先选择一个输出设备。")
            return

        self.window_manager.focus_game_if_needed(self.mic_statu)
        self.playback.play_file(
            path=record.path,
            device_index=device,
            volume=self.tts_volume,
            open_game_mic=self.mic_statu,
            speak_key=self.speak_key,
            game_games=list(self.config.get("games", [])),
        )

    def show_history_context_menu(self, pos):
        item = self.history_list.itemAt(pos)
        if not item:
            return
        record = item.data(Qt.UserRole)
        if not isinstance(record, HistoryRecord):
            return

        menu = QMenu()
        play_action = menu.addAction("▶️ 播放此记录")
        preset_action = menu.addAction("⭐ 提升为预设文本")
        open_action = menu.addAction("📂 打开所在文件夹")
        menu.addSeparator()
        delete_action = menu.addAction("🗑️ 删除此记录 (同步删除音频)")

        action = menu.exec_(self.history_list.mapToGlobal(pos))
        if action == play_action:
            self._play_history_record(record)
        elif action == preset_action:
            if self.presets.add_text(record.text):
                self.load_presets_text()
                QMessageBox.information(self, "成功", "已成功添加到预设文本！")
            else:
                QMessageBox.information(self, "提示", "该预设已存在。")
        elif action == open_action:
            self._open_path(record.path)
        elif action == delete_action:
            reply = QMessageBox.question(
                self, "确认删除", "确定要删除这条历史记录及硬盘上的关联音频文件吗？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
            self.history_store.remove(record)
            if record.path and Path(record.path).exists():
                try:
                    Path(record.path).unlink()
                except OSError as exc:
                    logging.warning("删除历史音频失败: %s", exc)
            row = self.history_list.row(item)
            self.history_list.takeItem(row)

    def perform_auto_clear_history(self):
        if not self.auto_clear_history:
            return
        removed, deleted = self.history_store.clear_non_presets(set(self.presets.text_presets))
        if removed:
            logging.info("启动清理：移除 %d 条历史，删除 %d 个文件", removed, deleted)

    def on_auto_clear_history_changed(self, checked: bool):
        self.auto_clear_history = checked
        self.config_manager.save({"auto_clear_history": checked})

    def clear_all_data(self):
        reply = QMessageBox.question(
            self, '确认清理',
            "这将清空所有历史记录，并删除所有生成的音频文件。您确定吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        deleted, failed = self.history_store.clear_all()
        self.history_list.clear()
        msg = f"清理完成！\n成功删除音频: {deleted} 个"
        if failed:
            msg += f"\n失败: {failed} 个(可能文件已丢失或无权限)"
        QMessageBox.information(self, "清理结果", msg)

    # ==================================================================
    # 转换与播放
    # ==================================================================
    def get_input_text(self) -> str:
        return self.text_input.toPlainText().strip()

    def _new_audio_path(self) -> str:
        suffix = self.active_engine.file_suffix if self.active_engine else ".wav"
        self.paths.audios_dir.mkdir(parents=True, exist_ok=True)
        name = f"audio_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}{suffix}"
        return str((self.paths.audios_dir / name).resolve())

    def convert_text(self):
        text = self.get_input_text()
        if not text:
            QMessageBox.warning(self, "警告", "请输入要转换的文本。")
            return

        device = self._current_device()
        if device is None:
            QMessageBox.warning(self, "警告", "请先选择一个输出设备。")
            return

        voice_id = self.voice_combo.currentData()
        if voice_id is None:
            QMessageBox.warning(self, "警告", "当前引擎无可用音色，请更换引擎或检查依赖。")
            return
        if self.active_engine is None:
            QMessageBox.warning(self, "警告", "请先选择一个 TTS 引擎。")
            return

        self.last_play_type = 'text'
        self.last_play_content = text
        self.window_manager.focus_game_if_needed(self.mic_statu)

        record = self.history_store.find(
            text, self.rate, self.current_engine_name, voice_id or ""
        )
        if record is not None and Path(record.path).exists():
            logging.info("命中历史记录，直接播放: %s", record.path)
            self._play_history_record(record)
            return

        self.playback.speak(
            text=text,
            engine=self.active_engine,
            voice_id=voice_id,
            rate=self.rate,
            output_path=self._new_audio_path(),
            device_index=device,
            volume=self.tts_volume,
            open_game_mic=self.mic_statu,
            speak_key=self.speak_key,
            game_games=list(self.config.get("games", [])),
        )

    def repeat_last_play(self):
        if not self.last_play_type:
            logging.warning("没有可重复播放的记录")
            return
        logging.info("重复播放: [%s] %s", self.last_play_type, self.last_play_content)
        if self.last_play_type == 'text':
            self.text_input.setText(self.last_play_content)
            self.convert_text()
        elif self.last_play_type == 'audio':
            if not Path(self.last_play_content).exists():
                logging.warning("原文件已丢失: %s", self.last_play_content)
                return
            self.play_preset_audio(self.last_play_content)

    def play_preset_audio(self, path: str):
        device = self._current_device()
        if device is None:
            QMessageBox.warning(self, "警告", "请先选择一个输出设备。")
            return
        self.last_play_type = 'audio'
        self.last_play_content = path
        self.window_manager.focus_game_if_needed(self.mic_statu)
        self.playback.play_file(
            path=path,
            device_index=device,
            volume=self.preset_audio_volume,
            open_game_mic=self.mic_statu,
            speak_key=self.speak_key,
            game_games=list(self.config.get("games", [])),
        )

    def stop_playback(self):
        self.playback.stop()

    def import_preset_audio(self):
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "选择要导入的音频文件", "",
            "Audio Files (*.mp3 *.wav *.ogg *.flac *.aac *.m4a *.wma);;All Files (*)",
        )
        if not file_paths:
            return

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("选择导入方式")
        msg_box.setText(
            f"已选择 {len(file_paths)} 个音频文件。\n\n请选择导入模式：\n\n"
            "📦【复制文件】：将文件拷贝到软件内部统一管理（原文件被删也不影响）。\n"
            "🔗【仅存引用】：不移动原文件，仅记录路径（节省硬盘空间）。"
        )
        btn_copy = msg_box.addButton("📦 复制文件", QMessageBox.AcceptRole)
        btn_link = msg_box.addButton("🔗 仅存引用", QMessageBox.AcceptRole)
        btn_cancel = msg_box.addButton("取消", QMessageBox.RejectRole)
        msg_box.exec_()

        clicked = msg_box.clickedButton()
        if clicked == btn_cancel:
            return

        imported = self.presets.import_audio(file_paths, copy_files=(clicked == btn_copy))
        self.load_preset_audio()
        QMessageBox.information(self, "导入完成", f"成功导入 {imported} 个音频文件！")

    def on_preset_text_double_clicked(self, item: QListWidgetItem):
        scrollbar = self.preset_text_list.verticalScrollBar()
        current_pos = scrollbar.value()
        text = item.data(Qt.UserRole)
        if text:
            self.text_input.setText(text)
            self.convert_text()
        self.qlist_scrollbar_recover_pos(scrollbar, current_pos)

    def on_preset_audio_double_clicked(self, item: QListWidgetItem):
        scrollbar = self.preset_audio_list.verticalScrollBar()
        current_pos = scrollbar.value()
        path = item.data(Qt.UserRole)
        if path:
            self.play_preset_audio(path)
        self.qlist_scrollbar_recover_pos(scrollbar, current_pos)

    # ==================================================================
    # 其它 UI 事件
    # ==================================================================
    def set_mic_key_dialog(self):
        dialog = HotkeyBindDialog(self.speak_key, self)
        dialog.setWindowTitle("设置游戏内开麦按键")
        if dialog.exec_() == QDialog.Accepted:
            new_key = dialog.get_hotkey()
            if new_key:
                self.speak_key = new_key
                self.btn_set_mic_key.setText(f"[{self.speak_key}]")
                self.save_current_config()

    def open_float_window(self):
        if self.float_window is None:
            self.float_window = FloatInputWindow()
            self.float_window.text_submitted.connect(self.handle_input_task)
            self.float_window.open_mic_submitted.connect(self.handle_float_window_mic_task)
            self.float_window.open_game_mic_box.setChecked(self.mic_statu)
        self.float_window.show()
        self.float_window.raise_()
        self.float_window.activateWindow()
        self.float_window.input_box.setFocus()
        self.float_window.input_box.selectAll()

    def handle_input_task(self, text: str):
        self.text_input.setText(text)
        self.convert_text()

    def handle_float_window_mic_task(self, checked: bool):
        self.open_game_mic_box.setChecked(checked)
        self.mic_statu = checked

    def on_voice_speed_changed(self, value: float):
        val = int(value * 100)
        self.rate = f'+{val - 100}%' if val >= 100 else f'-{100 - val}%'
        self.save_current_config()

    def on_tts_volume_changed(self, value: float):
        self.tts_volume = value
        self.save_current_config()

    def on_preset_audio_volume_changed(self, value: float):
        self.preset_audio_volume = value
        self.save_current_config()

    def on_always_on_top_changed(self, checked: bool):
        self.setWindowFlag(Qt.WindowStaysOnTopHint, checked)
        self.show()

    def on_open_game_mic_box_changed(self, checked: bool):
        self.mic_statu = checked
        if self.float_window is not None:
            self.float_window.open_game_mic_box.setChecked(checked)

    def toggle_mic(self):
        self.open_game_mic_box.toggle()

    def toggle_visibility(self):
        if (self.isVisible()
                and not self.isMinimized()
                and self.text_input.hasFocus()):
            self.hide()
            return
        if self.isMinimized():
            self.showNormal()
        else:
            self.show()
        self.raise_()
        self.activateWindow()
        self.setWindowState((self.windowState() & ~Qt.WindowMinimized) | Qt.WindowActive)
        if not self.text_input.hasFocus():
            self.text_input.setFocus(Qt.OtherFocusReason)
        self.text_input.selectAll()

    def toggle_float_window(self):
        if self.float_window is None:
            self.open_float_window()
        fw = self.float_window
        if fw.isMinimized():
            fw.showNormal()
        elif fw.isVisible() and fw.input_box.hasFocus():
            fw.hide()
            return
        else:
            fw.show()
        fw.raise_()
        fw.activateWindow()
        if not fw.input_box.hasFocus():
            fw.input_box.setFocus()
        fw.input_box.selectAll()

    def qlist_scrollbar_recover_pos(self, scrollbar, position):
        timer = QTimer(scrollbar)
        timer.setInterval(10)
        tick_count = [0]

        def enforce_position():
            tick_count[0] += 1
            if scrollbar.value() != position:
                scrollbar.setValue(position)
            if tick_count[0] >= 50:
                timer.stop()
                timer.deleteLater()

        timer.timeout.connect(enforce_position)
        timer.start()

    def _animate_widget_update(self, widget, update_func):
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)

        self.anim_out = QPropertyAnimation(effect, b"opacity")
        self.anim_out.setDuration(100)
        self.anim_out.setStartValue(1.0)
        self.anim_out.setEndValue(0.0)

        def on_fade_out_finished():
            update_func()
            self.anim_in = QPropertyAnimation(effect, b"opacity")
            self.anim_in.setDuration(150)
            self.anim_in.setStartValue(0.0)
            self.anim_in.setEndValue(1.0)
            self.anim_in.start()

        self.anim_out.finished.connect(on_fade_out_finished)
        self.anim_out.start()

    def eventFilter(self, obj, event):
        if obj == self.text_input and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                if event.modifiers() & Qt.ShiftModifier:
                    return False
                self.convert_text()
                return True
        return super().eventFilter(obj, event)

    def closeEvent(self, event):
        self.game_status_timer.stop()
        self.playback.shutdown()
        self.hotkey_service.stop()
        if self.float_window is not None:
            self.float_window.close()
        super().closeEvent(event)
