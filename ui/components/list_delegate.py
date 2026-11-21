# ui/components/list_delegate.py
from PyQt5.QtWidgets import QStyledItemDelegate, QStyle, QStyleOptionViewItem
from PyQt5.QtGui import QFont, QColor, QPalette, QFontMetrics
from PyQt5.QtCore import Qt, QRect, QSize


class HotkeyItemDelegate(QStyledItemDelegate):
    """自定义列表项渲染器：适配现代主题库，暴力修复选中文字颜色"""

    def sizeHint(self, option, index):
        """重写此方法以增加每一行的行高，提供更好的呼吸感"""
        # 先获取系统默认的尺寸
        size = super().sizeHint(option, index)

        # 在默认高度的基础上增加 12 个像素（你可以根据喜好微调这个数值）
        # 现代 UI 通常推荐行高在 36~42 像素左右
        size.setHeight(size.height() + 8)

        return size

    def paint(self, painter, option, index):
        # 🛠️ 防止 qdarktheme 的 QSS 与自定义绘制重叠
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        # 清空底层选项中的文本，让 qdarktheme 只画背景
        opt.text = ""
        option.widget.style().drawControl(QStyle.CE_ItemViewItem, opt, painter, option.widget)

        # 获取数据
        text = index.data(Qt.DisplayRole) or ""
        hotkey = index.data(Qt.UserRole + 2) or ""

        rect = opt.rect
        padding = 8


        painter.save()

        # ==========================================
        # 🎨 修复选中变色：物理外挂，强制白色
        # ==========================================
        is_selected = option.state & QStyle.State_Selected

        if is_selected:
            text_color = QColor(Qt.white)
            hotkey_color = QColor(Qt.white)
            hotkey_color.setAlpha(230)
        else:
            text_color = option.palette.color(QPalette.Text)
            hotkey_color = option.palette.color(QPalette.Text)
            hotkey_color.setAlpha(170)

        text_rect = QRect(rect.left() + padding, rect.top(), rect.width() - padding * 2, rect.height())

        # ==========================================
        # 👑 设置快捷键字体（加粗）并计算宽度
        # ==========================================
        hotkey_width = 0
        gap = 15

        hotkey_font = QFont(painter.font())
        hotkey_font.setBold(True)

        if hotkey:
            hotkey_metrics = QFontMetrics(hotkey_font)
            hotkey_width = hotkey_metrics.boundingRect(hotkey).width() + gap

        # 动态截断主文本
        available_text_width = max(0, text_rect.width() - hotkey_width)
        main_metrics = painter.fontMetrics()
        elided_text = main_metrics.elidedText(text, Qt.ElideRight, available_text_width)

        # 1. 绘制左侧主文本
        painter.setPen(text_color)
        painter.setFont(option.font)
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, elided_text)

        # 2. 绘制右侧快捷键（加粗版）
        if hotkey:
            painter.setFont(hotkey_font)
            painter.setPen(hotkey_color)
            painter.drawText(text_rect, Qt.AlignRight | Qt.AlignVCenter, hotkey)

        painter.restore()