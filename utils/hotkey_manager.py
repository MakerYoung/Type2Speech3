# utils/hotkey_manager.py
import ctypes
from ctypes import wintypes
from PyQt5.QtCore import pyqtSignal, QThread
from typing import Dict
import logging

# 加载必要的 DLL
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


# --- Windows 消息结构体定义 ---
class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", wintypes.POINT)
    ]


# --- 常量定义 ---
WM_HOTKEY = 0x0312

# 修饰键标志
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008

# --- 虚拟键码映射 (VK_MAP) ---
VK_MAP = {
    '.': 0xDE,  # VK_OEM_PERIOD
    ',': 0xBC,  # VK_OEM_COMMA
    '/': 0xBF,  # VK_OEM_2
    ' ': 0x20,  # VK_SPACE
    'space': 0x20,  # VK_SPACE
    'tab': 0x09,  # VK_TAB
    'enter': 0x0D,  # VK_RETURN
    'pagedown': 0x22,
}
# 数字键 0-9
for i in range(10):
    VK_MAP[str(i)] = 0x30 + i
# 字母键 A-Z
for i in range(26):
    char = chr(ord('a') + i)
    VK_MAP[char] = 0x41 + i
# 数字小键盘 (NumPad)
for i in range(10):
    VK_MAP[f'num{i}'] = 0x60 + i  # VK_NUMPAD0 到 VK_NUMPAD9
VK_MAP['num_dot'] = 0x6E
VK_MAP['num_add'] = 0x6B
VK_MAP['num_sub'] = 0x6D
VK_MAP['num_mul'] = 0x6A
VK_MAP['num_div'] = 0x6F


def parse_hotkey_string(hotkey_str: str) -> tuple[int, int]:
    """
    解析热键字符串 (如 'ctrl+alt+a') 为 Windows MOD 和 VK。
    """
    parts = hotkey_str.lower().split('+')
    mod_flags = 0
    vk_code = 0

    for part in parts:
        if part == 'ctrl':
            mod_flags |= MOD_CONTROL
        elif part == 'alt':
            mod_flags |= MOD_ALT
        elif part == 'shift':
            mod_flags |= MOD_SHIFT
        elif part == 'win':
            mod_flags |= MOD_WIN
        elif part in VK_MAP:
            vk_code = VK_MAP[part]
        elif len(part) == 1 and part.isalpha():
            vk_code = VK_MAP[part]
        else:
            logging.warning(f"警告：无法识别的热键部分: {part}")
            return 0, 0  # 失败

    if vk_code == 0:
        raise ValueError(f"热键必须包含一个非修饰键: {hotkey_str}")

    return mod_flags, vk_code


class HotkeyManager(QThread):
    """
    纯粹的热键监听器，使用 Windows API (ctypes) 在单独线程中监听。
    不再包含按键注入逻辑。
    """
    hotkey_triggered = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = True
        self.hotkeys_data: Dict[str, dict] = {}
        self.next_hotkey_id = 100
        self.id_to_name: Dict[int, str] = {}
        self._win_thread_id = None

    def register_hotkey(self, name: str, hotkey: str):
        if name in self.hotkeys_data:
            self.unregister_hotkey(name)

        try:
            mod, vk = parse_hotkey_string(hotkey)
        except ValueError as e:
            logging.error(f"注册热键失败 {name}: {e}")
            return

        if vk == 0:
            return

        hotkey_id = self.next_hotkey_id
        self.next_hotkey_id += 1

        data = {'mod': mod, 'vk': vk, 'id': hotkey_id, 'hotkey_str': hotkey}
        self.hotkeys_data[name] = data
        self.id_to_name[hotkey_id] = name

        if self.isRunning():
            self._register_single_hotkey(data)

        # logging.info(f"待注册热键: {name} -> {hotkey}")

    def unregister_hotkey(self, name: str):
        if name in self.hotkeys_data:
            data = self.hotkeys_data.pop(name)
            hotkey_id = data['id']

            if self.isRunning():
                user32.UnregisterHotKey(None, hotkey_id)
                logging.info(f"已注销API热键 ID:{hotkey_id}")

            if hotkey_id in self.id_to_name:
                del self.id_to_name[hotkey_id]

    def _register_single_hotkey(self, data: dict):
        hotkey_id = data['id']
        success = user32.RegisterHotKey(None, hotkey_id, data['mod'], data['vk'])

        if success:
            pass
            # logging.info(f"注册API热键成功 ID:{hotkey_id} -> {data['hotkey_str']}")
        else:
            logging.error(f"注册API热键失败 ID:{data}，错误码: {ctypes.get_last_error()}")

        return success

    def run(self):
        logging.info("热键监听线程已启动")

        # 强制系统为当前线程创建消息队列
        self._win_thread_id = kernel32.GetCurrentThreadId()
        msg = MSG()
        user32.PeekMessageA(ctypes.byref(msg), None, 0, 0, 0x0000)

        for data in self.hotkeys_data.values():
            self._register_single_hotkey(data)

        # 消息循环
        while self._running:
            if user32.GetMessageA(ctypes.byref(msg), None, 0, 0) != 0:
                if msg.message == WM_HOTKEY:
                    hotkey_id = msg.wParam
                    if hotkey_id in self.id_to_name:
                        hotkey_name = self.id_to_name[hotkey_id]
                        self.hotkey_triggered.emit(hotkey_name)
                        # logging.info(f'触发热键: {hotkey_name}')

                elif msg.message == 0x12:  # WM_QUIT
                    self._running = False

                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageA(ctypes.byref(msg))
            else:
                self._running = False

        self.remove_all_hotkeys()
        logging.info("热键监听线程已安全退出")

    def remove_all_hotkeys(self):
        for hotkey_id in list(self.id_to_name.keys()):
            user32.UnregisterHotKey(None, hotkey_id)
        self.hotkeys_data.clear()
        self.id_to_name.clear()

    # def remove_all_hotkeys(self):
    #     import ctypes
    #     import logging
    #
    #     for hotkey_id in list(self.id_to_name.keys()):
    #         # 这里的 None 极大可能是罪魁祸首！
    #         # 先试着看它有没有成功
    #         res = ctypes.windll.user32.UnregisterHotKey(None, hotkey_id)
    #
    #         if res == 0:
    #             # 获取 Windows 底层真实错误码
    #             error_code = ctypes.windll.kernel32.GetLastError()
    #             logging.error(f"❌ 快捷键 {hotkey_id} 释放失败！Win32错误码: {error_code}")
    #         else:
    #             logging.info(f"✅ 快捷键 {hotkey_id} 释放成功！")
    #
    #     self.hotkeys_data.clear()
    #     self.id_to_name.clear()

    def stop(self):
        self._running = False
        self.remove_all_hotkeys()

        thread_id = self._win_thread_id
        if thread_id is not None:
            logging.info(f"发送 WM_QUIT 终止线程 ID: {thread_id}")
            user32.PostThreadMessageA(thread_id, 0x12, 0, 0)

        self.wait()