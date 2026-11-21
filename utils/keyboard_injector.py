# utils/keyboard_injector.py
import ctypes
from ctypes import wintypes
import logging

# --- 定义 SendInput 所需的结构和常量 ---
user32 = ctypes.windll.user32

INPUT_KEYBOARD = 1
KEYEVENT_KEYDOWN = 0x0000
KEYEVENT_KEYUP = 0x0002
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_SCANCODE = 0x0008

# 硬件扫描码映射
SCAN_MAP = {
    'pagedown': (0x51, True),
    'pageup': (0x49, True),
    'v': (0x2F, False),
    'k': (0x25, False),
    'alt': (0x38, False),
}


# 严谨的结构体定义（修复了 dwExtraInfo 的 64 位对齐问题）
class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),  # 使用 c_void_p 替代 POINTER
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUTunion(ctypes.Union):
    _fields_ = [
        ("ki", KEYBDINPUT),
        ("mi", MOUSEINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _anonymous_ = ("union",)
    _fields_ = [
        ("type", wintypes.DWORD),
        ("union", _INPUTunion),
    ]


class KeyboardInjector:
    """轻量级的硬件级按键注入工具"""

    @staticmethod
    def v_press(key_code: str):
        key_lower = key_code.lower()
        if key_lower not in SCAN_MAP:
            logging.warning(f"缺少硬件扫描码映射: '{key_code}'")
            return False

        scan_code, is_extended = SCAN_MAP[key_lower]
        flags = KEYEVENTF_SCANCODE | (KEYEVENTF_EXTENDEDKEY if is_extended else 0)

        input_struct = INPUT(
            type=INPUT_KEYBOARD,
            ki=KEYBDINPUT(wVk=0, wScan=scan_code, dwFlags=flags)
        )

        if user32.SendInput(1, ctypes.byref(input_struct), ctypes.sizeof(INPUT)) == 0:
            logging.error(f"按下 {key_code} 失败: {ctypes.get_last_error()}")
            return False
        return True

    @staticmethod
    def v_release(key_code: str):
        key_lower = key_code.lower()
        if key_lower not in SCAN_MAP:
            return False

        scan_code, is_extended = SCAN_MAP[key_lower]
        flags = KEYEVENTF_SCANCODE | KEYEVENT_KEYUP | (KEYEVENTF_EXTENDEDKEY if is_extended else 0)

        input_struct = INPUT(
            type=INPUT_KEYBOARD,
            ki=KEYBDINPUT(wVk=0, wScan=scan_code, dwFlags=flags)
        )

        if user32.SendInput(1, ctypes.byref(input_struct), ctypes.sizeof(INPUT)) == 0:
            logging.error(f"释放 {key_code} 失败: {ctypes.get_last_error()}")
            return False
        return True