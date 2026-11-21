# ui/main_window.py
import os, sys
import shutil
import time
from pathlib import Path

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (QMainWindow, QVBoxLayout, QCheckBox,
                             QHBoxLayout, QTextEdit, QComboBox,
                             QPushButton, QListWidget, QWidget,
                             QLabel, QMessageBox, QListWidgetItem, QDoubleSpinBox,
                             QMenu, QDialog, QInputDialog, QSplitter, QFileDialog,
                             QGraphicsOpacityEffect)
from PyQt5.QtCore import Qt, QThreadPool, QEvent, QTimer,QPropertyAnimation

from core.audio_manager import AudioManager
from core.workers.tts_worker import TTSWorker
from core.workers.voice_loader_worker import VoiceLoaderWorker
from core.engines.pyttsx3_engine import PyTTSX3Engine
from core.engines.edge_tts_engine import EdgeTTSEngine
from core.engines.api_engine import OnlineAPIEngine

from utils.config_manager import ConfigManager
from utils.history_manager import HistoryManager
from utils.hotkey_manager import HotkeyManager
from ui.components.hotkey_dialog import HotkeyBindDialog, SystemHotkeyDialog
from ui.components.list_delegate import HotkeyItemDelegate
from ui.components.float_input_window import FloatInputWindow
from utils.window_manager import WindowManager

import logging


class MainWindow(QMainWindow):
    AUDIO_DIR = Path("audios")

    AVAILABLE_ENGINES = {
        'PyTTSX3': PyTTSX3Engine,
        'EdgeTTS': EdgeTTSEngine,
        'OnlineAPI': OnlineAPIEngine,
    }

    def __init__(self):
        super().__init__()

        # ==========================================
        # 1. 核心管理器与配置加载 (无 UI 依赖)
        # ==========================================
        self.config_manager = ConfigManager()
        self.config = self.config_manager.load()  # 先拿到总配置字典
        self.history_manager = HistoryManager()
        self.history_manager.load()
        self.float_window = None
        self.window_manager = WindowManager()

        # ==========================================
        # 2. 状态变量初始化 (从配置中提取)
        # ==========================================
        # --- TTS 引擎与音量 ---
        self.current_engine_name = self.config.get("last_engine")
        self.current_voice_id = self.config.get("last_voice_id")
        self.current_worker  = None
        self.rate = self.config.get("rate", "+10%")
        self.tts_volume = self.config.get("tts_volume", 1.0)
        self.preset_audio_volume = self.config.get("preset_audio_volume", 0.5)

        # --- 数据预设与杂项 ---
        self.linked_audio = self.config.get("linked_audio", {})
        self.split_sign = '--|--'
        self.last_played_file = None
        self.last_played_text = ""

        # --- 游戏开麦相关 ---
        self.speak_key = self.config.get("speak_key", "pagedown")
        self.mic_statu = False

        # --- 全局系统快捷键 ---
        self.sys_hotkeys = self.config.get("sys_hotkeys", {
            'sys_toggle_window': 'ctrl+num_dot',
            'sys_stop_play': 'ctrl+num0',
            'sys_toggle_mic': 'ctrl+enter',
            'sys_repeat_play': 'ctrl+num_add',
            'sys_float_window': 'alt+num_dot',
        })

        # ==========================================
        # 2. 用户自定义的预设快捷键 (默认为空字典)
        # ==========================================
        self.audio_hotkeys = self.config.get("audio_hotkeys", {})
        self.text_hotkeys = self.config.get("text_hotkeys", {})

        self.presets_text = self.config.get("presets_text", [])

        # ==========================================
        # 3. 后台服务与预处理 (在构建 UI 前执行)
        # ==========================================
        # 初始化多线程池
        self.threadpool = QThreadPool()
        self.threadpool.setMaxThreadCount(4)
        self.last_play_type = None  # 取值：'text' 或 'audio'
        self.last_play_content = None  # 取值：真实的文本字符串 或 预设音频的绝对路径

        # 启动时自动清理历史记录 (依赖于 history_manager 和 presets_text，必须在 UI 生成前执行！)
        self.auto_clear_history = self.config.get("auto_clear_history", False)
        self.perform_auto_clear_history()

        # ==========================================
        # 4. 构建 UI 界面
        # ==========================================
        # 此时所有基础变量均已就绪，_init_ui 可以安全地把它们绑定到复选框、滑块等控件上
        self._init_ui()

        # ==========================================
        # 5. 装填数据与底层监听 (UI 就绪后执行)
        # ==========================================
        # 将数据渲染进刚才画好的 UI 列表控件中
        self.load_presets_text()
        self.load_preset_audio()
        self.load_history_ui()

        # 初始化 TTS 引擎 (可能会有稍微的卡顿，所以放在最后)
        self.init_engine_and_voices()

        # 最后一步：注册全局快捷键 (避免在 UI 和底层没准备好时被触发)
        self._setup_hotkeys()

    # ==========================================
    # UI 布局拆分模块
    # ==========================================
    def _init_ui(self):
        """主 UI 初始化 (加入 QSplitter 实现区域可拖拽)"""
        self.setWindowTitle("我是你的嘴")
        self.setGeometry(100, 100, 550, 750)  # 稍微加宽加高一点，让现代布局有呼吸空间
        self.setWindowIcon(QIcon("resources/icon.png"))
        self.setWindowFlags(Qt.X11BypassWindowManagerHint)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # ==========================================
        # 核心改造 1：主布局加入舒适的留白 (呼吸感)
        # ==========================================
        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(16, 16, 16, 16)  # 四周边缘留白
        root_layout.setSpacing(12)  # 控件间隔

        # ==========================================
        # 核心改造 2：注入局部 QSS (不破坏 qdarktheme 的前提下增强视觉焦点)
        # ==========================================
        self.setStyleSheet("""
            /* 标题文本加粗 */
            QLabel#headerLabel {
                font-weight: bold;
                font-size: 14px;
            }

            /* 强调主操作按钮 (蓝色填充圆角) */
            QPushButton#primaryBtn {
                background-color: #0078D4;
                color: white;
                font-weight: bold;
                font-size: 14px;
                border-radius: 6px;
            }
            QPushButton#primaryBtn:hover {
                background-color: #106EBE;
            }
            QPushButton#primaryBtn:pressed {
                background-color: #005A9E;
            }
            QPushButton#primaryBtn:disabled {
                background-color: #A0CBE8;
            }

            /* 停止/警告类按钮 (浅色红字) */
            QPushButton#dangerBtn {
                color: #D13438;
                font-weight: bold;
                border-radius: 6px;
            }
        """)

        # 创建垂直方向的 QSplitter
        self.main_splitter = QSplitter(Qt.Vertical)
        self.main_splitter.setHandleWidth(6)  # 把拖拽条稍微变宽一点点，更有质感
        root_layout.addWidget(self.main_splitter)

        # 区域 1：顶部控制区 (内部增加 Padding)
        self.top_container = QWidget()
        self.top_layout = QVBoxLayout(self.top_container)
        self.top_layout.setContentsMargins(8, 8, 8, 12)
        self.main_splitter.addWidget(self.top_container)

        # 区域 2：预设列表区
        self.preset_container = QWidget()
        self.preset_layout = QVBoxLayout(self.preset_container)
        self.preset_layout.setContentsMargins(8, 8, 8, 12)
        self.preset_layout.setSpacing(10)
        self.main_splitter.addWidget(self.preset_container)

        # 区域 3：历史记录区
        self.history_container = QWidget()
        self.history_layout = QVBoxLayout(self.history_container)
        self.history_layout.setContentsMargins(8, 8, 8, 8)
        self.history_layout.setSpacing(10)
        self.main_splitter.addWidget(self.history_container)

        # ==========================================
        # 动态切换指针，装配内部组件
        # ==========================================
        self.main_layout = self.top_layout
        self._init_engine_voice_ui()
        self._init_device_ui()
        self._init_settings_ui()
        self._init_text_input_ui()
        self._init_control_buttons_ui()

        self.main_layout = self.preset_layout
        self._init_preset_lists_ui()
        # 【注意】：我已经在这里把你原有的 style_sheet 删掉了，完全交给 qdarktheme 接管列表样式

        self.main_layout = self.history_layout
        self._init_history_ui()

        # 恢复主布局指针，并设置这三个区域的默认高度比例
        self.main_layout = root_layout
        self.main_splitter.setSizes([380, 320, 250])

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
        # 注意：这里改为调用包装好的保存方法
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
        # 解析当前的 rate 配置回填
        initial_speed = 1.0 + float(self.rate.replace('%', '')) / 100
        self.settings_voice_speed_box.setValue(initial_speed)
        self.settings_voice_speed_box.valueChanged.connect(self.on_voice_speed_changed)
        layout.addWidget(self.settings_voice_speed_box)

        layout.addWidget(QLabel("置顶"))
        self.settings_always_on_top_box = QCheckBox()
        self.settings_always_on_top_box.setChecked(False)
        self.settings_always_on_top_box.toggled.connect(self.on_always_on_top_changed)
        layout.addWidget(self.settings_always_on_top_box)

        # ==================== 【新增：TTS音量控制】 ====================
        layout.addWidget(QLabel(" TTS音量:"))
        self.tts_volume_box = QDoubleSpinBox()
        self.tts_volume_box.setRange(0.0, 1.0)
        self.tts_volume_box.setSingleStep(0.1)
        self.tts_volume_box.setDecimals(1)
        self.tts_volume_box.setValue(self.tts_volume)
        self.tts_volume_box.valueChanged.connect(self.on_tts_volume_changed)
        layout.addWidget(self.tts_volume_box)

        # ==================== 【新增：预设音频音量控制】 ====================
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
        self.open_game_mic_box .toggled.connect(self.on_open_game_mic_box_changed)
        layout.addWidget(self.open_game_mic_box)

        # layout.addWidget(QLabel(" 开麦键:"))
        self.btn_set_mic_key = QPushButton(f"[{self.speak_key}]")
        self.btn_set_mic_key.setFixedWidth(80)
        self.btn_set_mic_key.setToolTip("点击设置游戏内语音按键")
        self.btn_set_mic_key.clicked.connect(self.set_mic_key_dialog)
        layout.addWidget(self.btn_set_mic_key)

        layout.addStretch(1)
        self.main_layout.addLayout(layout)

    def _init_device_ui(self):
        layout = QHBoxLayout()
        layout.addWidget(QLabel("输出设备:"))
        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(250)
        self.populate_audio_devices()  # 调用极简版的设备加载
        self.device_combo.currentIndexChanged.connect(self.save_current_config)

        layout.addWidget(self.device_combo)
        layout.addStretch(1)
        self.main_layout.addLayout(layout)

    def _init_text_input_ui(self):
        # 建立一个水平容器来装 标签 和 按钮
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)

        lbl_input = QLabel("输入文本:")
        lbl_input.setObjectName("headerLabel")
        header_layout.addWidget(lbl_input)

        # 将弹簧放在中间，把标签顶在左边，按钮顶在右边 (这样排版最规整好看)
        header_layout.addStretch(1)

        btn_float_input_box = QPushButton("打开悬浮输入框")
        # btn_add_text.setFixedWidth(100)
        btn_float_input_box.clicked.connect(self.open_float_window)
        header_layout.addWidget(btn_float_input_box)

        # 【新增】：在这里实例化“存为预设”按钮
        btn_add_text = QPushButton("存为预设")
        # btn_add_text.setFixedWidth(100)
        btn_add_text.clicked.connect(self.add_current_text_to_presets)
        header_layout.addWidget(btn_add_text)


        btn_sys_hotkeys = QPushButton("全局快捷键")
        # btn_sys_hotkeys.setFixedHeight(28)
        btn_sys_hotkeys.clicked.connect(self.open_sys_hotkey_dialog)
        header_layout.addWidget(btn_sys_hotkeys)

        # 将头部布局加入主布局
        self.main_layout.addLayout(header_layout)

        # 文本输入框保持不变
        self.text_input = QTextEdit()
        self.text_input.installEventFilter(self)
        self.text_input.setMaximumHeight(60)
        self.main_layout.addWidget(self.text_input)

    def _init_preset_lists_ui(self):
        label_layout = QHBoxLayout()

        # --- 预设文本 Header ---
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

        # --- 预设音频 Header ---
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

        # 加入主布局
        label_layout.addWidget(text_header_widget)
        label_layout.addWidget(audio_header_widget)
        self.main_layout.addLayout(label_layout)

        # --- 列表部分保持原样 ---
        list_layout = QHBoxLayout()

        self.preset_text_list = QListWidget()
        # self.preset_text_list.setMaximumHeight(200)
        self.preset_text_list.setUniformItemSizes(True)
        self.preset_text_list.setItemDelegate(HotkeyItemDelegate(self.preset_text_list))
        self.preset_text_list.itemDoubleClicked.connect(self.on_preset_text_double_clicked)
        self.preset_text_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.preset_text_list.customContextMenuRequested.connect(
            lambda pos: self.show_list_context_menu(pos, self.preset_text_list, "text")
        )
        list_layout.addWidget(self.preset_text_list)

        self.preset_audio_list = QListWidget()
        # self.preset_audio_list.setMaximumHeight(200)
        self.preset_audio_list.setUniformItemSizes(True)
        self.preset_audio_list.setItemDelegate(HotkeyItemDelegate(self.preset_audio_list))
        self.preset_audio_list.itemDoubleClicked.connect(self.on_preset_audio_double_clicked)
        self.preset_audio_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.preset_audio_list.customContextMenuRequested.connect(
            lambda pos: self.show_list_context_menu(pos, self.preset_audio_list, "audio")
        )
        list_layout.addWidget(self.preset_audio_list)

        self.main_layout.addLayout(list_layout)

    def _init_control_buttons_ui(self):
        layout = QHBoxLayout()
        layout.addStretch(1)

        self.convert_btn = QPushButton("开始转换和播放")
        self.convert_btn.setObjectName("primaryBtn") # 绑定强调样式
        self.convert_btn.setFixedSize(220, 42) # 高度微调，配合现代化的圆角
        self.convert_btn.clicked.connect(self.convert_text)

        self.stop_btn = QPushButton("停止播放")
        self.stop_btn.setObjectName("dangerBtn") # 绑定警告样式
        self.stop_btn.setFixedSize(220, 42)
        self.stop_btn.clicked.connect(self.stop_playback)

        layout.addWidget(self.convert_btn)
        layout.addSpacing(20) # 两个大按钮中间加一点点弹簧间距，不那么死板
        layout.addWidget(self.stop_btn)
        layout.addStretch(1)
        self.main_layout.addLayout(layout)

    def _init_history_ui(self):
        # --- 历史记录 Header 容器 ---
        history_header_widget = QWidget()
        history_header_layout = QHBoxLayout(history_header_widget)
        history_header_layout.setContentsMargins(0, 0, 0, 0)

        lbl_history = QLabel("历史记录 (双击播放 / 右键):")
        lbl_history.setObjectName("headerLabel")
        history_header_layout.addWidget(lbl_history)
        history_header_layout.addStretch(1)  # 把复选框推到右边

        # 【新增】：启动时自动清理复选框
        self.auto_clear_history_box = QCheckBox("每次启动时自动清理")
        self.auto_clear_history_box.setChecked(self.auto_clear_history)
        self.auto_clear_history_box.toggled.connect(self.on_auto_clear_history_changed)
        history_header_layout.addWidget(self.auto_clear_history_box)

        # 把整个 Header 放入主布局
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

    # ==========================================
    # 核心重构逻辑 (解耦与简化)
    # ==========================================
    def populate_audio_devices(self):
        """使用 AudioManager 极简加载设备"""
        self.device_combo.clear()
        devices = AudioManager.get_output_devices()

        if not devices:
            self.device_combo.addItem("未找到输出设备", -1)
            self.convert_btn.setEnabled(False)
            return

        for device in devices:
            self.device_combo.addItem(device['name'], device['index'])

        last_name = self.config_manager.get("last_device_name")
        target_row = AudioManager.find_device_row_by_name(devices, last_name)

        self.device_combo.setCurrentIndex(max(0, target_row))

    def save_current_config(self):
        """统一保存配置到 ConfigManager"""
        # 防止初始化时触发报错
        if not hasattr(self, 'device_combo'): return

        current_device_name = self.device_combo.currentText()
        if current_device_name == "未找到输出设备":
            current_device_name = None

        current_voice_id = self.voice_combo.currentData()
        if current_voice_id in ("加载失败", "请先选择引擎", None):
            current_voice_id = None

        self.config_manager.save({
            "last_device_name": current_device_name,
            "last_engine": self.current_engine_name,
            "last_voice_id": current_voice_id,
            "rate": self.rate,
            "tts_volume": self.tts_volume,
            "preset_audio_volume": self.preset_audio_volume,
            "speak_key": self.speak_key
        })
        self.current_voice_id = current_voice_id

    # ==========================================
    # 快捷键重构 (策略模式消除 if-elif)
    # ==========================================
    def _setup_hotkeys(self):
        """装载或重启热键系统"""
        # 如果已经存在旧的监听线程，先让它安全退出并销毁
        if hasattr(self, 'hotkey_manager') and self.hotkey_manager.isRunning():
            self.hotkey_manager.stop()

        # 重新实例化一个干净的后台线程
        self.hotkey_manager = HotkeyManager(parent=self)
        self.hotkey_manager.hotkey_triggered.connect(self.handle_hotkey)

        # 把配置字典里的所有快捷键喂给它
        # 2. 注册系统快捷键 (本身就带有 sys_ 前缀，或者直接映射方法)
        for action_id, hotkey in self.sys_hotkeys.items():
            if hotkey:
                # 传入 action_id 让 handle_hotkey 去分发
                self.hotkey_manager.register_hotkey(action_id, hotkey)

        # 3. 注册音频快捷键 (在键名前面动态加上 'audio_' 前缀喂给路由)
        for audio_name, hotkey in self.audio_hotkeys.items():
            if hotkey:
                action_id = f"audio_{audio_name}"
                self.hotkey_manager.register_hotkey(action_id, hotkey)

        # 4. 注册文本快捷键 (动态加上 'text_' 前缀)
        for text_content, hotkey in self.text_hotkeys.items():
            if hotkey:
                action_id = f"text_{text_content}"
                self.hotkey_manager.register_hotkey(action_id, hotkey)

        # 启动线程！新线程的 run() 会接管所有的 RegisterHotKey 操作
        self.hotkey_manager.start()

    def handle_hotkey(self, action_id):
        """前缀路由分发器，处理各种类型的快捷键触发"""
        logging.info(f"触发热键动作: {action_id}")

        # 1. 基础功能路由
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

        # 2. 预设音频路由 (前缀 audio_)
        elif action_id.startswith('audio_'):
            item_name = action_id[6:]  # 切除 'audio_' 前缀
            # 音频的预设依然是字典 {文件名: 文件绝对路径}
            if item_name in getattr(self, 'presets_audio', {}):
                self.play_preset_audio(self.presets_audio[item_name])

        # 3. 预设文本路由 (前缀 text_)
        elif action_id.startswith('text_'):
            item_name = action_id[5:]  # 切除 'text_' 前缀
            # 【修复】：现在 presets_text 是一个列表，且 item_name 就是真实文本
            if item_name in getattr(self, 'presets_text', []):
                self.text_input.setText(item_name)
                self.convert_text()

    def show_list_context_menu(self, pos, list_widget, item_type):
        """全面升级的预设列表右键菜单"""
        item = list_widget.itemAt(pos)
        if not item:
            return

        menu = QMenu()
        bind_action = menu.addAction("🎯 分配 / 修改快捷键")
        unbind_action = menu.addAction("❌ 取消快捷键")
        menu.addSeparator()

        edit_action = None
        if item_type == "text":
            edit_action = menu.addAction("📝 编辑此文本")
            delete_action = menu.addAction("🗑️ 删除此预设")
        else:
            delete_action = menu.addAction("🗑️ 删除此音频文件")

        original_name = item.data(Qt.UserRole + 1)
        action_id = f"{item_type}_{original_name}"
        current_key = self.audio_hotkeys.get(action_id, "")

        if current_key:
            bind_action.setText(f"🎯 修改快捷键 (当前: {current_key})")

        action = menu.exec_(list_widget.mapToGlobal(pos))

        # --- 快捷键操作 ---
        if action == bind_action:
            # ==========================================
            # 1. 【录制前强行缴械】：让底层全局监听器暂时失效，把按键还给系统
            # ==========================================
            if hasattr(self, 'hotkey_manager'):
                self.hotkey_manager.stop()

            dialog = HotkeyBindDialog(current_key, self)
            result = dialog.exec_()  # 阻塞等待，此时用户敲击任何按键都会被顺利捕获

            if result == QDialog.Accepted:
                new_key = dialog.get_hotkey()
                if new_key and new_key != current_key:
                    # 冲突检测
                    # 1. 定义数据源与对应前缀的关系 (sys 本身自带前缀，所以传空字符串)
                    category_map = {
                        "": self.sys_hotkeys,
                        "audio_": self.audio_hotkeys,
                        "text_": self.text_hotkeys
                    }

                    # 2. 极致优雅的一行流：按需生成，找到即停
                    conflict_id = next(
                        (f"{prefix}{k}" for prefix, d in category_map.items() for k, v in d.items()
                         if v == new_key and f"{prefix}{k}" != action_id),
                        None  # 默认返回值
                    )

                    if conflict_id:
                        reply = QMessageBox.warning(
                            self, "快捷键冲突",
                            f"快捷键 [{new_key}] 已被分配。\n是否强制覆盖？",
                            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
                        )
                        if reply == QMessageBox.No:
                            # ==========================================
                            # 【致命排雷】：用户取消覆盖，准备 return 前，必须把快捷键恢复！
                            # ==========================================
                            self._setup_hotkeys()
                            return

                        self.update_single_hotkey(conflict_id, "")

                # 更新当前快捷键 (这个方法内部会自动调用 self._setup_hotkeys() 进行重新武装)
                self.update_single_hotkey(action_id, new_key)

            else:
                # ==========================================
                # 2. 【录制取消恢复】：用户点了取消或按 Esc 关了弹窗，把原有的快捷键恢复回来
                # ==========================================
                self._setup_hotkeys()

        elif action == unbind_action:
            self.update_single_hotkey(action_id, "")

        # --- 数据管理操作 ---
        elif edit_action and action == edit_action:
            current_true_text = item.data(Qt.UserRole)
            new_text, ok = QInputDialog.getMultiLineText(self, "编辑预设文本", "请输入新的文本:", current_true_text)
            if ok and new_text.strip():
                new_text = new_text.strip()
                if new_text != current_true_text:
                    # 替换列表中的文本
                    if current_true_text in self.presets_text:
                        idx = self.presets_text.index(current_true_text)
                        self.presets_text[idx] = new_text
                    else:
                        self.presets_text.append(new_text)

                    # 同步转移快捷键配置
                    if action_id in self.hotkeys_map:
                        hk = self.hotkeys_map.pop(action_id)
                        self.hotkeys_map[f"text_{new_text}"] = hk

                    self.config_manager.save({"presets_text": self.presets_text, "hotkeys": self.hotkeys_map})
                    self._setup_hotkeys()
                    self.load_presets_text()


        elif action == delete_action:
            type_name = "文本" if item_type == "text" else "音频"
            reply = QMessageBox.question(self, "确认删除", f"确定要删除此预设{type_name}吗？",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                if item_type == "text":
                    current_true_text = item.data(Qt.UserRole)
                    if current_true_text in self.presets_text:
                        self.presets_text.remove(current_true_text)
                    self.config_manager.save({"presets_text": self.presets_text})
                    self.update_single_hotkey(action_id, "")
                else:
                    # 【核心修改】：智能音频删除逻辑
                    file_path = item.data(Qt.UserRole)
                    original_name = item.data(Qt.UserRole + 1)
                    if original_name in getattr(self, 'linked_audio', {}):
                        # 如果是外部引用文件：只删记录，绝不碰原文件
                        self.linked_audio.pop(original_name, None)
                        self.config_manager.save({"linked_audio": self.linked_audio})
                        self.update_single_hotkey(action_id, "")
                        self.load_preset_audio()
                        QMessageBox.information(self, "成功", "已移除该音频的引用记录（您的原文件未被删除）。")
                    else:
                        # 如果是复制进内部的文件：物理删除
                        if file_path and os.path.exists(file_path):
                            try:
                                os.remove(file_path)
                                self.update_single_hotkey(action_id, "")
                                self.load_preset_audio()
                                QMessageBox.information(self, "成功", "音频文件已从软件库中彻底删除。")
                            except Exception as e:
                                QMessageBox.critical(self, "错误", f"删除失败，文件可能被占用:\n{e}")

    def add_current_text_to_presets(self):
        """将当前输入框的内容存为预设"""
        text = self.text_input.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "提示", "请先在下方输入需要保存的文本。")
            return

        if text not in self.presets_text:
            # 插入到列表最前面
            self.presets_text.insert(0, text)
            self.config_manager.save({"presets_text": self.presets_text})
            self.load_presets_text()
            QMessageBox.information(self, "成功", "已成功保存为预设文本！")
        else:
            QMessageBox.information(self, "提示", "该预设已存在。")

    def show_history_context_menu(self, pos):
        """历史记录的专属右键菜单"""
        item = self.history_list.itemAt(pos)
        if not item:
            return

        menu = QMenu()
        play_action = menu.addAction("▶️ 播放此记录")
        preset_action = menu.addAction("⭐ 提升为预设文本")
        menu.addSeparator()
        delete_action = menu.addAction("🗑️ 删除此记录 (同步删除音频)")

        action = menu.exec_(self.history_list.mapToGlobal(pos))

        if action == play_action:
            self.play_history(item)

        elif action == preset_action:
            # 从复杂的拼接字符串里拆分出原本的文本
            parts = item.text().split(self.split_sign)
            if parts:
                text = parts[0]
                if text not in self.presets_text:
                    self.presets_text.insert(0, text)
                    self.config_manager.save({"presets_text": self.presets_text})
                    self.load_presets_text()
                    QMessageBox.information(self, "成功", "已成功添加到预设文本！")
                else:
                    QMessageBox.information(self, "提示", "该预设已存在。")

        elif action == delete_action:
            reply = QMessageBox.question(self, "确认删除", "确定要删除这条历史记录及硬盘上的关联音频文件吗？",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                file_path = item.data(Qt.UserRole)

                # 1. 从内存中的历史记录里抹除
                for i, record in enumerate(self.history_manager.history_data):
                    if record.get("path") == file_path:
                        self.history_manager.history_data.pop(i)
                        break
                self.history_manager.save()

                # 2. 物理删除音频文件
                if file_path and os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except Exception as e:
                        logging.warning(f"删除历史音频文件失败: {e}")

                # 3. 动态从 UI 列表中抽走这一行
                row = self.history_list.row(item)
                self.history_list.takeItem(row)

    def update_single_hotkey(self, action_id, new_key_str):
        """实时更新单个快捷键，分类保存，重启底层服务，并智能刷新 UI"""

        # 1. 路由分发：根据前缀决定修改哪个字典，以及存什么名字
        if action_id.startswith('sys_'):
            target_dict = getattr(self, 'sys_hotkeys', {})
            dict_name = "sys_hotkeys"
            item_name = action_id  # 系统快捷键保留全名作为 key

        elif action_id.startswith('audio_'):
            target_dict = getattr(self, 'audio_hotkeys', {})
            dict_name = "audio_hotkeys"
            item_name = action_id[6:]  # 切除 'audio_' 前缀，配置里只存纯文件名

        elif action_id.startswith('text_'):
            target_dict = getattr(self, 'text_hotkeys', {})
            dict_name = "text_hotkeys"
            item_name = action_id[5:]  # 切除 'text_' 前缀，配置里只存纯文本

        else:
            logging.error(f"未知的快捷键类型，无法更新: {action_id}")
            return

        # 2. 更新对应字典的数据
        if new_key_str:
            target_dict[item_name] = new_key_str
        else:
            target_dict.pop(item_name, None)

        # 3. 立即保存变动的那个字典到 config.json
        self.config_manager.save({dict_name: target_dict})
        logging.info(f"已分类更新热键保存 [{dict_name}]: {item_name} -> {new_key_str}")

        # 4. 重启热键系统 (让新按键生效)
        self._setup_hotkeys()

        # 5. 【究极进化】：给 UI 刷新加上呼吸感动画！
        if dict_name != "sys_hotkeys":
            if dict_name == "text_hotkeys":
                # 把 load_presets_text 当作任务扔进动画引擎
                self._animate_widget_update(self.preset_text_list, self.load_presets_text)
            elif dict_name == "audio_hotkeys":
                self._animate_widget_update(self.preset_audio_list, self.load_preset_audio)

    # ==========================================
    # 批量清除快捷键逻辑
    # ==========================================
    def clear_text_hotkeys(self):
        """清除所有文本快捷键并刷新列表"""
        if self._bulk_clear_hotkeys_by_prefix("text_"):
            self.load_presets_text()

    def clear_audio_hotkeys(self):
        """清除所有音频快捷键并刷新列表"""
        if self._bulk_clear_hotkeys_by_prefix("audio_"):
            self.load_preset_audio()

    def _bulk_clear_hotkeys_by_prefix(self, prefix: str) -> bool:
        """
        根据前缀批量清除快捷键字典的内部实现
        返回 True 表示执行了清除，返回 False 表示取消或无需清除
        """
        # 1. 路由分发：精确定位目标字典和保存键名
        if prefix == "text_":
            target_dict = getattr(self, 'text_hotkeys', {})
            dict_name = "text_hotkeys"
            type_str = "文本"
        elif prefix == "audio_":
            target_dict = getattr(self, 'audio_hotkeys', {})
            dict_name = "audio_hotkeys"
            type_str = "音频"
        else:
            logging.error(f"未知的批量清除前缀: {prefix}")
            return False

        # 2. 检查到底有没有东西可以删
        if not target_dict:
            QMessageBox.information(self, "提示", f"当前分类下没有绑定任何{type_str}快捷键。")
            return False

        # 3. 增加安全二次确认
        count = len(target_dict)
        reply = QMessageBox.question(self, '确认清除',
                                     f"确定要清除所有预设{type_str}的快捷键吗？\n(将清除 {count} 个按键绑定，不会删除文件)",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            # 4. 暴力美学：直接清空整个专属字典！
            target_dict.clear()

            # 5. 分类保存并重启底层 API
            self.config_manager.save({dict_name: target_dict})
            self._setup_hotkeys()

            # 6. 【关键体验】：只刷新对应的 UI 列表，让界面上的快捷键标签瞬间消失
            if prefix == "text_":
                self.load_presets_text()
            else:
                self.load_preset_audio()

            logging.info(f"已批量清除 {count} 个 '{prefix}' 的快捷键")
            return True

        return False


    def toggle_mic(self):
        self.open_game_mic_box.toggle()



    # ==========================================
    # 引擎与音色管理逻辑
    # ==========================================
    def init_engine_and_voices(self):
        """初始化引擎选择框，并加载音色"""
        cached_engine_name = self.current_engine_name
        self.engine_combo.blockSignals(True)  # 防止初始化时触发多次 change 事件
        self.engine_combo.clear()

        for name in self.AVAILABLE_ENGINES.keys():
            self.engine_combo.addItem(name)

        target_index = -1
        if cached_engine_name in self.AVAILABLE_ENGINES:
            target_index = list(self.AVAILABLE_ENGINES.keys()).index(cached_engine_name)

        if target_index != -1:
            self.engine_combo.setCurrentIndex(target_index)
        elif self.AVAILABLE_ENGINES:
            self.current_engine_name = list(self.AVAILABLE_ENGINES.keys())[0]
            self.engine_combo.setCurrentIndex(0)

        self.engine_combo.blockSignals(False)
        self.engine_selection_changed()

    def engine_selection_changed(self):
        """当引擎选择改变时，更新音色列表并保存配置"""
        selected_name = self.engine_combo.currentText()
        engine_class = self.AVAILABLE_ENGINES.get(selected_name)

        if engine_class:
            self.active_engine = engine_class()
            self.current_engine_name = selected_name
            self.populate_voices_async()
            self.save_current_config()
        else:
            if selected_name:
                QMessageBox.warning(self, "错误", f"未知的 TTS 引擎: {selected_name}")
            self.voice_combo.clear()
            self.voice_combo.addItem("请先选择引擎", None)

    def populate_voices_async(self):
        """启动后台线程加载音色，防止 GUI 阻塞"""
        if not self.active_engine:
            self.voice_combo.clear()
            self.voice_combo.addItem("请先选择引擎", None)
            return

        self.voice_combo.clear()
        self.voice_combo.addItem(f"加载 {self.active_engine.name} 音色中...", None)
        self.voice_combo.setEnabled(False)

        loader_worker = VoiceLoaderWorker(self.active_engine)
        loader_worker.signals.finished.connect(self.handle_voices_loaded)
        loader_worker.signals.error.connect(self.handle_voices_error)
        self.threadpool.start(loader_worker)

    def handle_voices_loaded(self, voices: list):
        """音色加载成功后，更新 ComboBox"""
        cache_voice_id = self.current_voice_id
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
                if cache_voice_id == voice["id"]:
                    target_index = i

            if target_index != -1:
                self.voice_combo.setCurrentIndex(target_index)
            else:
                self.voice_combo.setCurrentIndex(0)
                self.current_voice_id = self.voice_combo.currentData()

        self.voice_combo.blockSignals(False)
        self.save_current_config()

    def handle_voices_error(self, message: str):
        self.voice_combo.clear()
        self.voice_combo.addItem("加载失败", None)
        self.voice_combo.setEnabled(True)
        self.current_voice_id = None
        self.save_current_config()
        QMessageBox.critical(self, "音色加载错误", message)

    # ==========================================
    # 预设与历史记录加载逻辑
    # ==========================================
    def load_presets_text(self):
        """加载预设文本，智能截断超长文本并分离快捷键渲染"""
        self.preset_text_list.clear()

        # ==========================================
        # 1. 核心魔法：一步到位的完美排序
        # ==========================================
        sorted_texts = sorted(
            self.presets_text,
            key=lambda t: self._get_hotkey_sort_weight(t, self.text_hotkeys)
        )


        for text in sorted_texts:
            hotkey = self.text_hotkeys.get(text, "")

            # 视觉处理：单行显示与超长截断
            display_name = text.replace('\n', ' ')
            if len(display_name) > 30:
                display_name = display_name[:28] + "..."

            # 直接创建 Item 并挂载数据
            item = QListWidgetItem(display_name)  # 明面上只放干净的名字
            item.setToolTip(text)  # 鼠标悬浮显示完整文本
            item.setData(Qt.UserRole, text)  # 实际用于转换的完整文本
            item.setData(Qt.UserRole + 1, text)  # 原始文本标识符
            item.setData(Qt.UserRole + 2, hotkey)  # 【暗藏】：把快捷键塞给 Delegate

            self.preset_text_list.addItem(item)

    def load_preset_audio(self):
        """加载音频预设列表，并根据快捷键智能排序"""
        self.presets_audio = self.get_preset_audio_dict()

        if not hasattr(self, 'presets_audio') or not self.presets_audio:
            return

        self.preset_audio_list.clear()

        # ==========================================
        # 【核心魔法】：一句话完成所有复杂排序！
        # ==========================================
        sorted_audio_names = sorted(
            self.presets_audio.keys(),
            key=lambda name: self._get_hotkey_sort_weight(name, self.audio_hotkeys)
        )

        # 遍历排好序的名字，直接生成 UI
        for name in sorted_audio_names:
            path = self.presets_audio[name]
            hotkey = self.audio_hotkeys.get(name, "")

            # 创建列表项
            item = QListWidgetItem(name)  # 明面上只放干净的名字
            item.setData(Qt.UserRole, str(path))
            item.setData(Qt.UserRole + 1, name)
            item.setData(Qt.UserRole + 2, hotkey)  # 藏好快捷键给 Delegate 画标签

            self.preset_audio_list.addItem(item)


    def get_preset_audio_dict(self) -> dict:
        """扫描预设文件夹，并合并外部引用的音频"""
        AUDIO_EXTENSIONS = {'.mp3', '.wav', '.ogg', '.flac', '.aac', '.m4a', '.wma'}

        if getattr(sys, 'frozen', False):
            base_dir = Path(sys.executable).parent
        else:
            base_dir = Path(__file__).resolve().parent.parent

        preset_audio_dir = base_dir / 'preset_audio'
        audio_dict = {}

        # 1. 扫描物理文件夹
        if preset_audio_dir.is_dir():
            for item in preset_audio_dir.iterdir():
                if item.is_file() and item.suffix.lower() in AUDIO_EXTENSIONS:
                    audio_dict[item.name] = str(item.resolve())
        else:
            # 如果没文件夹就顺手建一个，防止复制时报错
            preset_audio_dir.mkdir(parents=True, exist_ok=True)

        # 2. 合并外部引用的文件（并自动清理已经不存在的死链）
        keys_to_remove = []
        for name, path in self.linked_audio.items():
            if os.path.exists(path):
                audio_dict[name] = path
            else:
                keys_to_remove.append(name)

        if keys_to_remove:
            for k in keys_to_remove:
                self.linked_audio.pop(k, None)
            self.config_manager.save({"linked_audio": self.linked_audio})

        return audio_dict

    def load_history_ui(self):
        """从 HistoryManager 加载数据到 UI 列表"""
        history_data = self.history_manager.load()
        self.history_list.clear()

        for record in history_data:
            display_text = f'{record["text"]}{self.split_sign}{record.get("voice_engine", "Unknown")}{self.split_sign}{record.get("rate", self.rate)}{self.split_sign}{record.get("voice_id", "Unknown")}'
            item = QListWidgetItem(display_text)
            item.setData(Qt.UserRole, record["path"])
            self.history_list.insertItem(0, item)

    def set_mic_key_dialog(self):
        # 直接复用剥离出去的完美录入组件
        dialog = HotkeyBindDialog(self.speak_key, self)
        dialog.setWindowTitle("设置游戏内开麦按键")
        if dialog.exec_() == QDialog.Accepted:
            new_key = dialog.get_hotkey()
            if new_key:
                # 因为游戏开麦键绝大多数是单键，如果有玩家丧心病狂地录了组合键(如ctrl+v)
                # 也没关系，底层 keyboard_injector 也能防呆。
                self.speak_key = new_key
                self.btn_set_mic_key.setText(f"[{self.speak_key}]")
                self.save_current_config()

    def open_float_window(self):
        # 确保只实例化一次（单例模式的做法），避免重复点击弹出多个窗口
        if self.float_window is None:
            self.float_window = FloatInputWindow()
            # 【核心】连接子窗口的自定义信号到主程序的处理函数
            self.float_window.text_submitted.connect(self.handle_input_task)
            self.float_window.open_mic_submitted.connect(self.handle_float_window_mic_task)
            self.float_window.open_game_mic_box.setChecked(self.mic_statu)

        # 显示窗口并将其激活到前台
        self.float_window.show()
        self.float_window.raise_()  # 确保置顶
        self.float_window.activateWindow()
        self.float_window.input_box.setFocus()
        self.float_window.input_box.selectAll()

    def handle_input_task(self, text):
        """这个函数会在子窗口按下回车时触发"""
        print(f"[主程序] 收到来自悬浮窗的文本: {text}")
        self.text_input.setText(text)
        self.convert_text()
        # 在这里写你接下来的业务逻辑（比如发送网络请求、处理文件等）
        # ...

    def handle_float_window_mic_task(self, checked):
        self.open_game_mic_box.setChecked(checked)
        self.mic_statu = checked

    def open_sys_hotkey_dialog(self):
        """打开系统快捷键设置面板"""
        if hasattr(self, 'hotkey_manager'):
            self.hotkey_manager.stop()

        dialog = SystemHotkeyDialog(self.sys_hotkeys, self)

        if dialog.exec_() == QDialog.Accepted:
            new_sys_keys = dialog.get_new_hotkeys()
            changed = False
            for action_id, new_key in new_sys_keys.items():
                old_key = self.sys_hotkeys.get(action_id, "")
                if new_key != old_key:
                    # 这个方法最后会调用 _setup_hotkeys() 进行恢复
                    self.update_single_hotkey(action_id, new_key)
                    changed = True

            if changed:
                QMessageBox.information(self, "成功", "全局系统快捷键已更新！")
            else:
                # 用户点了确定，但是没做任何修改，也要恢复
                self._setup_hotkeys()
        else:
            # 【新增】：用户点了取消，恢复原来的监听
            self._setup_hotkeys()

    # ==========================================
    # 转换、播放与清理核心业务
    # ==========================================
    def check_text_in_history(self, text: str):
        """检查文本是否已在历史记录中，返回 (bool, QListWidgetItem)"""
        for index in range(self.history_list.count()):
            item = self.history_list.item(index)
            parts = item.text().split(self.split_sign)
            if len(parts) == 4:
                item_text, item_engine, item_rate, item_voice_id = parts
                # logging.info(f"{item_rate,self.rate}")
                if (item_text == text and
                        item_rate == self.rate and
                        item_engine == self.current_engine_name and
                        item_voice_id == str(self.voice_combo.currentData())):
                    return True, item
        return False, None

    def _start_worker_task(self, text, file_path, is_history_play, is_convert=False):
        """公共的 Worker 装配与启动器"""
        device_index = self.device_combo.currentData()
        if device_index == -1 or device_index is None:
            QMessageBox.warning(self, "警告", "请先选择一个输出设备。")
            return False
        if not self.active_engine:
            QMessageBox.warning(self, "警告", "请先选择一个 TTS 引擎。")
            return False

        # 实例化 Worker
        worker = TTSWorker(self.rate, text, device_index, file_path,
                           tts_engine=self.active_engine,
                           is_history_play=is_history_play)

        # 统一注入各种参数
        worker.set_tts_volume(self.tts_volume)
        worker.set_preset_audio_volume(self.preset_audio_volume)
        worker.set_open_game_mic(self.mic_statu)
        worker.set_speak_key(self.speak_key)

        # 挂载到当前工作句柄（修复了你原来 play_history 里的 bug）
        self.current_worker = worker

        # 统一绑定错误信号
        worker.signals.error_signal.connect(self.handle_tts_error)

        # 如果是新转换的任务，单独绑定完成信号以保存历史
        if is_convert:
            selected_voice_id = self.voice_combo.currentData()
            worker.signals.finished_signal.connect(
                lambda t, p: self.handle_tts_finished_slot(t, p, self.current_engine_name, selected_voice_id)
            )

        # 启动线程
        self.threadpool.start(worker)
        return True
    def get_input_text(self):
        return self.text_input.toPlainText().strip()


    def convert_text(self):
        """启动 TTS 转换和播放任务"""
        self.stop_playback()

        self.window_manager.focus_game_if_needed(self.mic_statu)

        text = self.get_input_text()

        self.last_play_type = 'text'
        self.last_play_content = text

        in_history, item = self.check_text_in_history(text)
        if in_history and item is not None:
            logging.info('发现历史记录，直接播放')
            self.play_history(item)
            return

        if not text:
            QMessageBox.warning(self, "警告", "请输入要转换的文本。")
            return

        selected_voice_id = self.voice_combo.currentData()
        if selected_voice_id is None:
            QMessageBox.warning(self, "警告", "当前引擎无可用音色，请更换引擎或检查依赖。")
            return

        # 准备音频存储路径
        self.AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        filename_base = f"audio_{int(time.time())}.wav"
        audio_filename = str((self.AUDIO_DIR / filename_base).resolve())

        # 设置音色并更新按钮状态
        self.active_engine.set_voice(selected_voice_id)
        self.convert_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        # 调用公共启动器
        self._start_worker_task(text=text, file_path=audio_filename,
                                is_history_play=False, is_convert=True)

    def play_history(self, item):
        scrollbar = self.history_list.verticalScrollBar()
        current_pos = scrollbar.value()

        self.stop_playback()

        self.window_manager.focus_game_if_needed(self.mic_statu)

        file_path = item.data(Qt.UserRole)

        if not file_path or not Path(file_path).exists():
            QMessageBox.warning(self, "警告", "音频文件未找到，可能已被删除。")
            return

        # 调用公共启动器
        self._start_worker_task(text="", file_path=file_path,
                                is_history_play=True, is_convert=False)

        self.qlist_scrollbar_recover_pos(scrollbar, current_pos)

    def repeat_last_play(self):
        """系统快捷键调用：模拟用户重新触发上一次的动作"""
        if not self.last_play_type:
            logging.warning("没有可重复播放的记录！")
            return

        logging.info(f"🔄 触发重复播放: [{self.last_play_type}] -> {self.last_play_content}")

        if self.last_play_type == 'text':
            # 1. 自动把上次的文字填入输入框 (视觉反馈拉满)
            self.text_input.setText(self.last_play_content)
            # 2. 直接走完整的 TTS 转换/播放流程
            self.convert_text()

        elif self.last_play_type == 'audio':
            # 1. 检查物理文件还在不在
            if not os.path.exists(self.last_play_content):
                logging.warning(f"无法重复播放，原文件已丢失: {self.last_play_content}")
                return
            # 2. 直接走完整的本地音频播放流程
            self.play_preset_audio(self.last_play_content)

    def play_preset_audio(self, pth: str):
        """播放预设音频"""
        self.stop_playback()

        self.window_manager.focus_game_if_needed(self.mic_statu)

        # 调用公共启动器
        self.last_play_type = 'audio'
        self.last_play_content = pth
        self._start_worker_task(text="", file_path=pth,
                                is_history_play=True, is_convert=False)

    def stop_playback(self):
        if self.current_worker:
            self.current_worker.stop()

    def clear_all_data(self):
        """清空所有历史记录和生成的音频文件 (委托给 Manager)"""
        reply = QMessageBox.question(self, '确认清理',
                                     "这将清空所有历史记录，并删除所有生成的音频文件。您确定吗？",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            deleted_count, failed_count = self.history_manager.clear_all()
            self.history_list.clear()
            msg = f"清理完成！\n成功删除音频: {deleted_count} 个"
            if failed_count > 0:
                msg += f"\n失败: {failed_count} 个(可能文件已丢失或无权限)"
            QMessageBox.information(self, "清理结果", msg)

    def import_preset_audio(self):
        # 1. 打开多选文件对话框
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "选择要导入的音频文件", "",
            "Audio Files (*.mp3 *.wav *.ogg *.flac *.aac *.m4a *.wma);;All Files (*)"
        )

        if not file_paths:
            return

        # 2. 弹窗询问导入方式
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("选择导入方式")
        msg_box.setText(f"已选择 {len(file_paths)} 个音频文件。\n\n请选择导入模式：\n\n"
                        "📦【复制文件】：将文件拷贝到软件内部统一管理（原文件被删也不影响）。\n"
                        "🔗【仅存引用】：不移动原文件，仅记录路径（节省硬盘空间）。")

        btn_copy = msg_box.addButton("📦 复制文件", QMessageBox.AcceptRole)
        btn_link = msg_box.addButton("🔗 仅存引用", QMessageBox.AcceptRole)
        btn_cancel = msg_box.addButton("取消", QMessageBox.RejectRole)
        msg_box.exec_()

        clicked_button = msg_box.clickedButton()
        if clicked_button == btn_cancel:
            return

        # 获取基础目录
        if getattr(sys, 'frozen', False):
            base_dir = Path(sys.executable).parent
        else:
            base_dir = Path(__file__).resolve().parent.parent
        preset_audio_dir = base_dir / 'preset_audio'

        success_count = 0
        for path in file_paths:
            path_obj = Path(path)
            file_name = path_obj.name

            if clicked_button == btn_copy:
                target_path = preset_audio_dir / file_name
                try:
                    shutil.copy2(path, target_path)
                    # 如果原本在外部引用里有同名文件，把它覆盖/清除掉
                    if file_name in self.linked_audio:
                        self.linked_audio.pop(file_name, None)
                    success_count += 1
                except Exception as e:
                    logging.error(f"复制文件失败: {e}")

            elif clicked_button == btn_link:
                self.linked_audio[file_name] = path
                success_count += 1

        # 如果修改了引用字典，则保存配置
        self.config_manager.save({"linked_audio": self.linked_audio})
        self.load_preset_audio()  # 刷新UI列表
        QMessageBox.information(self, "导入完成", f"成功导入 {success_count} 个音频文件！")

        # ==========================================
        # 历史记录自动清理逻辑
        # ==========================================

    def perform_auto_clear_history(self):
        """启动时自动清理非预设的临时历史记录及关联的音频文件"""

        # 1. 检查开关状态
        if not getattr(self, 'auto_clear_history', False):
            return

        records_to_keep = []
        files_deleted = 0
        records_deleted = 0

        # 2. 遍历历史记录
        for record in self.history_manager.history_data:
            # 【核心修复】：千万不要用 record["text"]，一旦某条老历史记录缺少这个键，程序会直接抛出 KeyError 并中断执行！
            # 改用 .get() 方法，即使没有这个键也会安全返回空字符串。
            text = record.get("text", "")
            file_path = record.get("path", "")


            # 白名单检查
            if text in self.presets_text:
                records_to_keep.append(record)
            else:
                # 不在预设里，需要删除
                records_deleted += 1
                if file_path and os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                        files_deleted += 1
                    except Exception as e:
                        logging.error(f"   --> ❌ 结果: 物理文件删除失败 (可能被占用): {e}")
                else:
                    logging.info("   --> 👻 结果: 物理文件已不存在，仅清除记录。")

        # 3. 更新并保存
        if records_deleted > 0:
            self.history_manager.history_data = records_to_keep
            self.history_manager.save()
            logging.info(
                f"清理完成：移除了 {records_deleted} 条记录，物理删除了 {files_deleted} 个文件")
        # else:
        #     logging.info("======== 🆗 清理完成：没有发现需要被清理的临时记录 ========")


    def on_auto_clear_history_changed(self, checked):
        """复选框状态改变时，保存到配置文件"""
        self.auto_clear_history = checked
        self.config_manager.save({"auto_clear_history": self.auto_clear_history})

    def _get_hotkey_sort_weight(self, item_name: str, hotkeys_dict: dict) -> tuple:
        """
        生成快捷键排序权重元组。
        排序规则：有快捷键的置顶 -> 按修饰键(Ctrl<Alt<Shift) -> 按数字(1) -> 按字母(2) -> 按符号(3)
        """
        hotkey_str = hotkeys_dict.get(item_name, "")

        # 0. 如果没有快捷键，直接打入冷宫 (第一权重给 1，有快捷键的给 0)
        if not hotkey_str:
            return (1, 0, 0, "", item_name)

        parts = hotkey_str.lower().split('+')
        modifiers = [p for p in parts if p in ('ctrl', 'alt', 'shift', 'win')]
        main_keys = [p for p in parts if p not in ('ctrl', 'alt', 'shift', 'win')]
        main_key = main_keys[0] if main_keys else ""

        # 1. 修饰键权重 (利用二进制位移，Ctrl最优先，组合键累加)
        mod_score = 0
        if 'ctrl' in modifiers: mod_score += 1
        if 'alt' in modifiers: mod_score += 2
        if 'shift' in modifiers: mod_score += 4
        if 'win' in modifiers: mod_score += 8

        # 2. 主键分类 (1=数字, 2=字母, 3=其他符号)
        # 兼容普通数字 '1' 和小键盘数字 'num1'
        if main_key.isdigit() or (main_key.startswith('num') and main_key.replace('num', '').isdigit()):
            category = 1
        elif len(main_key) == 1 and main_key.isalpha():
            category = 2
        else:
            category = 3  # 包含 enter, space, pagedown, num_add 等

        # 返回五维比较元组
        return (0, mod_score, category, main_key, item_name)
    # ==========================================
    # 辅助事件与槽函数
    # ==========================================
    def handle_tts_finished_slot(self, text, file_path, engine_name, voice_id):
        self.convert_btn.setEnabled(True)
        self.current_worker = None

        # 更新 UI
        display_text = f"{text}{self.split_sign}{engine_name}{self.split_sign}{self.rate}{self.split_sign}{voice_id if voice_id else 'Default'}"
        item = QListWidgetItem(display_text)
        item.setData(Qt.UserRole, file_path)
        self.history_list.insertItem(0, item)

        # 交给 Manager 统一保存
        self.history_manager.add_record(text, file_path, self.rate, engine_name, voice_id)

    def handle_tts_error(self, message):
        self.convert_btn.setEnabled(True)
        self.current_worker = None
        QMessageBox.critical(self, "TTS 错误", message)

    def on_preset_text_double_clicked(self, item):
        # 1. 记下当前滚动条位置
        scrollbar = self.preset_text_list.verticalScrollBar()
        current_pos = scrollbar.value()

        # 原来的业务逻辑
        text = item.data(Qt.UserRole)
        if text:
            self.text_input.setText(text)
            self.convert_text()

        self.qlist_scrollbar_recover_pos(scrollbar,current_pos)

    def on_preset_audio_double_clicked(self, item):
        scrollbar = self.preset_audio_list.verticalScrollBar()
        current_pos = scrollbar.value()

        path = item.data(Qt.UserRole)
        if path:
            self.play_preset_audio(path)

        self.qlist_scrollbar_recover_pos(scrollbar,current_pos)

    def qlist_scrollbar_recover_pos(self, scrollbar, position):
        """
        在 0.5 秒内持续锁定滚动条位置，强行对抗 Qt 底层的延迟重绘与自动滚动
        """
        # 直接以 scrollbar 为父对象创建定时器，确保它不会被 Python 的垃圾回收机制吃掉
        timer = QTimer(scrollbar)
        timer.setInterval(10)  # 每 10 毫秒检查一次

        # 用列表包装计数器，这样才能在内部函数（闭包）中修改它的值
        tick_count = [0]

        def enforce_position():
            tick_count[0] += 1

            # 一旦发现位置不对，立刻强行按回去
            if scrollbar.value() != position:
                scrollbar.setValue(position)

            # 50 次 * 10 毫秒 = 500 毫秒 (0.5 秒)
            if tick_count[0] >= 50:
                timer.stop()
                timer.deleteLater()  # 功成身退，销毁自己，不留内存垃圾

        # 绑定并启动循环检查
        timer.timeout.connect(enforce_position)
        timer.start()

    def on_voice_speed_changed(self, value):
        val = int(value * 100)
        if val >= 100:
            self.rate = f'+{val - 100}%'
        else:
            self.rate = f'-{100 - val}%'
        self.save_current_config()

    def on_tts_volume_changed(self, value):
        self.tts_volume = value
        self.save_current_config()

    def on_preset_audio_volume_changed(self, value):
        self.preset_audio_volume = value
        self.save_current_config()

    def on_always_on_top_changed(self):
        if self.settings_always_on_top_box.isChecked():
            self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.X11BypassWindowManagerHint)
        else:
            self.setWindowFlags(Qt.X11BypassWindowManagerHint)
        self.show()  # 更新 flags 后必须重新 show()

    def on_open_game_mic_box_changed(self):
        self.mic_statu = self.open_game_mic_box.isChecked()
        if self.float_window:
            self.float_window.open_game_mic_box.setChecked(self.open_game_mic_box.isChecked())

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
        """切换浮动输入窗口的显示/隐藏状态，并保证焦点在输入框"""
        if not hasattr(self, 'float_window') or self.float_window is None:
            self.open_float_window()

        fw = self.float_window  # 简写，提高可读性
        if fw.isMinimized():
            fw.showNormal()
        elif fw.isVisible() and fw.input_box.hasFocus():
            fw.hide()
            return  # 隐藏后直接返回
        else:
            fw.show()

        # 确保窗口在前台并获得焦点（仅当显示时）
        fw.raise_()
        fw.activateWindow()

        # 重点优化：检查输入框是否已有焦点，没有才设置
        if not fw.input_box.hasFocus():
            fw.input_box.setFocus()
        fw.input_box.selectAll()



    def _animate_widget_update(self, widget, update_func):
        """给指定的控件更新添加丝滑的淡出淡入过渡动画"""
        # 1. 给控件挂载透明度特效
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)

        # 2. 第一段动画：极速淡出 (100毫秒)
        self.anim_out = QPropertyAnimation(effect, b"opacity")
        self.anim_out.setDuration(100)
        self.anim_out.setStartValue(1.0)
        self.anim_out.setEndValue(0.0)

        # 3. 核心机制：当淡出完成(全黑)时，悄悄替换数据，然后再淡入
        def on_fade_out_finished():
            update_func()  # 执行真正的列表加载逻辑 (此时用户看不见跳变)

            # 第二段动画：柔和淡入 (150毫秒)
            self.anim_in = QPropertyAnimation(effect, b"opacity")
            self.anim_in.setDuration(150)
            self.anim_in.setStartValue(0.0)
            self.anim_in.setEndValue(1.0)
            self.anim_in.start()

        # 绑定淡出完成的信号
        self.anim_out.finished.connect(on_fade_out_finished)

        # 启动淡出！
        self.anim_out.start()

    def eventFilter(self, obj, event):
        """输入框回车键事件拦截"""
        if obj == self.text_input and event.type() == QEvent.KeyPress:
            key = event.key()
            modifiers = event.modifiers()
            if key in (Qt.Key_Return, Qt.Key_Enter):
                if modifiers & Qt.ShiftModifier:
                    return False
                else:
                    self.convert_text()
                    return True
        return super().eventFilter(obj, event)

    def closeEvent(self, event):
        """安全关闭释放资源"""
        if self.current_worker:
            self.stop_playback()
        self.hotkey_manager.stop()
        self.threadpool.waitForDone()
        event.accept()