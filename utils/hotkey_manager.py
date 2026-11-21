# utils/hotkey_manager.py
"""Windows 全局热键监听线程。

RegisterHotKey/UnregisterHotKey 和消息循环都具有线程亲和性：
注册、消息处理、注销都必须发生在同一个线程里。因此这里只在 run()
中注册，在 run() 退出前注销；外部只需要 start()/stop()。
"""

import ctypes
import logging
import threading
from ctypes import wintypes
from typing import Dict

from PyQt5.QtCore import QThread, pyqtSignal

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008

VK_MAP = {
    '.': 0xDE,
    ',': 0xBC,
    '/': 0xBF,
    ' ': 0x20,
    'space': 0x20,
    'tab': 0x09,
    'enter': 0x0D,
    'pagedown': 0x22,
    'pageup': 0x21,
    'escape': 0x1B,
}
for _i in range(10):
    VK_MAP[str(_i)] = 0x30 + _i
for _i in range(26):
    _char = chr(ord('a') + _i)
    VK_MAP[_char] = 0x41 + _i
for _i in range(10):
    VK_MAP[f'num{_i}'] = 0x60 + _i
VK_MAP.update({
    'num_dot': 0x6E,
    'num_add': 0x6B,
    'num_sub': 0x6D,
    'num_mul': 0x6A,
    'num_div': 0x6F,
})

_MODIFIERS = {'ctrl': MOD_CONTROL, 'alt': MOD_ALT, 'shift': MOD_SHIFT, 'win': MOD_WIN}


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", wintypes.POINT),
    ]


def parse_hotkey_string(hotkey_str: str) -> tuple[int, int]:
    """把 'ctrl+alt+a' 解析为 (MOD 标志, VK 虚拟键码)。"""
    parts = hotkey_str.lower().split('+')
    mod_flags = 0
    vk_code = 0

    for part in parts:
        if part in _MODIFIERS:
            mod_flags |= _MODIFIERS[part]
        elif part in VK_MAP:
            vk_code = VK_MAP[part]
        else:
            logging.warning("无法识别的热键部分: %s", part)
            return 0, 0

    if vk_code == 0:
        raise ValueError(f"热键必须包含一个非修饰键: {hotkey_str}")
    return mod_flags, vk_code


class HotkeyManager(QThread):
    hotkey_triggered = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = True
        self.hotkeys_data: Dict[str, dict] = {}
        self.next_hotkey_id = 100
        self.id_to_name: Dict[int, str] = {}
        self._win_thread_id = None
        self._ready = threading.Event()

    def register_hotkey(self, name: str, hotkey: str) -> bool:
        """只允许在 start() 之前调用（注册必须在监听线程内完成）。"""
        if self.isRunning():
            logging.error("热键监听已启动，无法动态注册 %s；请重建 HotkeyManager", name)
            return False

        try:
            mod, vk = parse_hotkey_string(hotkey)
        except ValueError as exc:
            logging.error("注册热键失败 %s: %s", name, exc)
            return False
        if vk == 0:
            return False

        hotkey_id = self.next_hotkey_id
        self.next_hotkey_id += 1
        self.hotkeys_data[name] = {'mod': mod, 'vk': vk, 'id': hotkey_id, 'hotkey_str': hotkey}
        self.id_to_name[hotkey_id] = name
        return True

    def _register_all(self) -> None:
        for name, data in self.hotkeys_data.items():
            success = user32.RegisterHotKey(None, data['id'], data['mod'], data['vk'])
            if not success:
                logging.error(
                    "注册热键失败 %s (%s)，可能已被其它程序占用",
                    name, data['hotkey_str'],
                )

    def _unregister_all(self) -> None:
        for hotkey_id in list(self.id_to_name.keys()):
            user32.UnregisterHotKey(None, hotkey_id)
        self.hotkeys_data.clear()
        self.id_to_name.clear()

    def run(self):
        logging.info("热键监听线程已启动")
        self._win_thread_id = kernel32.GetCurrentThreadId()

        # 强制系统为当前线程创建消息队列（之后 stop() 才能 PostThreadMessage）
        msg = MSG()
        user32.PeekMessageA(ctypes.byref(msg), None, 0, 0, 0x0000)
        self._ready.set()

        self._register_all()
        try:
            while self._running:
                result = user32.GetMessageA(ctypes.byref(msg), None, 0, 0)
                if result == 0:
                    break
                if result == -1:
                    logging.error("热键消息循环异常退出")
                    break
                if msg.message == WM_HOTKEY:
                    hotkey_name = self.id_to_name.get(msg.wParam)
                    if hotkey_name:
                        self.hotkey_triggered.emit(hotkey_name)
                elif msg.message == WM_QUIT:
                    break
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageA(ctypes.byref(msg))
        finally:
            self._unregister_all()
            logging.info("热键监听线程已安全退出")

    def stop(self):
        if not self.isRunning():
            return
        self._running = False
        # 等待 run() 拿到线程 ID，避免在启动瞬间调用 stop 时死等
        self._ready.wait(1.0)
        if self._win_thread_id is not None:
            user32.PostThreadMessageA(self._win_thread_id, WM_QUIT, 0, 0)
        self.wait()
