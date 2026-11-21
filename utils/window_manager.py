# utils/window_manager.py
"""游戏窗口识别与聚焦。

匹配规则同时看窗口标题和进程名：
- 配置里的关键词（不区分大小写）出现在窗口标题中即命中；
- 关键词或内置别名出现在进程名中也会命中（例如 cs2.exe / VALORANT-Win64-Shipping.exe）。
这样既能覆盖标题不固定的游戏，也能避免只靠短标题造成的误判。
"""

import ctypes
import logging
import re
from ctypes import wintypes
from dataclasses import dataclass

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetWindowThreadProcessId.argtypes = [
    wintypes.HWND, ctypes.POINTER(wintypes.DWORD)
]
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)
]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

# 关键词 -> 进程名别名（进程名通常与窗口标题差别很大）
PROCESS_ALIASES = {
    'counter-strike 2': ['cs2'],
    'counter-strike': ['hl'],
    'valorant': ['valorant-win64-shipping'],
    'league of legends': ['leagueclient', 'leagueclientux', 'league of legends'],
    'dota 2': ['dota2'],
    'overwatch': ['overwatch'],
    'apex legends': ['r5apex'],
    'fortnite': ['fortniteclient-win64-shipping', 'fortnite'],
    'pubg': ['tslgame'],
    'rocket league': ['rocketleague'],
    'grand theft auto v': ['gta5'],
    'gta5': ['gta5'],
    'call of duty': ['cod', 'modernwarfare'],
    'warzone': ['cod', 'modernwarfare'],
    'battlefield': ['bf1', 'bf4', 'bfv', 'bf2042'],
    'hell let loose': ['hll'],
    'dayz': ['dayz_x64'],
    'the finals': ['discovery'],
    'hunt: showdown': ['huntgame', 'hunt'],
    'arena breakout': ['arenabreakout'],
    '暗区突围': ['arenabreakout'],
    '三角洲行动': ['deltaforceclient'],
    '永劫无间': ['naraka'],
    '漫威争锋': ['marvelrivals'],
    '七日世界': ['oncehumanclient'],
    '燕云十六声': ['wherewindsmeet'],
    '幻兽帕鲁': ['palworld'],
}


# 标题里出现游戏名、但显然不是游戏的进程（浏览器标签、聊天软件等）
NON_GAME_PROCESSES = {
    'chrome', 'msedge', 'firefox', 'opera', 'brave', 'vivaldi', 'iexplore',
    'discord', 'telegram', 'qq', 'wechat', 'weixin', 'teams', 'slack',
    'code', 'notepad', 'explorer', 'cmd', 'powershell', 'pwsh',
    'windowsterminal', 'applicationframehost', 'steamwebhelper',
}


@dataclass(frozen=True)
class GameWindowMatch:
    hwnd: int
    title: str
    exe_name: str
    keyword: str


def _compact(text: str) -> str:
    return re.sub(r"[\s:：_\-–—]+", "", text.lower())


def _stem(exe_name: str) -> str:
    name = exe_name.lower().strip().replace('/', '\\').rsplit('\\', 1)[-1]
    return name[:-4] if name.endswith('.exe') else name


def is_non_game_process(exe_name: str) -> bool:
    return bool(exe_name) and _stem(exe_name) in NON_GAME_PROCESSES


def match_game(games: list[str], title: str, exe_name: str = "") -> str | None:
    """返回命中的关键词；未命中返回 None。纯函数，便于测试。"""
    title_l = (title or "").lower()
    exe_stem = _stem(exe_name or "")

    for raw_keyword in games:
        keyword = str(raw_keyword).strip()
        if not keyword:
            continue
        key = keyword.lower()

        if key in title_l:
            return keyword

        if not exe_stem:
            continue

        candidates = [key, _compact(key)]
        candidates.extend(PROCESS_ALIASES.get(key, []))

        for candidate in candidates:
            candidate = candidate.lower()
            if not candidate:
                continue
            if candidate == exe_stem:
                return keyword
            # 短别名（如 cod）只做精确匹配，避免命中 code.exe
            if len(candidate) >= 6 and candidate in exe_stem:
                return keyword

    return None


def _get_window_title(hwnd) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buff = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buff, length + 1)
    return buff.value


def _get_process_name(hwnd) -> str:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if not pid.value:
        return ""
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return ""
    try:
        buff = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(len(buff))
        if kernel32.QueryFullProcessImageNameW(handle, 0, buff, ctypes.byref(size)):
            return buff.value.rsplit('\\', 1)[-1]
    finally:
        kernel32.CloseHandle(handle)
    return ""


class WindowManager:
    def __init__(self, target_games: list[str] | None = None):
        self.current_hwnd: int | None = None
        self.current_title: str = ""
        self.target_games: list[str] = []
        self.set_target_games(target_games)

    def set_target_games(self, games: list[str] | None) -> None:
        self.target_games = [str(g).strip() for g in (games or []) if str(g).strip()]

    # ------------------------------------------------------------------
    def _match_window(self, hwnd) -> GameWindowMatch | None:
        title = _get_window_title(hwnd)
        exe_name = _get_process_name(hwnd)
        # 浏览器/聊天软件标题里出现游戏名时不算命中
        if is_non_game_process(exe_name):
            return None
        keyword = match_game(self.target_games, title, exe_name)
        if keyword is None:
            return None
        return GameWindowMatch(hwnd, title, exe_name, keyword)

    def foreground_match(self) -> GameWindowMatch | None:
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        found = self._match_window(hwnd)
        if found is not None:
            self.current_hwnd = found.hwnd
            self.current_title = found.title
        return found

    def is_game_foreground(self) -> bool:
        return self.foreground_match() is not None

    # ------------------------------------------------------------------
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
        # 已经在前台游戏窗口里时不再抢焦点（部分游戏/反作弊会拦截切窗）
        if self.foreground_match() is not None:
            return True
        try:
            return self.detect_and_focus_game()
        except Exception as exc:
            logging.error("检测游戏窗口失败: %s", exc)
            return False

    def detect_and_focus_game(self) -> bool:
        self.current_hwnd = None
        self.current_title = ""
        found: list[GameWindowMatch] = []

        def enum_callback(hwnd, lParam):
            if not user32.IsWindowVisible(hwnd):
                return True
            title = _get_window_title(hwnd)
            if not title:
                return True

            exe_name = _get_process_name(hwnd)
            if is_non_game_process(exe_name):
                return True
            keyword = match_game(self.target_games, title, exe_name)
            if keyword is None:
                return True

            found.append(GameWindowMatch(hwnd, title, exe_name, keyword))
            return False  # 找到即停止枚举

        user32.EnumWindows(WNDENUMPROC(enum_callback), 0)
        if not found:
            logging.warning("未检测到目标游戏窗口")
            return False

        match = found[0]
        self.current_hwnd = match.hwnd
        self.current_title = match.title
        return self._focus_hwnd(match.hwnd, match.title)

    # ------------------------------------------------------------------
    def get_current_window(self) -> tuple[int | None, str]:
        return self.current_hwnd, self.current_title

    def is_game_window_active(self) -> bool:
        if not self.current_hwnd:
            return False
        return bool(
            user32.IsWindow(self.current_hwnd)
            and user32.IsWindowVisible(self.current_hwnd)
        )

    def refocus_current_game(self) -> bool:
        if not self.current_hwnd:
            return False
        return self._focus_hwnd(self.current_hwnd, self.current_title)

    def clear(self):
        self.current_hwnd = None
        self.current_title = ""
