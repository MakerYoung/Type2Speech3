# ui/components/float_input_window.py
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                             QLineEdit, QSlider, QCheckBox, QLabel,
                             QPushButton, QFrame, QSizeGrip, QSizePolicy,
                             QTextEdit)
from PyQt5.QtCore import pyqtSignal, Qt, QPoint


class FloatInputWindow(QWidget):
    text_submitted = pyqtSignal(str)
    open_mic_submitted = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.dragPos = None
        self.init_ui()

    def init_ui(self):
        # 默认无边框、背景透明
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setGeometry(100, 850, 350, 85)
        # self.resize(500, 100)
        self.setMinimumSize(350, 85)
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)


        # 主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- 背景容器 ---
        self.bg_frame = QFrame(self)
        self.bg_frame.setObjectName("BgFrame")
        self.bg_frame.setStyleSheet("""
            QFrame#BgFrame {
                background-color: #F8F8F8;
                border: 1px solid #CCCCCC;
                border-radius: 10px; 
            }
        """)
        bg_layout = QVBoxLayout(self.bg_frame)
        bg_layout.setContentsMargins(10, 5, 10, 5)
        bg_layout.setSpacing(4)

        # --- 标题控制栏 ---
        title_bar_layout = QHBoxLayout()

        self.title_label = QLabel(" 文本输入", self)
        self.title_label.setStyleSheet("color: #888; font-weight: bold; font-size: 11px;")

        self.open_game_mic_box = QCheckBox("游戏麦",self)
        self.open_game_mic_box.toggled.connect(self.on_open_game_mic_toggled)


        # 仅保留置顶和透明度
        self.always_on_top_box = QCheckBox("置顶", self)
        self.always_on_top_box.toggled.connect(self.on_always_on_top_toggled)
        self.always_on_top_box.setChecked(True)


        self.opacity_slider = QSlider(Qt.Horizontal, self)
        self.opacity_slider.setRange(30, 100)
        self.opacity_slider.setValue(100)
        self.opacity_slider.setFixedWidth(70)
        self.opacity_slider.setMaximumHeight(12)
        self.opacity_slider.valueChanged.connect(lambda v: self.setWindowOpacity(v / 100.0))
        self.opacity_slider.setValue(80)

        self.close_btn = QPushButton("x", self)
        # self.close_btn.setFixedSize(18, 18)
        self.close_btn.setStyleSheet("""
            QPushButton { border: none; font-size: 16px; color: red; background: transparent; }
            QPushButton:hover { color: red; background-color: #ff4d4f; border-radius: 9px; }
        """)
        self.close_btn.clicked.connect(self.close)

        title_bar_layout.addWidget(self.title_label)
        title_bar_layout.addStretch()
        title_bar_layout.addWidget(self.open_game_mic_box)
        title_bar_layout.addWidget(self.always_on_top_box)
        title_bar_layout.addWidget(self.opacity_slider)
        title_bar_layout.addWidget(self.close_btn)
        bg_layout.addLayout(title_bar_layout)

        # --- 输入框 ---.
        self.input_box = QLineEdit(self)
        self.input_box.setPlaceholderText("在此键入文本，回车自动播放...")
        self.input_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.input_box.setStyleSheet("""
            QLineEdit {
                border: 1px solid #DDD;
                border-radius: 6px;
                padding: 4px 10px;
                background-color: #FFF;
                font-size: 15px;
            }
            QLineEdit:focus { border: 1px solid #1890ff; }
        """)
        self.input_box.returnPressed.connect(self.on_enter_pressed)
        bg_layout.addWidget(self.input_box)

        # --- 底部缩放手柄 ---
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()
        self.size_grip = QSizeGrip(self)
        self.size_grip.setFixedSize(24, 8)
        bottom_layout.addWidget(self.size_grip)
        bg_layout.addLayout(bottom_layout)

        main_layout.addWidget(self.bg_frame)

    # ================= 逻辑处理 =================

    def on_enter_pressed(self):
        text = self.input_box.text().strip()
        if text:
            self.text_submitted.emit(text)
            self.input_box.selectAll()  # 发送后全选，方便下次输入

    def on_always_on_top_toggled(self, checked):
        flags = self.windowFlags()
        if checked:
            flags |= Qt.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()  # 必须 show 否则窗口会消失

    def on_open_game_mic_toggled(self, checked):
        """在子窗口修改麦克风状态时调用"""
        # 直接转发这个 checked 即可
        self.open_mic_submitted.emit(checked)

    def mousePressEvent(self, event):
        """核心修复：只在点击背景或标题时允许拖动，避开输入框和手柄"""
        if event.button() == Qt.LeftButton:
            target = self.childAt(event.pos())
            # 如果点的是 QLineEdit 或 QSizeGrip，不触发窗口拖拽
            if target in [self.bg_frame, self.title_label, None]:
                self.dragPos = event.globalPos() - self.frameGeometry().topLeft()
                event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self.dragPos:
            self.move(event.globalPos() - self.dragPos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self.dragPos = None

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)