"""自绘的小部件：图标按钮、日期格、勾选圈、色块、开关、待办行等。"""

from datetime import datetime

from PySide6.QtCore import QPointF, QRectF, Qt, QTime, Signal
from PySide6.QtGui import (
    QColor,
    QConicalGradient,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from .theme import PRESET_ACCENTS, Theme, rgba, with_alpha


def repolish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


class IconButton(QAbstractButton):
    def __init__(self, theme: Theme, kind: str, size: int = 28, tooltip: str = "", danger: bool = False):
        super().__init__()
        self.theme = theme
        self.kind = kind
        self.danger = danger
        self._hover = False
        self.active = False
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        if tooltip:
            self.setToolTip(tooltip)

    def setActive(self, active: bool) -> None:
        self.active = bool(active)
        self.update()

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)

        if self._hover:
            color = QColor(255, 90, 90, 40) if self.danger else QColor(255, 255, 255, 20)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(rect, 7, 7)
            color = QColor("#ff8d8d") if self.danger else QColor(244, 239, 231, 235)
        elif self.active:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(with_alpha(self.theme.accent, 36))
            painter.drawRoundedRect(rect, 7, 7)
            color = QColor(self.theme.accent)
        else:
            color = QColor(244, 239, 231, 140)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        pen = QPen(color, 1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)

        cx = self.width() / 2
        cy = self.height() / 2
        kind = self.kind

        if kind == "opacity":
            r = 6.5
            painter.drawEllipse(QPointF(cx, cy), r, r)
            path = QPainterPath()
            path.moveTo(cx, cy - r)
            path.arcTo(QRectF(cx - r, cy - r, r * 2, r * 2), 90, -180)
            path.closeSubpath()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawPath(path)
        elif kind == "pin":
            painter.drawLine(QPointF(cx, cy + 6), QPointF(cx, cy - 6))
            painter.drawLine(QPointF(cx - 4, cy - 1), QPointF(cx, cy - 5))
            painter.drawLine(QPointF(cx + 4, cy - 1), QPointF(cx, cy - 5))
            painter.drawLine(QPointF(cx - 6, cy + 8), QPointF(cx + 6, cy + 8))
        elif kind == "idea":
            painter.drawEllipse(QPointF(cx, cy - 1.8), 4.4, 4.6)
            painter.drawLine(QPointF(cx - 2.2, cy + 2.8), QPointF(cx - 2.2, cy + 5.2))
            painter.drawLine(QPointF(cx + 2.2, cy + 2.8), QPointF(cx + 2.2, cy + 5.2))
            painter.drawLine(QPointF(cx - 1.6, cy + 7.2), QPointF(cx + 1.6, cy + 7.2))
        elif kind == "clock":
            painter.drawEllipse(QPointF(cx, cy), 5.6, 5.6)
            painter.drawLine(QPointF(cx, cy), QPointF(cx, cy - 3.2))
            painter.drawLine(QPointF(cx, cy), QPointF(cx + 2.6, cy + 1.2))
        elif kind == "close":
            painter.drawLine(QPointF(cx - 4.5, cy - 4.5), QPointF(cx + 4.5, cy + 4.5))
            painter.drawLine(QPointF(cx + 4.5, cy - 4.5), QPointF(cx - 4.5, cy + 4.5))
        elif kind == "chevron_left":
            painter.drawLine(QPointF(cx + 2, cy - 5), QPointF(cx - 3, cy))
            painter.drawLine(QPointF(cx - 3, cy), QPointF(cx + 2, cy + 5))
        elif kind == "chevron_right":
            painter.drawLine(QPointF(cx - 2, cy - 5), QPointF(cx + 3, cy))
            painter.drawLine(QPointF(cx + 3, cy), QPointF(cx - 2, cy + 5))


class BrandDot(QWidget):
    def __init__(self, theme: Theme):
        super().__init__()
        self.theme = theme
        self.setFixedSize(12, 12)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        center = QPointF(6, 6)
        glow = QRadialGradient(center, 6)
        glow.setColorAt(0, with_alpha(self.theme.accent, 150))
        glow.setColorAt(1, with_alpha(self.theme.accent, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(center, 6, 6)
        painter.setBrush(self.theme.accent)
        painter.drawEllipse(center, 3, 3)


class DayButton(QAbstractButton):
    def __init__(self, theme: Theme):
        super().__init__()
        self.theme = theme
        self.date_key = ""
        self.day_number = 1
        self.in_month = True
        self.is_today = False
        self.selected = False
        self.dot = None
        self._hover = False
        self.setFixedHeight(34)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def configure(self, date_key: str, day_number: int, in_month: bool, is_today: bool, selected: bool, dot):
        self.date_key = date_key
        self.day_number = day_number
        self.in_month = in_month
        self.is_today = is_today
        self.selected = selected
        self.dot = dot
        self.update()

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect())

        if self.selected:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self.theme.accent)
            painter.drawRoundedRect(rect, 9, 9)
        elif self._hover:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 255, 255, 20))
            painter.drawRoundedRect(rect, 9, 9)

        if self.is_today and not self.selected:
            pen = QPen(with_alpha(self.theme.accent, 140), 1)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 9, 9)

        if self.selected:
            color = self.theme.ink
        elif not self.in_month:
            color = QColor(244, 239, 231, 51)
        else:
            color = QColor(244, 239, 231, 219)

        font = QFont("Microsoft YaHei UI")
        font.setPixelSize(12)
        font.setWeight(QFont.Weight.DemiBold if self.selected else QFont.Weight.Normal)
        painter.setFont(font)
        painter.setPen(color)
        text_rect = QRectF(0, -1 if self.dot else 0, self.width(), self.height())
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, str(self.day_number))

        if self.dot:
            painter.setPen(Qt.PenStyle.NoPen)
            if self.selected:
                dot_color = self.theme.ink
            elif self.dot == "pending":
                dot_color = self.theme.accent
            else:
                dot_color = QColor(244, 239, 231, 72)
            painter.setBrush(dot_color)
            painter.drawEllipse(QPointF(self.width() / 2, self.height() - 6), 1.6, 1.6)


class CheckButton(QAbstractButton):
    def __init__(self, theme: Theme):
        super().__init__()
        self.theme = theme
        self._hover = False
        self.setFixedSize(16, 16)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setToolTip("标记完成 / 取消")

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(1.2, 1.2, -1.2, -1.2)

        if self.isChecked():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self.theme.accent)
            painter.drawEllipse(rect)
            pen = QPen(self.theme.ink, 2.2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            cx = self.width() / 2
            cy = self.height() / 2
            painter.drawLine(QPointF(cx - 3.4, cy + 0.2), QPointF(cx - 1.0, cy + 2.6))
            painter.drawLine(QPointF(cx - 1.0, cy + 2.6), QPointF(cx + 3.8, cy - 2.4))
        else:
            color = self.theme.accent if self._hover else QColor(244, 239, 231, 77)
            painter.setPen(QPen(color, 1.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(rect)


class Switch(QAbstractButton):
    def __init__(self, theme: Theme):
        super().__init__()
        self.theme = theme
        self.setFixedSize(34, 19)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        track = QRectF(0, 0, 34, 19)
        if self.isChecked():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self.theme.accent)
            painter.drawRoundedRect(track, 9.5, 9.5)
            knob = self.theme.ink
            knob_x = 34 - 2.5 - 14
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 255, 255, 38))
            painter.drawRoundedRect(track, 9.5, 9.5)
            knob = QColor(255, 255, 255, 224)
            knob_x = 2.5
        painter.setBrush(knob)
        painter.drawEllipse(QRectF(knob_x, 2.5, 14, 14))


class SwatchButton(QAbstractButton):
    def __init__(self, theme: Theme, color_hex: str, custom: bool = False):
        super().__init__()
        self.theme = theme
        self.color_hex = color_hex
        self.custom = custom
        self.selected = False
        self._hover = False
        self.setFixedSize(18, 18)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def set_selected(self, selected: bool) -> None:
        self.selected = bool(selected)
        self.update()

    def set_color(self, color_hex: str) -> None:
        self.color_hex = color_hex
        self.update()

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        center = QPointF(9, 9)
        inner = 5.7

        painter.setPen(Qt.PenStyle.NoPen)
        if self.custom:
            gradient = QConicalGradient(center, 210)
            count = len(PRESET_ACCENTS)
            for index, color in enumerate(PRESET_ACCENTS):
                gradient.setColorAt(index / count, QColor(color))
            gradient.setColorAt(1.0, QColor(PRESET_ACCENTS[0]))
            painter.setBrush(gradient)
        else:
            painter.setBrush(QColor(self.color_hex))
        painter.drawEllipse(center, inner, inner)

        if self.selected:
            ring = self.theme.accent if self.custom else QColor(self.color_hex)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(ring, 1.6))
            painter.drawEllipse(center, 8.1, 8.1)
        elif self._hover:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(255, 255, 255, 70), 1.0))
            painter.drawEllipse(center, 8.1, 8.1)


class AddButton(QAbstractButton):
    def __init__(self, theme: Theme):
        super().__init__()
        self.theme = theme
        self._hover = False
        self.setFixedSize(26, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setToolTip("添加")

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        color = QColor(self.theme.accent)
        if self._hover:
            color = color.lighter(108)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(QRectF(self.rect()), 8, 8)
        pen = QPen(self.theme.ink, 2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        cx, cy = self.width() / 2, self.height() / 2
        painter.drawLine(QPointF(cx, cy - 5.5), QPointF(cx, cy + 5.5))
        painter.drawLine(QPointF(cx - 5.5, cy), QPointF(cx + 5.5, cy))


class DelButton(QAbstractButton):
    def __init__(self, theme: Theme):
        super().__init__()
        self.theme = theme
        self.row_hovered = False
        self._hover = False
        self.setFixedSize(18, 18)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setToolTip("删除")
        self.setEnabled(False)

    def set_row_hovered(self, hovered: bool) -> None:
        self.row_hovered = hovered
        self.setEnabled(hovered)
        self.update()

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        if not self.row_hovered:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self._hover:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 90, 90, 36))
            painter.drawRoundedRect(QRectF(self.rect()), 6, 6)
            color = QColor("#ff9a9a")
        else:
            color = QColor(244, 239, 231, 102)
        pen = QPen(color, 1.7)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        cx, cy = self.width() / 2, self.height() / 2
        painter.drawLine(QPointF(cx - 3.2, cy - 3.2), QPointF(cx + 3.2, cy + 3.2))
        painter.drawLine(QPointF(cx + 3.2, cy - 3.2), QPointF(cx - 3.2, cy + 3.2))


class ProgressBar(QWidget):
    def __init__(self, theme: Theme, height: int = 2):
        super().__init__()
        self.theme = theme
        self.value = 0.0
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_value(self, value: float) -> None:
        self.value = max(0.0, min(1.0, float(value)))
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        h = self.height()
        radius = h / 2
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 18))
        painter.drawRoundedRect(QRectF(0, 0, self.width(), h), radius, radius)
        if self.value > 0:
            painter.setBrush(self.theme.accent)
            painter.drawRoundedRect(QRectF(0, 0, self.width() * self.value, h), radius, radius)


class EditableLabel(QLabel):
    doubleClicked = Signal()

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.doubleClicked.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class DeadlineLabel(QLabel):
    clicked = Signal()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)


class DeadlineDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        theme: Theme,
        initial: QTime | None = None,
        allow_clear: bool = False,
        title: str = "设置限时任务",
    ):
        super().__init__(parent)
        self.theme = theme
        self._action = "cancel"
        self.setWindowTitle(title)
        self.setModal(True)
        self.setFixedWidth(260)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 14)
        layout.setSpacing(12)

        label = QLabel("截止时间（HH:mm）")
        layout.addWidget(label)

        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("HH:mm")
        self.time_edit.setTime(initial if initial is not None else self._default_time())
        self.time_edit.setFixedHeight(34)
        layout.addWidget(self.time_edit)

        box = QDialogButtonBox()
        ok = box.addButton("确定", QDialogButtonBox.ButtonRole.AcceptRole)
        cancel = box.addButton("取消", QDialogButtonBox.ButtonRole.RejectRole)
        clear = None
        if allow_clear:
            clear = box.addButton("移除限时", QDialogButtonBox.ButtonRole.DestructiveRole)

        ok.clicked.connect(self._accept)
        cancel.clicked.connect(self.reject)
        if clear is not None:
            clear.clicked.connect(self._clear)
        layout.addWidget(box)

        self.setStyleSheet(
            """
            QDialog { background: #202027; }
            QLabel {
                color: #f4efe7;
                background: transparent;
                font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI";
                font-size: 12px;
            }
            QTimeEdit {
                background: rgba(255,255,255,15);
                border: 1px solid rgba(255,255,255,35);
                border-radius: 6px;
                color: #f4efe7;
                padding: 4px 8px;
                font-size: 16px;
            }
            QPushButton {
                background: rgba(255,255,255,14);
                border: 1px solid rgba(255,255,255,30);
                border-radius: 6px;
                color: #f4efe7;
                padding: 5px 12px;
                font-size: 12px;
            }
            QPushButton:hover { background: rgba(255,255,255,24); }
            """
        )
        ok.setStyleSheet(
            f"QPushButton {{ background: {theme.accent_hex}; color: {theme.ink_hex};"
            " border: none; border-radius: 6px; padding: 5px 14px; font-size: 12px; }"
            f" QPushButton:hover {{ background: {QColor(theme.accent_hex).lighter(108).name()}; }}"
        )
        if clear is not None:
            clear.setStyleSheet("QPushButton { color: #ff9a9a; }")

        self.time_edit.setFocus()

    @staticmethod
    def _default_time() -> QTime:
        now = QTime.currentTime()
        candidate = now.addSecs(3600)
        return QTime(23, 59) if candidate < now else candidate

    def _accept(self) -> None:
        self._action = "set"
        self.accept()

    def _clear(self) -> None:
        self._action = "clear"
        self.accept()

    @classmethod
    def get(
        cls,
        parent: QWidget,
        theme: Theme,
        initial: QTime | None = None,
        allow_clear: bool = False,
        title: str = "设置限时任务",
    ):
        dialog = cls(parent, theme, initial, allow_clear, title)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog._action, dialog.time_edit.time()
        return "cancel", None


class InlineEdit(QLineEdit):
    committed = Signal(str)
    cancelled = Signal()

    def __init__(self, theme: Theme):
        super().__init__()
        self.theme = theme
        self._finished = False
        self.setFixedHeight(22)
        self.setStyleSheet(
            "QLineEdit {"
            " background: rgba(255,255,255,18);"
            f" border: 1px solid {rgba(theme.accent, 115)};"
            " border-radius: 6px; color: #f4efe7; padding: 1px 6px; font-size: 12px;"
            "}"
        )

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            event.accept()
            self._finish(True)
            return
        if event.key() == Qt.Key.Key_Escape:
            event.accept()
            self._finish(False)
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self._finish(True)

    def _finish(self, commit: bool) -> None:
        if self._finished:
            return
        self._finished = True
        if commit:
            self.committed.emit(self.text())
        else:
            self.cancelled.emit()


class TodoRow(QWidget):
    toggled = Signal(str)
    deleted = Signal(str)
    edited = Signal(str, str)
    deadlineClicked = Signal(str)

    def __init__(self, item: dict, theme: Theme):
        super().__init__()
        self.item = item
        self.theme = theme
        self._hover = False
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 7, 4, 7)
        layout.setSpacing(7)

        self.check = CheckButton(theme)
        self.check.setChecked(bool(item.get("done")))
        self.check.clicked.connect(lambda: self.toggled.emit(self.item["id"]))
        layout.addWidget(self.check, 0, Qt.AlignmentFlag.AlignTop)

        self.label = EditableLabel()
        self.label.setWordWrap(True)
        self.label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.label.setText(item.get("text", ""))
        self.label.setToolTip("双击编辑")
        self.label.doubleClicked.connect(self.begin_edit)

        self.edit = InlineEdit(theme)
        self.edit.hide()
        self.edit.committed.connect(self._on_edit_done)
        self.edit.cancelled.connect(self._on_edit_cancel)

        self.meta = DeadlineLabel()
        self.meta.setCursor(Qt.CursorShape.PointingHandCursor)
        self.meta.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.meta.hide()
        self.meta.clicked.connect(lambda: self.deadlineClicked.emit(self.item["id"]))

        text_box = QVBoxLayout()
        text_box.setContentsMargins(0, 0, 0, 0)
        text_box.setSpacing(1)
        text_box.addWidget(self.label)
        text_box.addWidget(self.meta)
        text_box.addWidget(self.edit)
        layout.addLayout(text_box, 1)

        self.delete = DelButton(theme)
        self.delete.clicked.connect(lambda: self.deleted.emit(self.item["id"]))
        layout.addWidget(self.delete, 0, Qt.AlignmentFlag.AlignTop)

        self._apply_done_style()
        self.refresh_deadline()

    def _apply_done_style(self) -> None:
        done = bool(self.item.get("done"))
        font = QFont("Microsoft YaHei UI")
        font.setPixelSize(13)
        font.setStrikeOut(done)
        self.label.setFont(font)
        color = "rgba(244, 239, 231, 82)" if done else "rgba(244, 239, 231, 230)"
        self.label.setStyleSheet(f"color: {color}; background: transparent;")

    def refresh_deadline(self, now_ms=None) -> None:
        due = self.item.get("dueAt")
        if not isinstance(due, (int, float)) or due <= 0:
            self.meta.hide()
            self.check.setToolTip("标记完成 / 取消")
            return
        try:
            stamp = datetime.fromtimestamp(float(due) / 1000).strftime("%H:%M")
        except (ValueError, OSError, OverflowError):
            self.meta.hide()
            return

        if now_ms is None:
            now_ms = int(datetime.now().timestamp() * 1000)

        if self.item.get("done"):
            text = f"{stamp} 打卡"
            color = "rgba(244, 239, 231, 82)"
        elif due <= now_ms:
            text = f"超时 · {stamp}"
            color = "#ff8d8d"
        else:
            text = f"{stamp} 前打卡"
            color = self.theme.accent_text_hex

        self.meta.setText(text)
        self.meta.setStyleSheet(
            f"color: {color}; background: transparent; font-size: 9px; padding: 0;"
        )
        self.meta.setToolTip("点击修改或移除限时")
        self.meta.show()
        self.check.setToolTip("打卡完成 / 取消")

    def begin_edit(self) -> None:
        self.label.hide()
        self.edit.setText(self.item.get("text", ""))
        self.edit.show()
        self.edit.setFocus()
        self.edit.selectAll()

    def _on_edit_done(self, text: str) -> None:
        text = text.strip()
        if text and text != self.item.get("text", ""):
            self.edited.emit(self.item["id"], text)
        else:
            self._on_edit_cancel()

    def _on_edit_cancel(self) -> None:
        self.edit.hide()
        self.label.show()

    def enterEvent(self, event) -> None:
        self._hover = True
        self.delete.set_row_hovered(True)
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.delete.set_row_hovered(False)
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        if not self._hover:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 13))
        painter.drawRoundedRect(QRectF(self.rect()), 9, 9)


def _format_idea_time(created_at) -> str:
    if not created_at:
        return ""
    try:
        return datetime.fromtimestamp(float(created_at) / 1000).strftime("%m月%d日 %H:%M")
    except (ValueError, OSError, OverflowError):
        return ""


class IdeaRow(QWidget):
    opened = Signal(object)
    deleted = Signal(str)

    def __init__(self, item: dict, theme: Theme):
        super().__init__()
        self.item = item
        self.theme = theme
        self._hover = False
        children = item.get("children") or []
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("双击进入，记录子灵感")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 10, 10)
        layout.setSpacing(8)

        self.label = EditableLabel()
        self.label.setWordWrap(True)
        self.label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.label.setText(item.get("text", ""))
        self.label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.label.setToolTip("双击进入，记录子灵感")
        self.label.doubleClicked.connect(lambda: self.opened.emit(self.item))
        font = QFont("Microsoft YaHei UI")
        font.setPixelSize(13)
        self.label.setFont(font)
        self.label.setStyleSheet("color: rgba(244,239,231,230); background: transparent;")
        layout.addWidget(self.label, 1)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(2)

        meta_parts = []
        time_text = _format_idea_time(item.get("createdAt"))
        if time_text:
            meta_parts.append(time_text)
        if children:
            meta_parts.append(f"{len(children)} 个子灵感")
        self.meta_label = QLabel(" · ".join(meta_parts) if meta_parts else "双击进入")
        self.meta_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop
        )
        self.meta_label.setStyleSheet(
            "color: rgba(244,239,231,88); background: transparent; font-size: 9px;"
        )
        right.addWidget(self.meta_label)

        self.delete = DelButton(theme)
        self.delete.setToolTip("删除（会一并删除子灵感）" if children else "删除")
        self.delete.clicked.connect(lambda: self.deleted.emit(self.item["id"]))
        right.addWidget(self.delete, 0, Qt.AlignmentFlag.AlignRight)
        right.addStretch(1)
        layout.addLayout(right)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.opened.emit(self.item)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def enterEvent(self, event) -> None:
        self._hover = True
        self.delete.set_row_hovered(True)
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.delete.set_row_hovered(False)
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QPen(QColor(255, 255, 255, 20), 1))
        painter.setBrush(QColor(255, 255, 255, 16 if self._hover else 10))
        painter.drawRoundedRect(rect, 10, 10)

        pen = QPen(with_alpha(self.theme.accent, 170), 2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawLine(QPointF(5.5, 10), QPointF(5.5, self.height() - 10))


class MonthCard(QFrame):
    def __init__(self, theme: Theme):
        super().__init__()
        self.theme = theme
        self.setObjectName("monthCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(84)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 11)
        layout.setSpacing(6)

        title = QLabel("本月")
        title.setObjectName("monthTitleSmall")
        layout.addWidget(title)

        self.stat = QLabel("本月暂无待办")
        self.stat.setObjectName("monthStat")
        layout.addWidget(self.stat)

        self.bar = ProgressBar(theme, 3)
        layout.addWidget(self.bar)
        layout.addStretch(1)

    def update_stats(self, total: int, done: int) -> None:
        self.stat.setText(f"{total} 项待办 · 已完成 {done}" if total else "本月暂无待办")
        self.bar.set_value(done / total if total else 0.0)


class EmptyState(QWidget):
    def __init__(self, title_text="这天还没有待办", hint_text="在下方输入，回车即可添加"):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(4)
        layout.addStretch(1)

        title = QLabel(title_text)
        title.setObjectName("emptyTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        hint = QLabel(hint_text)
        hint.setObjectName("emptyHint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)
        layout.addStretch(1)


def divider() -> QFrame:
    line = QFrame()
    line.setObjectName("popDivider")
    line.setFixedHeight(1)
    return line
