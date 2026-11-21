# # utils/window_manager.py
# import ctypes
# from ctypes import wintypes
# import logging
#
# # 加载 user32 DLL
# user32 = ctypes.windll.user32
#
# # 定义 EnumWindows 的回调函数类型
# WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
#
#
# class WindowManager:
#     """窗口管理器，封装底层 Win32 API 实现窗口的高级操作"""
#     @staticmethod
#     def focus_window_by_title(target_title="Counter-Strike 2") -> bool:
#         """
#         遍历系统所有窗口，忽略大小写寻找匹配的窗口，并将其强制带到前台。
#         """
#         found_hwnd = None
#
#         def enum_windows_callback(hwnd, lParam):
#             nonlocal found_hwnd
#
#             # 过滤：只检查当前可见的窗口，忽略后台幽灵窗口
#             if user32.IsWindowVisible(hwnd):
#                 length = user32.GetWindowTextLengthW(hwnd)
#                 if length > 0:
#                     buff = ctypes.create_unicode_buffer(length + 1)
#                     user32.GetWindowTextW(hwnd, buff, length + 1)
#                     window_title = buff.value
#
#                     # 核心：忽略大小写的包含匹配 (抗截断、抗后缀)
#                     if target_title.lower() in window_title.lower():
#                         found_hwnd = hwnd
#                         return False  # 找到了！返回 False 告诉系统停止遍历
#             return True  # 没找到，返回 True 继续下一个
#
#         # 1. 触发遍历系统所有顶层窗口
#         user32.EnumWindows(WNDENUMPROC(enum_windows_callback), 0)
#
#         # 2. 如果找到了对应的窗口句柄 (HWND)，执行聚焦操作
#         if found_hwnd:
#             try:
#                 # 常量 9 = SW_RESTORE。如果游戏被最小化到任务栏了，先把它还原出来
#                 user32.ShowWindow(found_hwnd, 9)
#
#                 # 核心杀招：强行把窗口拽到最前台并激活
#                 user32.SetForegroundWindow(found_hwnd)
#
#                 logging.info(f"🎮 成功切回游戏窗口: {target_title} (HWND: {found_hwnd})")
#                 return True
#             except Exception as e:
#                 logging.error(f"❌ 聚焦窗口时发生异常: {e}")
#                 return False
#         else:
#             logging.warning(f"⚠️ 未检测到运行中的目标窗口: {target_title}")
#             return False


# utils/window_manager.py
import ctypes
from ctypes import wintypes
from utils.config_manager import ConfigManager

import logging

user32 = ctypes.windll.user32
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


class WindowManager:
    """窗口管理器，支持自动检测并持久化记录当前游戏窗口"""

    def __init__(self):
        self.current_hwnd: int | None = None          # 当前检测到的窗口句柄
        self.current_title: str = ""                  # 当前检测到的窗口标题
        self.config_manager = ConfigManager()
        self.config = ConfigManager().load()            # 去配置文件修改具体游戏
        self.target_games = self.config.get("games")


    def _focus_hwnd(self, hwnd: int, title: str) -> bool:
        """内部强力聚焦逻辑"""
        try:
            user32.ShowWindow(hwnd, 9)                    # SW_RESTORE
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)

            # 额外置顶再取消，兼容 Win10/11
            user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0003)  # HWND_TOPMOST
            user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, 0x0003)  # HWND_NOTOPMOST

            logging.info(f"🎮 成功聚焦游戏窗口: {title} (HWND: {hwnd})")
            return True
        except Exception as e:
            logging.error(f"❌ 聚焦窗口失败: {e}")
            return False

    def focus_game_if_needed(self, mic_status: bool) -> bool:
        """
        根据麦克风状态决定是否切回游戏窗口
        - mic_status 为 True 时 → 自动检测并聚焦游戏窗口
        - 返回 True 表示成功聚焦（或不需要聚焦）
        """
        if not mic_status:
            return True  # 麦克风没开，不需要切游戏窗口，直接返回成功

        try:
            # 使用我们新的实例化方式
            success = self.detect_and_focus_game()
            if not success:
                logging.warning("尝试聚焦游戏窗口失败，未找到游戏窗口")
            return success
        except Exception as e:
            logging.error(f"Failed to focus game window: {e}")
            return False

    def detect_and_focus_game(self) -> bool:
        """
        自动检测主流游戏窗口，并将其保存到实例变量中，同时聚焦
        返回: 是否成功检测到并聚焦
        """
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
                if game.lower() in lower_title:
                    self.current_hwnd = hwnd
                    self.current_title = title
                    return False  # 停止枚举
            return True

        # 执行枚举
        user32.EnumWindows(WNDENUMPROC(enum_callback), 0)

        if self.current_hwnd:
            success = self._focus_hwnd(self.current_hwnd, self.current_title)
            return success
        else:
            logging.warning("⚠️ 未检测到任何主流游戏窗口")
            return False

    # ==================== 便捷属性和方法 ====================

    def get_current_window(self) -> tuple[int | None, str]:
        """返回当前保存的窗口句柄和标题"""
        return self.current_hwnd, self.current_title

    def is_game_window_active(self) -> bool:
        """检查当前记录的窗口是否仍然存在且可见"""
        if not self.current_hwnd:
            return False
        return bool(user32.IsWindow(self.current_hwnd) and user32.IsWindowVisible(self.current_hwnd))

    def refocus_current_game(self) -> bool:
        """直接对上次检测到的窗口重新聚焦（无需重新遍历）"""
        if not self.current_hwnd:
            logging.warning("没有已记录的游戏窗口可聚焦")
            return False
        return self._focus_hwnd(self.current_hwnd, self.current_title)

    def clear(self):
        """清空当前记录的窗口"""
        self.current_hwnd = None
        self.current_title = ""