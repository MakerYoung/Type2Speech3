# main.py
import logging
import os
import sys

import qdarktheme
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow

logging.basicConfig(
    level=logging.INFO,
    force=True,
    format='%(asctime)s - [%(levelname)s] - %(message)s'
)


def _smoke_exit_ms() -> int:
    """诊断/CI 用：启动后自动关闭窗口的毫秒数，0 表示不启用。"""
    try:
        return max(0, int(os.environ.get("TYPE2SPEECH_SMOKE_EXIT_MS", "0") or "0"))
    except ValueError:
        return 0


def main():
    app = QApplication(sys.argv)

    # 启用现代主题（支持 'dark' 或 'light'，也可以设为 'auto' 跟随系统）
    qdarktheme.setup_theme("light", custom_colors={"primary": "#0078D4"})

    window = MainWindow()
    window.show()

    smoke_ms = _smoke_exit_ms()
    if smoke_ms:
        QTimer.singleShot(smoke_ms, window.close)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
