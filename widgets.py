"""自绘组件库：进度环、日历格、勾选动画、热力图、行内编辑、Toast。

所有颜色都从 `Theme` 实时读取（主题对象是共享可变实例），因此切换深浅主题
只需要重建 QSS 并 `update()`，不需要重建控件树。
"""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QWidget,
)

from .theme import Theme, with_alpha
from .quickadd import WEEKDAY_NAMES, WEEKDAY_FULL

PRIORITY_COLORS = {1: "#f2b64b", 2: "#ff6f61"}
RING_TRACK_ALPHA = 46


def repolish(widget: QWidget) -> None:
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def elide(text: str, font: QFont, width: int) -> str:
    metrics = QFontMetrics(font)
    return metrics.elidedText(text, Qt.TextElideMode.ElideRight, max(10, width))


class IconButton(QAbstractButton):
    """矢量图标按钮：搜索 / 设置 / 置顶 / 关闭 / 左右箭头 / 加号 / 撤销。"""

    def __init__(self, theme: Theme, kind: str, size: int = 26, tooltip: str = "") -> None:
        super().__init__()
        self.theme = theme
        self.kind = kind
        self._size = size
        self._hover = False
        self._active = False
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        if tooltip:
            self.setToolTip(tooltip)

    def set_active(self, value: bool) -> None:
        if self._active != value:
            self._active = value
            self.update()

    def sizeHint(self) -> QSize:
        return QSize(self._size, self._size)

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
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())
        if self._hover:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self.theme.hover)
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 8, 8)

        if self.kind == "pin" and self._active:
            color = self.theme.accent
        elif self._hover:
            color = self.theme.text
        else:
            color = self.theme.muted
        painter.setPen(
            QPen(color, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        )
        painter.setBrush(Qt.BrushStyle.NoBrush)

        c = rect.center()
        w = rect.width()
        h = rect.height()
        span = w * 0.30  # 图标半尺寸

        if self.kind == "close":
            painter.drawLine(c.x() - span * 0.8, c.y() - span * 0.8, c.x() + span * 0.8, c.y() + span * 0.8)
            painter.drawLine(c.x() + span * 0.8, c.y() - span * 0.8, c.x() - span * 0.8, c.y() + span * 0.8)
        elif self.kind == "search":
            radius = span * 0.85
            off = span * 0.2
            painter.drawEllipse(QRectF(c.x() - radius - off, c.y() - radius - off, radius * 2, radius * 2))
            painter.drawLine(
                c.x() + radius * 0.62,
                c.y() + radius * 0.62,
                c.x() + radius * 1.5,
                c.y() + radius * 1.5,
            )
        elif self.kind == "settings":
            radius = span * 0.42
            painter.drawEllipse(QRectF(c.x() - radius, c.y() - radius, radius * 2, radius * 2))
            painter.drawEllipse(
                QRectF(c.x() - span * 1.05, c.y() - span * 1.05, span * 2.1, span * 2.1)
            )
            gx = span * 1.05
            for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0), (-0.72, -0.72), (0.72, 0.72), (-0.72, 0.72), (0.72, -0.72)):
                painter.drawLine(
                    QPoint(int(c.x() + dx * gx), int(c.y() + dy * gx)),
                    QPoint(int(c.x() + dx * gx * 1.42), int(c.y() + dy * gx * 1.42)),
                )
        elif self.kind == "pin":
            path = QPainterPath()
            path.moveTo(c.x() - span * 0.55, c.y() - span * 0.95)
            path.lineTo(c.x() + span * 0.55, c.y() - span * 0.95)
            path.lineTo(c.x() + span * 0.28, c.y() - span * 0.1)
            path.lineTo(c.x() + span * 0.28, c.y() + span * 0.55)
            path.lineTo(c.x() - span * 0.28, c.y() + span * 0.55)
            path.lineTo(c.x() - span * 0.28, c.y() - span * 0.1)
            path.closeSubpath()
            painter.drawPath(path)
            painter.drawLine(QPointF(c.x(), c.y() + span * 0.55), QPointF(c.x(), c.y() + span * 1.15))
        elif self.kind == "chevron_left":
            painter.drawLine(
                QPointF(c.x() + span * 0.35, c.y() - span * 0.7),
                QPointF(c.x() - span * 0.4, c.y()),
            )
            painter.drawLine(
                QPointF(c.x() - span * 0.4, c.y()),
                QPointF(c.x() + span * 0.35, c.y() + span * 0.7),
            )
        elif self.kind == "chevron_right":
            painter.drawLine(
                QPointF(c.x() - span * 0.35, c.y() - span * 0.7),
                QPointF(c.x() + span * 0.4, c.y()),
            )
            painter.drawLine(
                QPointF(c.x() + span * 0.4, c.y()),
                QPointF(c.x() - span * 0.35, c.y() + span * 0.7),
            )
        elif self.kind == "undo":
            painter.drawArc(
                QRectF(c.x() - span, c.y() - span * 0.85, span * 2, span * 1.7), 40 * 16, 250 * 16
            )
            painter.drawLine(
                QPointF(c.x() - span * 0.95, c.y() - span * 0.5),
                QPointF(c.x() - span * 0.35, c.y() - span * 0.95),
            )
        elif self.kind == "trash":
            painter.drawLine(
                QPointF(c.x() - span * 0.8, c.y() - span * 0.6),
                QPointF(c.x() + span * 0.8, c.y() - span * 0.6),
            )
            painter.drawLine(
                QPointF(c.x() - span * 0.35, c.y() - span * 0.95),
                QPointF(c.x() + span * 0.35, c.y() - span * 0.95),
            )
            path = QPainterPath()
            path.moveTo(c.x() - span * 0.62, c.y() - span * 0.6)
            path.lineTo(c.x() - span * 0.5, c.y() + span * 0.9)
            path.lineTo(c.x() + span * 0.5, c.y() + span * 0.9)
            path.lineTo(c.x() + span * 0.62, c.y() - span * 0.6)
            painter.drawPath(path)
        elif self.kind == "dot":
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QRectF(c.x() - span * 0.5, c.y() - span * 0.5, span, span))


class BrandDot(QWidget):
    def __init__(self, theme: Theme, size: int = 14) -> None:
        super().__init__()
        self.theme = theme
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center = QRectF(self.rect()).center()
        radius = self.width() * 0.22
        glow = QColor(self.theme.accent)
        glow.setAlpha(70)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(center, radius * 2.2, radius * 2.2)
        painter.setBrush(self.theme.accent)
        painter.drawEllipse(center, radius, radius)


class AccentFab(QAbstractButton):
    """强调色圆形按钮（快速添加的 +）。"""

    def __init__(self, theme: Theme, size: int = 26) -> None:
        super().__init__()
        self.theme = theme
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("添加（回车）")

    def sizeHint(self) -> QSize:
        return self.size()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())
        pressed = self.isDown()
        shrink = 1.0 if not pressed else 0.97
        circle = rect.adjusted(1, 1, -1, -1)
        if shrink != 1.0:
            circle = QRectF(
                circle.center().x() - circle.width() * shrink / 2,
                circle.center().y() - circle.height() * shrink / 2,
                circle.width() * shrink,
                circle.height() * shrink,
            )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.theme.accent if self.underMouse() or pressed else with_alpha(self.theme.accent, 235))
        painter.drawEllipse(circle)
        painter.setPen(
            QPen(self.theme.ink, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        )
        cx = circle.center().x()
        cy = circle.center().y()
        half = circle.width() * 0.22
        painter.drawLine(QPoint(int(cx - half), int(cy)), QPoint(int(cx + half), int(cy)))
        painter.drawLine(QPoint(int(cx), int(cy - half)), QPoint(int(cx), int(cy + half)))


class DayCell(QAbstractButton):
    """日历格。周视图与月视图共用，只是尺寸和字号不同。"""

    def __init__(self, theme: Theme, compact: bool = False) -> None:
        super().__init__()
        self.theme = theme
        self.compact = compact
        self.day: date | None = None
        self.in_month = True
        self.is_today = False
        self.selected = False
        self.marker = 0  # 0 无 / 1 有未完成 / 2 全部完成
        self.weekday_label = ""
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        if compact:
            self.setMinimumSize(1, 46)
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        else:
            self.setFixedHeight(32)
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def configure(
        self,
        day: date,
        *,
        in_month: bool = True,
        is_today: bool = False,
        selected: bool = False,
        marker: int = 0,
        weekday_label: str = "",
    ) -> None:
        self.day = day
        self.in_month = in_month
        self.is_today = is_today
        self.selected = selected
        self.marker = marker
        self.weekday_label = weekday_label
        self.update()

    def paintEvent(self, event) -> None:
        if self.day is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        theme = self.theme
        rect = QRectF(self.rect()).adjusted(2, 1, -2, -1)

        if self.selected:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(theme.accent)
            painter.drawRoundedRect(rect, 9, 9)
        elif self.underMouse():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(theme.hover)
            painter.drawRoundedRect(rect, 9, 9)
        elif self.is_today:
            pen = QPen(with_alpha(theme.accent, 120), 1.0)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 9, 9)

        if self.compact:
            self._paint_compact(painter, rect)
        else:
            self._paint_month(painter, rect)

    def _day_color(self) -> QColor:
        theme = self.theme
        if self.selected:
            return theme.ink
        if not self.in_month:
            return theme.faint
        if self.is_today:
            return QColor(theme.accent_text_hex)
        return theme.text

    def _paint_compact(self, painter: QPainter, rect: QRectF) -> None:
        theme = self.theme
        if self.weekday_label:
            font = painter.font()
            font.setPixelSize(9)
            painter.setFont(font)
            weekday_color = QColor(theme.ink) if self.selected else theme.faint
            painter.setPen(weekday_color)
            painter.drawText(
                QRectF(rect.left(), rect.top() + 2, rect.width(), 11),
                Qt.AlignmentFlag.AlignCenter,
                self.weekday_label,
            )
        font = painter.font()
        font.setPixelSize(12)
        font.setWeight(QFont.Weight.DemiBold if self.selected or self.is_today else QFont.Weight.Normal)
        painter.setFont(font)
        painter.setPen(self._day_color())
        painter.drawText(
            QRectF(rect.left(), rect.top() + 13, rect.width(), 17),
            Qt.AlignmentFlag.AlignCenter,
            str(self.day.day),
        )
        self._paint_marker(painter, rect, y=rect.top() + 32)

    def _paint_month(self, painter: QPainter, rect: QRectF) -> None:
        font = painter.font()
        font.setPixelSize(11.5)
        font.setWeight(QFont.Weight.DemiBold if self.selected or self.is_today else QFont.Weight.Normal)
        painter.setFont(font)
        painter.setPen(self._day_color())
        painter.drawText(rect.adjusted(0, -1, 0, -1), Qt.AlignmentFlag.AlignCenter, str(self.day.day))
        self._paint_marker(painter, rect, y=rect.bottom() - 7)

    def _paint_marker(self, painter: QPainter, rect: QRectF, y: float) -> None:
        if not self.marker:
            return
        color = QColor(self.theme.ink) if self.selected else self.theme.accent
        if self.marker == 2:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(QRectF(rect.center().x() - 1.6, y - 1.6, 3.2, 3.2))
        else:
            pen = QPen(color, 1.0)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QRectF(rect.center().x() - 1.5, y - 1.5, 3.0, 3.0))


class CheckButton(QAbstractButton):
    """勾选框：0.16s 的填充 + 描边动画，替代原版瞬间切换。"""

    def __init__(self, theme: Theme, size: int = 20) -> None:
        super().__init__()
        self.theme = theme
        self._progress = 0.0
        self._hover = False
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(170)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_value)
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def sizeHint(self) -> QSize:
        return self.size()

    def set_checked(self, checked: bool, animate: bool = True) -> None:
        target = 1.0 if checked else 0.0
        self._anim.stop()
        if not animate:
            self._progress = target
            self.update()
            return
        self._anim.setStartValue(self._progress)
        self._anim.setEndValue(target)
        self._anim.start()

    def _on_value(self, value) -> None:
        try:
            self._progress = float(value)
        except (TypeError, ValueError):
            self._progress = 0.0
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
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        theme = self.theme
        rect = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        progress = max(0.0, min(1.0, self._progress))

        if progress > 0.01:
            painter.setPen(Qt.PenStyle.NoPen)
            fill = QColor(theme.accent)
            fill.setAlphaF(progress)
            painter.setBrush(fill)
            painter.drawEllipse(rect)
            border = QColor(theme.accent)
            border.setAlphaF(progress)
        else:
            border = with_alpha(theme.text, 96 if self._hover else 72)
        painter.setPen(QPen(border, 1.3))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(rect)

        if progress > 0.05:
            painter.save()
            clip = QRectF(rect.left(), rect.top(), rect.width() * progress, rect.height())
            painter.setClipRect(clip)
            pen = QPen(theme.ink, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.drawLine(
                QPointF(rect.left() + rect.width() * 0.26, rect.center().y() + rect.height() * 0.02),
                QPointF(rect.left() + rect.width() * 0.44, rect.bottom() - rect.height() * 0.26),
            )
            painter.drawLine(
                QPointF(rect.left() + rect.width() * 0.44, rect.bottom() - rect.height() * 0.26),
                QPointF(rect.left() + rect.width() * 0.76, rect.top() + rect.height() * 0.28),
            )
            painter.restore()


class Switch(QAbstractButton):
    def __init__(self, theme: Theme, width: int = 34, height: int = 19) -> None:
        super().__init__()
        self.theme = theme
        self._checked = False
        self._pos = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_value)
        self.setFixedSize(width, height)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.clicked.connect(self._toggle_on_click)

    def _toggle_on_click(self) -> None:
        self.set_checked(not self._checked)

    def sizeHint(self) -> QSize:
        return self.size()

    def isChecked(self) -> bool:  # noqa: N802 - 跟随 Qt 命名
        return self._checked

    def set_checked(self, checked: bool, animate: bool = True) -> None:
        self._checked = bool(checked)
        target = 1.0 if self._checked else 0.0
        self._anim.stop()
        if not animate:
            self._pos = target
            self.update()
            return
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(target)
        self._anim.start()

    def _on_value(self, value) -> None:
        try:
            self._pos = float(value)
        except (TypeError, ValueError):
            self._pos = 0.0
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = rect.height() / 2
        if self._pos <= 0.001:
            painter.setPen(QPen(self.theme.line, 1))
            painter.setBrush(self.theme.track)
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            fill = QColor(self.theme.accent)
            fill.setAlpha(int(60 + 195 * self._pos))
            painter.setBrush(fill)
        painter.drawRoundedRect(rect, radius, radius)

        knob_radius = radius - 3
        left = rect.left() + 3 + knob_radius
        right = rect.right() - 3 - knob_radius
        cx = left + (right - left) * self._pos
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.theme.ink if self._pos > 0.5 else self.theme.muted)
        painter.drawEllipse(QRectF(cx - knob_radius, rect.center().y() - knob_radius, knob_radius * 2, knob_radius * 2))


class SwatchButton(QAbstractButton):
    def __init__(self, theme: Theme, color: str, size: int = 20) -> None:
        super().__init__()
        self.theme = theme
        self.color = color
        self._selected = False
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def set_selected(self, value: bool) -> None:
        if self._selected != value:
            self._selected = value
            self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        if self._selected:
            painter.setPen(QPen(self.theme.text, 1.2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(rect)
            rect = rect.adjusted(3, 3, -3, -3)
        elif self.underMouse():
            rect = rect.adjusted(1, 1, -1, -1)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self.color))
        painter.drawEllipse(rect)


class ProgressRing(QWidget):
    """今日进度环：环心显示 done/total。"""

    def __init__(self, theme: Theme, size: int = 62, thickness: float = 5.0) -> None:
        super().__init__()
        self.theme = theme
        self.thickness = thickness
        self.done = 0
        self.total = 0
        self._progress = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(320)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_value)
        self.setFixedSize(size, size)

    def set_data(self, done: int, total: int, animate: bool = True) -> None:
        target = (done / total) if total else 0.0
        self.done = done
        self.total = total
        if animate:
            self._anim.stop()
            self._anim.setStartValue(self._progress)
            self._anim.setEndValue(target)
            self._anim.start()
        else:
            self._progress = target
        self.update()

    def _on_value(self, value) -> None:
        try:
            self._progress = float(value)
        except (TypeError, ValueError):
            self._progress = 0.0
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        theme = self.theme
        rect = QRectF(self.rect()).adjusted(
            self.thickness / 2 + 1, self.thickness / 2 + 1, -self.thickness / 2 - 1, -self.thickness / 2 - 1
        )
        pen = QPen(with_alpha(theme.text, RING_TRACK_ALPHA), self.thickness)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawArc(rect, 0, 360 * 16)

        complete = self.total > 0 and self.done >= self.total
        accent = QColor(theme.accent)
        if complete:
            accent = QColor(theme.accent).lighter(108)
        if self._progress > 0.001:
            pen = QPen(accent, self.thickness)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawArc(rect, 90 * 16, -int(360 * 16 * min(1.0, self._progress)))

        font = painter.font()
        font.setPixelSize(13 if self.width() > 54 else 11)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(theme.text if self.total else theme.faint)
        text = f"{self.done}/{self.total}" if self.total else "—"
        painter.drawText(
            QRectF(self.rect()).adjusted(0, -1, 0, -1),
            Qt.AlignmentFlag.AlignCenter,
            text,
        )


class Heatmap(QWidget):
    """近 N 天完成情况：一条横向色带，越亮表示当天完成得越充分。

    原来打算画 7×4 的格子，但页脚只有 22px 高，格子必然被裁掉一半、糊成一团，
    所以改成单行色带 —— 一眼能看出「这周比上周忙/闲」。
    """

    CELL = 5
    GAP = 2
    HEIGHT = 12

    def __init__(self, theme: Theme, days: int = 28) -> None:
        super().__init__()
        self.theme = theme
        self.days = days
        self.data: list[dict] = []
        self.setFixedSize(days * (self.CELL + self.GAP) - self.GAP, self.HEIGHT)
        self.setToolTip("近 28 天完成情况")

    def set_data(self, data: list[dict]) -> None:
        self.data = data or []
        tips = []
        for item in self.data[-7:]:
            day: date = item["date"]
            tips.append(f"{day.month}/{day.day} {item['done']}/{item['total']}")
        if tips:
            self.setToolTip("近 28 天完成情况\n" + "　".join(tips))
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        theme = self.theme
        if not self.data:
            return
        painter.setPen(Qt.PenStyle.NoPen)
        for index, item in enumerate(self.data[-self.days :]):
            x = index * (self.CELL + self.GAP)
            cell = QRectF(x, 0, self.CELL, self.HEIGHT)
            total = item.get("total", 0)
            done = item.get("done", 0)
            if not total:
                color = QColor(theme.heat_empty)
            elif done == total:
                color = QColor(theme.accent)
            else:
                color = QColor(theme.accent)
                color.setAlpha(int(52 + 165 * (done / total)))
            painter.setBrush(color)
            painter.drawRoundedRect(cell, 2.0, 2.0)


class Toast(QWidget):
    """底部浮起的撤销提示条。"""

    def __init__(self, theme: Theme, parent: QWidget) -> None:
        super().__init__(parent)
        self.theme = theme
        self.message = ""
        self.action = ""
        self._callback = None
        self._action_rect = QRectF()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        self.hide()
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def show_message(self, message: str, action: str = "", callback=None, timeout: int = 4200) -> None:
        self.message = message
        self.action = action
        self._callback = callback
        self._layout()
        self.show()
        self.raise_()
        self._timer.start(timeout)

    def _layout(self) -> None:
        font = self.font()
        font.setPixelSize(11)
        metrics = QFontMetrics(font)
        width = metrics.horizontalAdvance(self.message) + 20
        if self.action:
            width += metrics.horizontalAdvance(self.action) + 16
        width = min(width, self.parent().width() - 24)
        self.resize(width, 30)
        self.move(
            max(8, (self.parent().width() - width) // 2),
            self.parent().height() - 118,
        )
        self._action_rect = (
            QRectF(width - metrics.horizontalAdvance(self.action) - 14, 0, metrics.horizontalAdvance(self.action) + 14, 30)
            if self.action
            else QRectF()
        )

    def mousePressEvent(self, event) -> None:
        if self._action_rect.contains(event.position()) and self._callback:
            callback = self._callback
            self.hide()
            callback()
        else:
            self.hide()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QPen(self.theme.line, 1))
        painter.setBrush(self.theme.palette.popover)
        painter.drawRoundedRect(rect, 9, 9)
        font = painter.font()
        font.setPixelSize(11)
        painter.setFont(font)
        painter.setPen(self.theme.muted)
        painter.drawText(
            rect.adjusted(10, 0, 0, 0),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self.message,
        )
        if self.action:
            painter.setPen(QColor(self.theme.accent_text_hex))
            painter.drawText(
                self._action_rect.adjusted(0, 0, -4, 0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                self.action,
            )


class Celebration(QWidget):
    """当日清零时的庆祝光晕。"""

    def __init__(self, theme: Theme, parent: QWidget) -> None:
        super().__init__(parent)
        self.theme = theme
        self.text = ""
        self._alpha = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(1500)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_value)
        self._anim.finished.connect(self.hide)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.hide()

    def play(self, text: str) -> None:
        self.text = text
        self._layout()
        self.show()
        self.raise_()
        self._anim.stop()
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()

    def _layout(self) -> None:
        parent = self.parent()
        self.setGeometry(0, 0, parent.width(), parent.height())

    def _on_value(self, value) -> None:
        self._alpha = float(value)
        self.update()

    def paintEvent(self, event) -> None:
        if self._alpha <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # 前 45% 淡入、后 55% 淡出
        alpha = 1.0 - abs(self._alpha - 0.28) / 0.72
        alpha = max(0.0, min(1.0, alpha))
        glow = QColor(self.theme.accent)
        glow.setAlpha(int(26 * alpha))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawRoundedRect(QRectF(self.rect()), 18, 18)

        font = painter.font()
        font.setPixelSize(15)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        text_color = QColor(self.theme.accent_text_hex)
        text_color.setAlpha(int(255 * alpha))
        painter.setPen(text_color)
        painter.drawText(
            QRectF(self.rect()).adjusted(0, -10, 0, -10),
            Qt.AlignmentFlag.AlignCenter,
            self.text,
        )


class TaskLabel(QLabel):
    """单行任务文本：省略号截断 + 完成态删除线 + 双击进入编辑。"""

    doubleClicked = Signal()

    def __init__(self, theme: Theme, text: str = "") -> None:
        super().__init__()
        self.theme = theme
        self.full_text = text
        self.done = False
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(20)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        font = self.font()
        font.setPixelSize(12)
        self.setFont(font)
        self._apply_style()
        self._refresh()

    def set_full_text(self, text: str) -> None:
        self.full_text = text
        self.setToolTip(text if len(text) > 28 else "")
        self._refresh()

    def set_done(self, done: bool) -> None:
        self.done = done
        self._apply_style()
        self._refresh()

    def _apply_style(self) -> None:
        font = self.font()
        font.setStrikeOut(self.done)
        self.setFont(font)
        color = self.theme.faint if self.done else self.theme.text
        self.setStyleSheet(
            f"color: rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha()}); background: transparent;"
        )

    def _refresh(self) -> None:
        width = max(20, self.width() - 4)
        self.setText(elide(self.full_text, self.font(), width))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._refresh()

    def mouseDoubleClickEvent(self, event) -> None:
        self.doubleClicked.emit()
        super().mouseDoubleClickEvent(event)


class InlineEdit(QLineEdit):
    def __init__(self, theme: Theme) -> None:
        super().__init__()
        self.theme = theme
        self.setMaxLength(200)
        self.setStyleSheet(
            "QLineEdit { background: transparent; border: none; color: %s; font-size: 12px; }"
            % theme.palette.text.name()
        )


class TaskRow(QWidget):
    """一行待办：优先级色条 + 勾选框 + 文本 + 提醒小标签 + 悬停删除。"""

    toggled = Signal(str, bool)
    deleted = Signal(str)
    edited = Signal(str, str)
    menuRequested = Signal(str, QPoint)

    def __init__(self, theme: Theme, task: dict, show_date: str = "") -> None:
        super().__init__()
        self.theme = theme
        self.task = dict(task)
        self.task_id = task.get("id", "")
        self.show_date = show_date
        self._hover = False
        self._editing = False
        self.setFixedHeight(34)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(
            lambda pos: self.menuRequested.emit(self.task_id, self.mapToGlobal(pos))
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 6, 0)
        layout.setSpacing(8)

        self.check = CheckButton(theme, 19)
        self.check.set_checked(bool(task.get("done")), animate=False)
        self.check.clicked.connect(self._on_check)
        layout.addWidget(self.check)

        self.label = TaskLabel(theme, task.get("text", ""))
        self.label.set_done(bool(task.get("done")))
        self.label.doubleClicked.connect(self.start_edit)
        layout.addWidget(self.label, 1)

        self.edit = InlineEdit(theme)
        self.edit.setVisible(False)
        self.edit.editingFinished.connect(self._commit_edit)
        layout.addWidget(self.edit, 1)

        self.chip = QLabel()
        self.chip.setStyleSheet(
            "color: %s; background: transparent; font-size: 10px;" % theme.accent_text_hex
        )
        layout.addWidget(self.chip)
        self._refresh_meta()

        self.delete_btn = IconButton(theme, "close", 18, "删除")
        self.delete_btn.setVisible(False)
        self.delete_btn.clicked.connect(lambda: self.deleted.emit(self.task_id))
        layout.addWidget(self.delete_btn)

    # ---------- 状态 ----------

    def set_task(self, task: dict) -> None:
        if self._editing:
            return
        self.task = dict(task)
        self.task_id = task.get("id", self.task_id)
        self.label.set_full_text(task.get("text", ""))
        done = bool(task.get("done"))
        self.label.set_done(done)
        self.check.set_checked(done)
        self._refresh_meta()
        self.update()

    def set_done(self, done: bool) -> None:
        self.task["done"] = done
        self.label.set_done(done)
        self.check.set_checked(done)
        self.update()

    def _refresh_meta(self) -> None:
        parts = []
        if self.show_date:
            parts.append(self.show_date)
        if self.task.get("remindAt"):
            parts.append("⏰" + self.task["remindAt"])
        if self.task.get("seriesId"):
            parts.append("↻")
        self.chip.setText(" ".join(parts))
        self.chip.setVisible(bool(parts))

    def _on_check(self) -> None:
        done = not bool(self.task.get("done"))
        self.set_done(done)
        self.toggled.emit(self.task_id, done)

    # ---------- 行内编辑 ----------

    def start_edit(self) -> None:
        if self._editing:
            return
        self._editing = True
        self.label.setVisible(False)
        self.edit.setText(self.task.get("text", ""))
        self.edit.setVisible(True)
        self.edit.setFocus(Qt.FocusReason.MouseFocusReason)
        self.edit.selectAll()

    def _commit_edit(self) -> None:
        if not self._editing:
            return
        self._editing = False
        text = " ".join(self.edit.text().split()).strip()
        self.edit.setVisible(False)
        self.label.setVisible(True)
        if not text:
            return
        self.label.set_full_text(text)
        self.task["text"] = text
        self.edited.emit(self.task_id, text)

    def cancel_edit(self) -> None:
        if not self._editing:
            return
        self._editing = False
        self.edit.setVisible(False)
        self.label.setVisible(True)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape and self._editing:
            self.cancel_edit()
            return
        super().keyPressEvent(event)

    # ---------- 交互 / 绘制 ----------

    def enterEvent(self, event) -> None:
        self._hover = True
        self.delete_btn.setVisible(True)
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        if not self._editing:
            self.delete_btn.setVisible(False)
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        if self._hover:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self.theme.hover)
            painter.drawRoundedRect(rect, 9, 9)
        priority = self.task.get("priority", 0)
        if priority:
            color = QColor(PRIORITY_COLORS.get(priority, self.theme.accent))
            color.setAlpha(210 if not self.task.get("done") else 90)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(QRectF(4, rect.top() + 9, 2.4, rect.height() - 18), 1.2, 1.2)
