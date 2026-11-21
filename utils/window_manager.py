# utils/window_manager.py
"""检测并聚焦游戏窗口。"""

import ctypes
import logging
from ctypes import wintypes

user32 = ctypes.windll.user32
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


class WindowManager:
    def __init__(self, target_games: list[str] | None = None):
        self.current_hwnd: int | None = None
        self.current_title: str = ""
        self.target_games = list(target_games or [])

    def _focus_hwnd(self, hwnd: int, title: str) -> bool:
        try:
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            # 置顶再取消，兼容 Win10/11
            user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0003)  # HWND_TOPMOST
            user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, 0x0003)  # HWND_NOTOPMOST
            logging.info("聚焦游戏窗口: %s (HWND %s)", title, hwnd)
            return True
        except Exception as exc:
            logging.error("聚焦游戏窗口失败: %s", exc)
            return False

    def focus_game_if_needed(self, mic_status: bool) -> bool:
        if not mic_status:
            return True
        try:
            return self.detect_and_focus_game()
        except Exception as exc:
            logging.error("检测游戏窗口失败: %s", exc)
            return False

    def detect_and_focus_game(self) -> bool:
        self.current_hwnd = None
        self.current_title = ""

        def enum_callback(hwnd, lParam):
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return True
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            title = buff.value.strip()
            if not title:
                return True
            lower_title = title.lower()
            for game in self.target_games:
                if game and game.lower() in lower_title:
                    self.current_hwnd = hwnd
                    self.current_title = title
                    return False
            return True

        user32.EnumWindows(WNDENUMPROC(enum_callback), 0)
        if self.current_hwnd:
            return self._focus_hwnd(self.current_hwnd, self.current_title)
        logging.warning("未检测到目标游戏窗口")
        return False

    def get_current_window(self) -> tuple[int | None, str]:
        return self.current_hwnd, self.current_title

    def is_game_window_active(self) -> bool:
        if not self.current_hwnd:
            return False
        return bool(user32.IsWindow(self.current_hwnd) and user32.IsWindowVisible(self.current_hwnd))

    def refocus_current_game(self) -> bool:
        if not self.current_hwnd:
            return False
        return self._focus_hwnd(self.current_hwnd, self.current_title)

    def clear(self):
        self.current_hwnd = None
        self.current_title = ""
