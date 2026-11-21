# ui/components/hotkey_dialog.py
from PySide6.QtWidgets import QPushButton, QDialog, QVBoxLayout, QLabel, QDialogButtonBox, QHBoxLayout
from PySide6.QtCore import Qt, QTimer


class HotkeyInputButton(QPushButton):
    """自定义的快捷键录制按钮"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_hotkey = ""
        self.is_recording = False
        self.setText("等待录制...")
        self.setFocusPolicy(Qt.StrongFocus)  # 确保能接收键盘焦点
        self.setToolTip("点击后，直接在键盘上按下你想要的组合键")

    def start_recording(self):
        """用代码主动触发录制状态"""
        self.is_recording = True
        self.setText("🔴 正在监听... 请按下快捷键 (按 Esc 清空)")
        self.setFocus()

    def mousePressEvent(self, event):
        """鼠标手动点击时也进入录制模式"""
        self.start_recording()

    def focusOutEvent(self, event):
        """失去焦点时退出录制模式"""
        self.is_recording = False
        self.update_display()
        super().focusOutEvent(event)

    def update_display(self):
        if self.current_hotkey:
            self.setText(f"已捕获: {self.current_hotkey}")
        else:
            self.setText("点击此处重新录制...")

    def keyPressEvent(self, event):
        """核心：拦截键盘输入并解析组合，精准区分主键盘和小键盘"""
        if not self.is_recording:
            super().keyPressEvent(event)
            return

        key = event.key()

        # 如果只按下了修饰键（Ctrl/Alt/Shift/Win），不要马上结束，等待主键按下
        if key in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta):
            return

            # 按下 Esc 键，清空当前快捷键
        if key == Qt.Key_Escape:
            self.is_recording = False
            self.current_hotkey = ""
            self.update_display()
            return

        # 1. 捕捉基础修饰键
        modifiers = event.modifiers()
        parts = []
        if modifiers & Qt.ControlModifier: parts.append('ctrl')
        if modifiers & Qt.AltModifier: parts.append('alt')
        if modifiers & Qt.ShiftModifier: parts.append('shift')
        if modifiers & Qt.MetaModifier: parts.append('win')

        # 判断这次按键是否来自小键盘 (NumPad)
        is_numpad = bool(modifiers & Qt.KeypadModifier)

        # 2. 捕捉并翻译主键位
        key_str = ""
        if Qt.Key_A <= key <= Qt.Key_Z:
            key_str = chr(key).lower()
        elif Qt.Key_0 <= key <= Qt.Key_9:
            # 区分主键盘数字和小键盘数字
            if is_numpad:
                key_str = f"num{key - Qt.Key_0}"
            else:
                key_str = chr(key)
        else:
            # 处理小键盘的特殊符号 (+ - * / .)
            if is_numpad:
                numpad_special = {
                    Qt.Key_Period: 'num_dot',
                    Qt.Key_Plus: 'num_add',
                    Qt.Key_Minus: 'num_sub',
                    Qt.Key_Asterisk: 'num_mul',
                    Qt.Key_Slash: 'num_div',
                }
                if key in numpad_special:
                    key_str = numpad_special[key]

            if not key_str:
                special_keys = {
                    Qt.Key_PageDown: 'pagedown',
                    Qt.Key_PageUp: 'pageup',
                    Qt.Key_Space: 'space',
                    Qt.Key_Return: 'enter',
                    Qt.Key_Enter: 'enter',
                    Qt.Key_Tab: 'tab',
                    Qt.Key_Period: '.',
                    Qt.Key_Comma: ',',
                    Qt.Key_Slash: '/',
                }
                key_str = special_keys.get(key, "")

        # 3. 组合并完成录制
        if key_str:
            parts.append(key_str)
            self.current_hotkey = "+".join(parts)
            self.is_recording = False
            self.update_display()
        else:
            self.setText("⚠️ 不支持的按键，请重新按下 (按 Esc 清空)")


class HotkeyBindDialog(QDialog):
    """升级版的可视化快捷键绑定窗口"""

    def __init__(self, current_key="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("分配快捷键")
        self.setFixedSize(320, 200)

        layout = QVBoxLayout(self)

        # 动态提示词：如果有旧按键，显示旧按键并提示可以直接覆盖
        if current_key:
            tip_text = f"当前快捷键为: <b>{current_key}</b><br>请直接在键盘上敲击<b>新快捷键</b>进行替换<br><span style='color:gray; font-size:11px;'>(按 Esc 清空，直接点确定则保持不变)</span>"
        else:
            tip_text = "请<b>直接在键盘上敲击</b>组合键<br><span style='color:gray; font-size:11px;'>(例如同时按下 Ctrl 和 V)</span>"

        tip_label = QLabel(tip_text)
        tip_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(tip_label)

        # 核心录制按钮
        self.input_btn = HotkeyInputButton()
        self.input_btn.setFixedHeight(40)

        # 赋予按钮初始值
        self.input_btn.current_hotkey = current_key
        layout.addWidget(self.input_btn)

        layout.addStretch(1)

        # 确认取消按钮
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

        # 【核心魔法】：延迟 50 毫秒，等窗口完全渲染出来后，自动触发监听模式
        QTimer.singleShot(50, self.input_btn.start_recording)

    def get_hotkey(self):
        """对话框确认后，吐出录制好的快捷键字符串"""
        return self.input_btn.current_hotkey


class SystemHotkeyDialog(QDialog):
    """系统级全局快捷键设置面板"""

    def __init__(self, hotkeys_map, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙️ 全局系统快捷键设置")
        self.setFixedSize(350, 250)
        self.hotkeys_map = hotkeys_map  # 传入当前的快捷键字典

        layout = QVBoxLayout(self)

        # 提示语
        tip = QLabel("点击下方按钮，直接在键盘上敲击新的组合键：\n(按 Esc 可清空对应快捷键)")
        tip.setAlignment(Qt.AlignCenter)
        layout.addWidget(tip)
        layout.addSpacing(10)

        # 定义需要设置的系统动作
        self.sys_actions = {
            'sys_toggle_window': '显示 / 隐藏主界面',
            'sys_stop_play': '立即停止当前播放',
            'sys_toggle_mic': '一键开关游戏麦',
            'sys_repeat_play': '重复上一次播放',
            'sys_float_window':'打开/关闭浮动输入框'
        }

        self.buttons = {}  # 用于保存按钮引用，方便最后提取数据

        # 循环生成设置行
        for action_id, display_name in self.sys_actions.items():
            row_layout = QHBoxLayout()
            row_layout.addWidget(QLabel(display_name + " :"))

            btn = HotkeyInputButton()
            btn.setFixedHeight(30)
            # 从传入的字典中读取当前按键，如果没有则为空
            current_key = self.hotkeys_map.get(action_id, "")
            btn.current_hotkey = current_key
            btn.update_display()

            self.buttons[action_id] = btn
            row_layout.addWidget(btn)
            layout.addLayout(row_layout)

        layout.addStretch(1)

        # 确认与取消
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def get_new_hotkeys(self):
        """返回修改后的系统快捷键字典"""
        new_map = {}
        for action_id, btn in self.buttons.items():
            new_map[action_id] = btn.current_hotkey
        return new_map