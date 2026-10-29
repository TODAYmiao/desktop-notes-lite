"""主窗口、日历、待办列表、托盘和开机自启。"""

import ctypes
import sys
import time
import uuid
from datetime import date, timedelta
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
    QIcon,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .store import Store
from .theme import (
    DEFAULT_ACCENT,
    PRESET_ACCENTS,
    Theme,
    normalize_hex,
    rgba,
    with_alpha,
)
from .widgets import (
    AddButton,
    BrandDot,
    DayButton,
    EmptyState,
    IconButton,
    MonthCard,
    ProgressBar,
    SwatchButton,
    Switch,
    TodoRow,
    divider,
    repolish,
)

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


ASSETS = _base_dir() / "assets"
WINDOW_WIDTH = 500
WINDOW_HEIGHT = 540
WINDOW_MARGIN = 8
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_VALUE = "DesktopNotesLite"
WEEK_LABELS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def _autostart_target() -> str:
    if getattr(sys, "frozen", False):
        return f'"{Path(sys.executable)}"'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = pythonw if pythonw.exists() else Path(sys.executable)
    main_py = Path(__file__).resolve().parent.parent / "main.py"
    return f'"{exe}" "{main_py}"'


def is_autostart_enabled() -> bool:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, AUTOSTART_VALUE)
            return True
    except (ImportError, FileNotFoundError, OSError):
        return False


def set_autostart_enabled(enabled: bool) -> bool:
    try:
        import winreg
    except ImportError:
        return False

    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, AUTOSTART_VALUE, 0, winreg.REG_SZ, _autostart_target())
        else:
            try:
                winreg.DeleteValue(key, AUTOSTART_VALUE)
            except FileNotFoundError:
                pass
    return is_autostart_enabled()


def apply_topmost(widget: QWidget, on: bool) -> None:
    if sys.platform != "win32":
        return
    try:
        hwnd = int(widget.winId())
        HWND_TOPMOST = -1
        HWND_NOTOPMOST = -2
        SWP_NOSIZE = 0x0001
        SWP_NOMOVE = 0x0002
        SWP_NOACTIVATE = 0x0010
        ctypes.windll.user32.SetWindowPos(
            hwnd,
            HWND_TOPMOST if on else HWND_NOTOPMOST,
            0,
            0,
            0,
            0,
            SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE,
        )
    except Exception:
        pass


class Shell(QWidget):
    def __init__(self, theme: Theme, opacity: int = 80):
        super().__init__()
        self.theme = theme
        self.opacity = opacity

    def set_opacity(self, value: int) -> None:
        self.opacity = value
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, 16, 16)

        base = QColor(20, 20, 25)
        base.setAlphaF(max(0.0, min(1.0, self.opacity / 100)))
        painter.fillPath(path, base)

        painter.save()
        painter.setClipPath(path)
        w, h = self.width(), self.height()

        top_glow = QRadialGradient(QPointF(w * 0.12, 0), max(w, h) * 1.1)
        top_glow.setColorAt(0, with_alpha(self.theme.accent, 33))
        top_glow.setColorAt(0.55, with_alpha(self.theme.accent, 0))
        painter.fillRect(self.rect(), top_glow)

        bottom_glow = QRadialGradient(QPointF(w, h), max(w, h) * 0.9)
        bottom_glow.setColorAt(0, with_alpha(self.theme.accent, 18))
        bottom_glow.setColorAt(0.6, with_alpha(self.theme.accent, 0))
        painter.fillRect(self.rect(), bottom_glow)
        painter.restore()

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(255, 255, 255, 31), 1))
        painter.drawPath(path)


class TitleBar(QWidget):
    def __init__(self, theme: Theme):
        super().__init__()
        self.theme = theme
        self.setFixedHeight(44)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 9, 0)
        layout.setSpacing(8)

        brand = QWidget()
        brand.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        brand_layout = QHBoxLayout(brand)
        brand_layout.setContentsMargins(0, 0, 0, 0)
        brand_layout.setSpacing(8)
        brand_layout.addWidget(BrandDot(theme))

        title = QLabel("便签")
        title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        font = QFont("Microsoft YaHei UI")
        font.setPixelSize(13)
        font.setWeight(QFont.Weight.DemiBold)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.5)
        title.setFont(font)
        title.setStyleSheet("color: rgba(244,239,231,230); background: transparent;")
        brand_layout.addWidget(title)
        layout.addWidget(brand)
        layout.addStretch(1)

        self.opacity_btn = IconButton(theme, "opacity", 28, "颜色与不透明度")
        self.pin_btn = IconButton(theme, "pin", 28, "置顶")
        self.close_btn = IconButton(theme, "close", 28, "隐藏到托盘", danger=True)
        layout.addWidget(self.opacity_btn)
        layout.addWidget(self.pin_btn)
        layout.addWidget(self.close_btn)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self.window().windowHandle()
            if handle is not None:
                handle.startSystemMove()
                event.accept()
                return
        super().mousePressEvent(event)


class Popover(QFrame):
    colorPicked = Signal(str)
    opacityChanged = Signal(int)
    autostartToggled = Signal(bool)

    def __init__(self, parent: QWidget, theme: Theme):
        super().__init__(parent)
        self.theme = theme
        self.setObjectName("popover")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(200)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(13, 12, 13, 14)
        layout.setSpacing(0)

        color_row = QHBoxLayout()
        color_row.setContentsMargins(0, 0, 0, 0)
        color_title = QLabel("便签颜色")
        color_title.setObjectName("popTitle")
        self.color_value = QLabel("#FFB26B")
        self.color_value.setObjectName("popValue")
        color_row.addWidget(color_title)
        color_row.addStretch(1)
        color_row.addWidget(self.color_value)
        layout.addLayout(color_row)
        layout.addSpacing(9)

        swatch_row = QHBoxLayout()
        swatch_row.setContentsMargins(0, 0, 0, 0)
        swatch_row.setSpacing(4)
        self.presets = []
        for hex_value in PRESET_ACCENTS:
            button = SwatchButton(theme, hex_value)
            button.clicked.connect(
                lambda checked=False, value=hex_value: self.colorPicked.emit(value)
            )
            swatch_row.addWidget(button)
            self.presets.append(button)

        self.custom = SwatchButton(theme, theme.accent_hex, custom=True)
        self.custom.setToolTip("自定义颜色")
        self.custom.clicked.connect(self._pick_custom)
        swatch_row.addWidget(self.custom)
        layout.addLayout(swatch_row)

        layout.addSpacing(13)
        layout.addWidget(divider())
        layout.addSpacing(12)

        opacity_row = QHBoxLayout()
        opacity_row.setContentsMargins(0, 0, 0, 0)
        opacity_title = QLabel("背景不透明度")
        opacity_title.setObjectName("popTitle")
        self.opacity_value = QLabel("80%")
        self.opacity_value.setObjectName("popValue")
        opacity_row.addWidget(opacity_title)
        opacity_row.addStretch(1)
        opacity_row.addWidget(self.opacity_value)
        layout.addLayout(opacity_row)
        layout.addSpacing(6)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(35, 95)
        self.slider.setValue(80)
        self.slider.valueChanged.connect(self._on_slider)
        layout.addWidget(self.slider)

        layout.addSpacing(13)
        layout.addWidget(divider())
        layout.addSpacing(12)

        auto_row = QHBoxLayout()
        auto_row.setContentsMargins(0, 0, 0, 0)
        auto_label = QLabel("开机自启")
        auto_label.setObjectName("settingLabel")
        self.auto_switch = Switch(theme)
        self.auto_switch.clicked.connect(
            lambda: self.autostartToggled.emit(self.auto_switch.isChecked())
        )
        auto_row.addWidget(auto_label)
        auto_row.addStretch(1)
        auto_row.addWidget(self.auto_switch)
        layout.addLayout(auto_row)

        self.adjustSize()

    def _on_slider(self, value: int) -> None:
        self.opacity_value.setText(f"{value}%")
        self.opacityChanged.emit(value)

    def _pick_custom(self) -> None:
        color = QColorDialog.getColor(QColor(self.theme.accent_hex), self, "选择便签颜色")
        if color.isValid():
            self.colorPicked.emit(color.name())

    def sync(self, accent: str, opacity: int, autostart: bool) -> None:
        accent = normalize_hex(accent)
        self.color_value.setText(accent.upper())
        for button in self.presets:
            button.set_selected(button.color_hex == accent)
        self.custom.set_color(accent)
        self.custom.set_selected(accent not in PRESET_ACCENTS)
        self.sync_opacity(opacity)
        self.sync_autostart(autostart)

    def sync_accent(self, accent: str) -> None:
        accent = normalize_hex(accent)
        self.color_value.setText(accent.upper())
        for button in self.presets:
            button.set_selected(button.color_hex == accent)
        self.custom.set_color(accent)
        self.custom.set_selected(accent not in PRESET_ACCENTS)

    def sync_opacity(self, opacity: int) -> None:
        self.slider.blockSignals(True)
        self.slider.setValue(int(opacity))
        self.slider.blockSignals(False)
        self.opacity_value.setText(f"{int(opacity)}%")

    def sync_autostart(self, enabled: bool) -> None:
        self.auto_switch.blockSignals(True)
        self.auto_switch.setChecked(bool(enabled))
        self.auto_switch.blockSignals(False)


class NotesWindow(QWidget):
    def __init__(self, store: Store):
        super().__init__()
        self.store = store
        self.theme = Theme(store.settings.get("accent", DEFAULT_ACCENT))
        self.selected_key = date.today().isoformat()
        self.view_year = date.today().year
        self.view_month = date.today().month
        self._last_list_key = None
        self._quitting = False
        self._hide_hint_shown = False
        self._position_ready = False
        self._initial_topmost_done = False

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self.store.save)

        self._position_timer = QTimer(self)
        self._position_timer.setSingleShot(True)
        self._position_timer.timeout.connect(self._save_position)

        self.setWindowTitle("桌面便签 Lite")
        self.setWindowIcon(QIcon(str(ASSETS / "icon.png")))
        self.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet(self.theme.stylesheet())

        self._build_ui()
        self._build_tray()
        self._restore_position()
        self._apply_initial_state()
        self.popover.hide()

        self._position_ready = True
        QApplication.instance().installEventFilter(self)

    # ---------- 构建界面 ----------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(WINDOW_MARGIN, WINDOW_MARGIN, WINDOW_MARGIN, WINDOW_MARGIN)
        outer.setSpacing(0)

        self.shell = Shell(self.theme, int(self.store.settings.get("opacity", 80)))
        outer.addWidget(self.shell)

        shell_layout = QVBoxLayout(self.shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)

        self.titlebar = TitleBar(self.theme)
        shell_layout.addWidget(self.titlebar)

        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(14, 0, 14, 14)
        content_layout.setSpacing(12)
        shell_layout.addWidget(content, 1)

        content_layout.addWidget(self._build_calendar_column())
        content_layout.addWidget(self._build_todo_panel(), 1)

        self.popover = Popover(self.shell, self.theme)
        self.popover.colorPicked.connect(self.set_accent)
        self.popover.opacityChanged.connect(self.set_opacity)
        self.popover.autostartToggled.connect(self.set_autostart)

        self.titlebar.opacity_btn.clicked.connect(self.toggle_popover)
        self.titlebar.pin_btn.clicked.connect(
            lambda: self.set_pin(not self.store.settings.get("alwaysOnTop", True))
        )
        self.titlebar.close_btn.clicked.connect(self.hide_to_tray)

        self.add_input.installEventFilter(self)

    def _build_calendar_column(self) -> QWidget:
        column = QWidget()
        column.setFixedWidth(240)
        layout = QVBoxLayout(column)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        head = QWidget()
        head.setFixedHeight(30)
        head_layout = QHBoxLayout(head)
        head_layout.setContentsMargins(0, 0, 0, 0)
        head_layout.setSpacing(4)

        self.prev_btn = IconButton(self.theme, "chevron_left", 24, "上个月")
        self.next_btn = IconButton(self.theme, "chevron_right", 24, "下个月")
        self.month_title = QPushButton("2026年10月")
        self.month_title.setObjectName("monthTitle")
        self.month_title.setCursor(Qt.CursorShape.PointingHandCursor)
        self.month_title.setFlat(True)
        self.month_title.setFixedHeight(26)
        self.month_title.setToolTip("回到所选日期")

        head_layout.addWidget(self.prev_btn)
        head_layout.addWidget(self.month_title, 1)
        head_layout.addWidget(self.next_btn)
        layout.addWidget(head)
        layout.addSpacing(4)

        weekday_widget = QWidget()
        weekday_widget.setFixedHeight(18)
        weekday_layout = QGridLayout(weekday_widget)
        weekday_layout.setContentsMargins(0, 0, 0, 0)
        weekday_layout.setSpacing(3)
        for index, text in enumerate(["一", "二", "三", "四", "五", "六", "日"]):
            label = QLabel(text)
            label.setObjectName("weekday")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            weekday_layout.addWidget(label, 0, index)
            weekday_layout.setColumnStretch(index, 1)
        layout.addWidget(weekday_widget)
        layout.addSpacing(3)

        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(3)
        self.day_buttons = []
        for index in range(42):
            button = DayButton(self.theme)
            button.clicked.connect(
                lambda checked=False, btn=button: self._day_clicked(btn)
            )
            grid.addWidget(button, index // 7, index % 7)
            grid.setColumnStretch(index % 7, 1)
            self.day_buttons.append(button)
        grid_widget.setFixedHeight(6 * 34 + 5 * 3)
        layout.addWidget(grid_widget)

        foot = QWidget()
        foot.setFixedHeight(30)
        foot_layout = QHBoxLayout(foot)
        foot_layout.setContentsMargins(0, 0, 0, 0)
        foot_layout.addStretch(1)
        self.today_btn = QPushButton("回到今天")
        self.today_btn.setObjectName("todayBtn")
        self.today_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.today_btn.setFlat(True)
        foot_layout.addWidget(self.today_btn)
        layout.addWidget(foot)

        layout.addStretch(1)
        self.month_card = MonthCard(self.theme)
        layout.addWidget(self.month_card)

        self.prev_btn.clicked.connect(lambda: self._shift_month(-1))
        self.next_btn.clicked.connect(lambda: self._shift_month(1))
        self.month_title.clicked.connect(self._month_title_clicked)
        self.today_btn.clicked.connect(self._today_clicked)

        return column

    def _build_todo_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("panel")
        panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 10)
        layout.setSpacing(0)

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(8)
        dates = QVBoxLayout()
        dates.setContentsMargins(0, 0, 0, 0)
        dates.setSpacing(3)
        self.sel_date = QLabel("")
        self.sel_date.setObjectName("selDate")
        self.sel_week = QLabel("")
        self.sel_week.setObjectName("selWeek")
        dates.addWidget(self.sel_date)
        dates.addWidget(self.sel_week)
        head.addLayout(dates)
        head.addStretch(1)

        self.count_label = QLabel("0/0")
        self.count_label.setObjectName("countLabel")
        self.count_label.setTextFormat(Qt.TextFormat.RichText)
        self.count_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop
        )
        head.addWidget(self.count_label, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(head)

        layout.addSpacing(10)
        self.panel_bar = ProgressBar(self.theme, 2)
        layout.addWidget(self.panel_bar)
        layout.addSpacing(2)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("scrollArea")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.viewport().setAutoFillBackground(False)

        self.list_widget = QWidget()
        self.list_widget.setObjectName("listContainer")
        self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.setContentsMargins(0, 8, 0, 6)
        self.list_layout.setSpacing(2)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.list_widget)
        layout.addWidget(self.scroll, 1)

        self.add_bar = QFrame()
        self.add_bar.setObjectName("addBar")
        self.add_bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.add_bar.setFixedHeight(40)
        bar_layout = QHBoxLayout(self.add_bar)
        bar_layout.setContentsMargins(10, 3, 3, 3)
        bar_layout.setSpacing(6)

        self.add_input = QLineEdit()
        self.add_input.setObjectName("addInput")
        self.add_input.setPlaceholderText("添加待办，回车保存")
        self.add_input.setMaxLength(200)
        palette = self.add_input.palette()
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(244, 239, 231, 77))
        self.add_input.setPalette(palette)
        self.add_input.returnPressed.connect(self.add_todo)

        self.add_btn = AddButton(self.theme)
        self.add_btn.clicked.connect(self.add_todo)

        bar_layout.addWidget(self.add_input, 1)
        bar_layout.addWidget(self.add_btn)
        layout.addWidget(self.add_bar)

        return panel

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(QIcon(str(ASSETS / "tray.png")), self)
        self.tray.setToolTip("桌面便签 Lite")

        menu = QMenu()
        self.act_show = menu.addAction("隐藏便签")
        self.act_show.triggered.connect(self.toggle_visible)
        menu.addSeparator()
        self.act_pin = menu.addAction("始终置顶")
        self.act_pin.setCheckable(True)
        self.act_pin.triggered.connect(lambda checked: self.set_pin(checked))
        self.act_auto = menu.addAction("开机自启")
        self.act_auto.setCheckable(True)
        self.act_auto.triggered.connect(lambda checked: self.set_autostart(checked))
        menu.addSeparator()
        quit_action = menu.addAction("退出")
        quit_action.triggered.connect(self.quit_app)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

        self._tray_timer = QTimer(self)
        self._tray_timer.setSingleShot(True)
        self._tray_timer.setInterval(220)
        self._tray_timer.timeout.connect(self.toggle_visible)

        self._refresh_tray()

    # ---------- 初始状态与位置 ----------

    def _apply_initial_state(self) -> None:
        settings = self.store.settings
        self.shell.set_opacity(int(settings.get("opacity", 80)))
        self.titlebar.pin_btn.setActive(bool(settings.get("alwaysOnTop", True)))
        self.titlebar.pin_btn.setToolTip(
            "取消置顶" if settings.get("alwaysOnTop", True) else "置顶"
        )
        self.popover.sync(
            settings.get("accent", DEFAULT_ACCENT),
            int(settings.get("opacity", 80)),
            is_autostart_enabled(),
        )
        self.render_all()

    def _restore_position(self) -> None:
        saved = self.store.load_window_pos()
        if saved:
            x, y = saved
            for screen in QGuiApplication.screens():
                area = screen.availableGeometry()
                if area.contains(QPoint(x + 60, y + 40)) and area.contains(
                    QPoint(x + self.width() - 60, y + self.height() - 40)
                ):
                    self.move(x, y)
                    return
        area = QGuiApplication.primaryScreen().availableGeometry()
        self.move(area.right() - self.width() - 24, area.top() + 24)

    def _save_position(self) -> None:
        if self._position_ready:
            self.store.save_window_pos(self.x(), self.y())

    # ---------- 渲染 ----------

    def render_all(self) -> None:
        self.render_calendar()
        self.render_todos()
        self.render_month_stat()

    def render_calendar(self) -> None:
        self.month_title.setText(f"{self.view_year}年{self.view_month}月")
        first = date(self.view_year, self.view_month, 1)
        start = first - timedelta(days=first.weekday())
        today_key = date.today().isoformat()

        for index, button in enumerate(self.day_buttons):
            day = start + timedelta(days=index)
            key = day.isoformat()
            items = self.store.items_for(key)
            dot = None
            if items:
                dot = "pending" if any(not item.get("done") for item in items) else "done"
            button.configure(
                key,
                day.day,
                day.month == self.view_month,
                key == today_key,
                key == self.selected_key,
                dot,
            )

    def render_todos(self) -> None:
        day = date.fromisoformat(self.selected_key)
        self.sel_date.setText(f"{day.month}月{day.day}日")
        week = WEEK_LABELS[day.weekday()]
        if self.selected_key == date.today().isoformat():
            week += " · 今天"
        self.sel_week.setText(week)

        items = self.store.items_for(self.selected_key)
        done = sum(1 for item in items if item.get("done"))
        self._update_count(items, done)
        self.panel_bar.set_value(done / len(items) if items else 0.0)

        scrollbar = self.scroll.verticalScrollBar()
        previous = scrollbar.value()
        same_day = self._last_list_key == self.selected_key
        self._last_list_key = self.selected_key

        while self.list_layout.count():
            entry = self.list_layout.takeAt(0)
            widget = entry.widget()
            if widget is not None:
                widget.deleteLater()

        if not items:
            self.list_layout.addWidget(EmptyState(), 1)
        else:
            for item in items:
                row = TodoRow(item, self.theme)
                row.toggled.connect(self.toggle_todo)
                row.deleted.connect(self.delete_todo)
                row.edited.connect(self.edit_todo)
                self.list_layout.addWidget(row)
            self.list_layout.addStretch(1)

        target = previous if same_day else 0
        QTimer.singleShot(0, lambda: scrollbar.setValue(target))

    def render_month_stat(self) -> None:
        prefix = f"{self.view_year}-{self.view_month:02d}-"
        total = 0
        done = 0
        for key, items in self.store.todos.items():
            if not key.startswith(prefix):
                continue
            total += len(items)
            done += sum(1 for item in items if item.get("done"))
        self.month_card.update_stats(total, done)

    def _update_count(self, items=None, done=None) -> None:
        items = self.store.items_for(self.selected_key) if items is None else items
        done = sum(1 for item in items if item.get("done")) if done is None else done
        self.count_label.setText(
            f'<span style="color:{self.theme.accent_hex}; font-weight:600;">{done}</span>/{len(items)}'
        )

    # ---------- 日期导航 ----------

    def _day_clicked(self, button: DayButton) -> None:
        if not button.date_key:
            return
        day = date.fromisoformat(button.date_key)
        if day.year != self.view_year or day.month != self.view_month:
            self.view_year, self.view_month = day.year, day.month
        self.selected_key = button.date_key
        self.render_all()

    def _shift_month(self, delta: int) -> None:
        month = self.view_month + delta
        year = self.view_year
        if month < 1:
            month = 12
            year -= 1
        elif month > 12:
            month = 1
            year += 1
        self.view_year, self.view_month = year, month
        self.render_calendar()
        self.render_month_stat()

    def _month_title_clicked(self) -> None:
        day = date.fromisoformat(self.selected_key)
        self.view_year, self.view_month = day.year, day.month
        self.render_calendar()
        self.render_month_stat()

    def _today_clicked(self) -> None:
        today = date.today()
        self.selected_key = today.isoformat()
        self.view_year, self.view_month = today.year, today.month
        self.render_all()
        self.add_input.setFocus()

    # ---------- 待办操作 ----------

    def add_todo(self) -> None:
        text = self.add_input.text().strip()
        if not text:
            return
        self.store.todos.setdefault(self.selected_key, []).append(
            {
                "id": str(uuid.uuid4()),
                "text": text[:200],
                "done": False,
                "createdAt": int(time.time() * 1000),
            }
        )
        self.add_input.clear()
        self.store.save()
        self.render_calendar()
        self.render_month_stat()
        self.render_todos()
        scrollbar = self.scroll.verticalScrollBar()
        QTimer.singleShot(0, lambda: scrollbar.setValue(scrollbar.maximum()))
        self.add_input.setFocus()

    def toggle_todo(self, item_id: str) -> None:
        for item in self.store.items_for(self.selected_key):
            if item.get("id") == item_id:
                item["done"] = not item.get("done")
                break
        self.store.save()
        self.render_calendar()
        self.render_month_stat()
        self.render_todos()

    def delete_todo(self, item_id: str) -> None:
        items = [
            item for item in self.store.items_for(self.selected_key)
            if item.get("id") != item_id
        ]
        if items:
            self.store.todos[self.selected_key] = items
        else:
            self.store.todos.pop(self.selected_key, None)
        self.store.save()
        self.render_calendar()
        self.render_month_stat()
        self.render_todos()

    def edit_todo(self, item_id: str, text: str) -> None:
        text = text.strip()
        if not text:
            return
        for item in self.store.items_for(self.selected_key):
            if item.get("id") == item_id:
                item["text"] = text[:500]
                break
        self.store.save()
        self.render_todos()

    # ---------- 设置 ----------

    def set_opacity(self, value: int) -> None:
        value = max(35, min(95, int(value)))
        self.store.settings["opacity"] = value
        self.shell.set_opacity(value)
        self.popover.sync_opacity(value)
        self._save_timer.start(250)

    def set_accent(self, value: str) -> None:
        accent = normalize_hex(value)
        self.theme.set_accent(accent)
        self.store.settings["accent"] = accent
        self.setStyleSheet(self.theme.stylesheet())
        self.popover.sync_accent(accent)
        for widget in self.findChildren(QWidget):
            widget.update()
        self._update_count()
        self.store.save()

    def set_pin(self, on: bool, persist: bool = True) -> None:
        on = bool(on)
        self.store.settings["alwaysOnTop"] = on
        self.titlebar.pin_btn.setActive(on)
        self.titlebar.pin_btn.setToolTip("取消置顶" if on else "置顶")
        apply_topmost(self, on)
        self._refresh_tray()
        if persist:
            self.store.save()

    def set_autostart(self, enabled: bool) -> None:
        try:
            actual = set_autostart_enabled(bool(enabled))
        except OSError:
            actual = is_autostart_enabled()
        self.popover.sync_autostart(actual)
        self._refresh_tray()

    # ---------- 浮层 ----------

    def toggle_popover(self) -> None:
        if self.popover.isVisible():
            self.popover.hide()
            return
        self.popover.sync(
            self.store.settings.get("accent", DEFAULT_ACCENT),
            int(self.store.settings.get("opacity", 80)),
            is_autostart_enabled(),
        )
        self._position_popover()
        self.popover.show()
        self.popover.raise_()

    def _position_popover(self) -> None:
        self.popover.adjustSize()
        self.popover.move(
            self.shell.width() - 10 - self.popover.width(),
            42,
        )

    def eventFilter(self, watched, event) -> bool:
        if watched is self.add_input:
            if event.type() == QEvent.Type.FocusIn:
                self.add_bar.setProperty("focused", "true")
                repolish(self.add_bar)
            elif event.type() == QEvent.Type.FocusOut:
                self.add_bar.setProperty("focused", "false")
                repolish(self.add_bar)

        if event.type() == QEvent.Type.MouseButtonPress and self.popover.isVisible():
            target = watched if isinstance(watched, QWidget) else None
            if target is not None:
                inside_popover = target is self.popover or self.popover.isAncestorOf(target)
                inside_button = target is self.titlebar.opacity_btn
                if not inside_popover and not inside_button:
                    self.popover.hide()

        return super().eventFilter(watched, event)

    # ---------- 托盘与显隐 ----------

    def _tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._tray_timer.start()
        elif reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._tray_timer.stop()
            self.show_from_tray()

    def _refresh_tray(self) -> None:
        if not hasattr(self, "tray"):
            return
        visible = self.isVisible()
        self.act_show.setText("隐藏便签" if visible else "显示便签")
        self.act_pin.setChecked(bool(self.store.settings.get("alwaysOnTop", True)))
        self.act_auto.setChecked(is_autostart_enabled())

    def show_from_tray(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
        self._refresh_tray()

    def hide_to_tray(self) -> None:
        self.hide()
        if not self._hide_hint_shown and self.tray.supportsMessages():
            self._hide_hint_shown = True
            self.tray.showMessage(
                "桌面便签 Lite",
                "便签已收进托盘，点击托盘图标可重新打开。",
                QSystemTrayIcon.MessageIcon.Information,
                3000,
            )

    def toggle_visible(self) -> None:
        if self.isVisible():
            self.hide_to_tray()
        else:
            self.show_from_tray()

    def quit_app(self) -> None:
        self._quitting = True
        self._save_timer.stop()
        self._save_position()
        self.store.save()
        self.tray.hide()
        QApplication.quit()

    # ---------- 事件 ----------

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._initial_topmost_done:
            self._initial_topmost_done = True
            apply_topmost(self, bool(self.store.settings.get("alwaysOnTop", True)))
        self._position_popover()
        self._refresh_tray()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self.popover.hide()
        self._refresh_tray()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "popover"):
            self._position_popover()

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        if self._position_ready:
            self._position_timer.start(400)

    def closeEvent(self, event) -> None:
        if self._quitting:
            event.accept()
            return
        event.ignore()
        self.hide_to_tray()
