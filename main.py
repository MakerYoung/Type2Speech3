# main.py
import sys
from PyQt5.QtWidgets import QApplication
from ui.main_window import MainWindow
import qdarktheme
import logging

logging.basicConfig(
    level=logging.INFO,
    force=True,
    format='%(asctime)s - [%(levelname)s] - %(message)s'
)


def main():
    app = QApplication(sys.argv)

    # 启用现代主题（支持 'dark' 或 'light'，也可以设为 'auto' 跟随系统）
    qdarktheme.setup_theme("light", custom_colors={"primary": "#0078D4"})

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()