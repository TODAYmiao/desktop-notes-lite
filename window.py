"""主窗口：单栏布局、顺延、撤销、搜索、重复任务、提醒、热键、自动淡化。

布局相对于 0.1 版是一次重构：原来「左日历 240px + 右列表 240px」在 500px 宽度下
两边都不够用，月历常年占着半屏却只用其中一天的格子。现在竖着排：
标题栏 → 今日概览（大日期 + 进度环）→ 日历（周条 / 月网格可切）→ 顺延条 →
任务列表 → 快速添加 → 底部统计与热力图。
"""

from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QSlider,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .hotkey import GlobalHotkey
from .quickadd import MAX_TEXT, WEEKDAY_FULL, format_day, parse_quick_add
from .store import Store
from .theme import PRESET_ACCENTS, Theme, with_alpha
from .widgets import (
    AccentFab,
    BrandDot,
    Celebration,
    DayCell,
    Heatmap,
    IconButton,
    ProgressRing,
    SwatchButton,
    Switch,
    TaskRow,
    Toast,
    repolish,
)

MIN_WIDTH = 360
MIN_HEIGHT = 520
DEFAULT_WIDTH = 420
DEFAULT_HEIGHT = 664
RESIZE_MARGIN = 7
AUTOSAVE_MS = 350
MIDNIGHT_CHECK_MS = 30_000
REMINDER_CHECK_MS = 30_000
MAX_UNDO = 30
WEEKDAY_SHORT = "一二三四五六日"


class HLine(QWidget):
    def __init__(self, theme: Theme, alpha: int = 26) -> None:
        super().__init__()
        self.theme = theme
        self.alpha = alpha
        self.setFixedHeight(1)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), with_alpha(self.theme.text, self.alpha))


class TitleBar(QWidget):
    """标题栏同时承担「拖动窗口」——原来只有中间的空白区能拖。"""

    def __init__(self, window: "NotesWindow") -> None:
        super().__init__()
        self.window_ref = window
        self.setFixedHeight(26)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self.window_ref.windowHandle()
            if handle is not None and handle.startSystemMove():
                return
        super().mousePressEvent(event)


class SettingsContent(QWidget):
    """设置浮层的实际内容；每次打开重建，保证主题 / 强调色状态是最新的。"""

    def __init__(self, theme: Theme, window: "NotesWindow") -> None:
        super().__init__()
        self.theme = theme
        self.window_ref = window
        self.swatches: list[SwatchButton] = []
        self._build()

    def _label(self, text: str, object_name: str = "popTitle") -> QLabel:
        label = QLabel(text)
        label.setObjectName(object_name)
        return label

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)
        window = self.window_ref
        settings = window.store.settings

        layout.addWidget(self._label("设置"))

        layout.addWidget(self._label("主题"))
        theme_row = QHBoxLayout()
        theme_row.setSpacing(6)
        for title, mode in (("深色", "dark"), ("浅色", "light")):
            button = QPushButton(title)
            button.setObjectName("modeBtn")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setProperty("active", "true" if settings.get("theme") == mode else "false")
            button.clicked.connect(lambda _=False, m=mode: window.set_theme_mode(m))
            theme_row.addWidget(button)
        theme_row.addStretch()
        layout.addLayout(theme_row)

        layout.addWidget(self._label("强调色"))
        swatch_row = QHBoxLayout()
        swatch_row.setSpacing(5)
        accent = settings.get("accent", PRESET_ACCENTS[0])
        for color in PRESET_ACCENTS:
            swatch = SwatchButton(self.theme, color, 19)
            swatch.set_selected(accent == color)
            swatch.clicked.connect(lambda _=False, c=color: window.set_accent(c))
            swatch_row.addWidget(swatch)
            self.swatches.append(swatch)
        custom = SwatchButton(self.theme, accent if accent not in PRESET_ACCENTS else "#8d8d99", 19)
        custom.setToolTip("自定义颜色")
        custom.clicked.connect(window.pick_accent)
        swatch_row.addWidget(custom)
        swatch_row.addStretch()
        layout.addLayout(swatch_row)

        opacity_head = QHBoxLayout()
        opacity_head.addWidget(self._label("透明度"))
        opacity_head.addStretch()
        self.opacity_value = QLabel(f"{int(settings.get('opacity', 80))}%")
        self.opacity_value.setObjectName("popValue")
        opacity_head.addWidget(self.opacity_value)
        layout.addLayout(opacity_head)
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(35, 100)
        self.opacity_slider.setValue(int(settings.get("opacity", 80)))
        self.opacity_slider.valueChanged.connect(window.set_opacity)
        layout.addWidget(self.opacity_slider)

        layout.addWidget(HLine(self.theme, 22))

        for key, title, hint in (
            ("autoFade", "不悬停时自动淡化", "鼠标离开后变淡，移回来恢复"),
            ("snap", "靠近屏幕边缘自动吸附", "拖到边缘 16px 内自动贴边"),
            ("autostart", "开机自动启动", "写入当前用户的启动项"),
        ):
            row = QHBoxLayout()
            row.setSpacing(8)
            text_box = QVBoxLayout()
            text_box.setSpacing(0)
            text_box.addWidget(self._label(title, object_name="settingLabel"))
            hint_label = QLabel(hint)
            hint_label.setObjectName("settingHint")
            text_box.addWidget(hint_label)
            row.addLayout(text_box, 1)
            switch = Switch(self.theme)
            switch.set_checked(bool(settings.get(key)))
            switch.clicked.connect(
                lambda _=False, k=key, s=switch: window.toggle_setting(k, s.isChecked())
            )
            setattr(self, f"switch_{key}", switch)
            row.addWidget(switch)
            layout.addLayout(row)

        layout.addWidget(HLine(self.theme, 22))

        tools = QHBoxLayout()
        tools.setSpacing(6)
        for title, slot in (("数据目录", window.open_data_dir), ("导出 MD", window.export_markdown)):
            button = QPushButton(title)
            button.setObjectName("modeBtn")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(slot)
            tools.addWidget(button)
        tools.addStretch()
        layout.addLayout(tools)

        hotkey = QLabel(f"快速记录：{settings.get('hotkey', 'Ctrl+Alt+N')}")
        hotkey.setObjectName("settingHint")
        layout.addWidget(hotkey)
        self.setFixedWidth(258)


class Popover(QFrame):
    def __init__(self, theme: Theme, window: "NotesWindow") -> None:
        super().__init__(window)
        self.theme = theme
        self.window_ref = window
        self.setObjectName("popover")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.outer = QVBoxLayout(self)
        self.outer.setContentsMargins(0, 0, 0, 0)
        self.content: SettingsContent | None = None
        self.hide()

    def refresh(self) -> None:
        if self.content is not None:
            self.content.setParent(None)
            self.content.deleteLater()
        self.content = SettingsContent(self.theme, self.window_ref)
        self.outer.addWidget(self.content)
        self.adjustSize()

    def __getattr__(self, name: str):
        content = self.__dict__.get("content")
        if content is not None and hasattr(content, name):
            return getattr(content, name)
        raise AttributeError(name)


class NotesWindow(QWidget):
    def __init__(self, store: Store, theme: Theme, shot_path: str | None = None) -> None:
        super().__init__()
        self.store = store
        self.theme = theme
        self.shot_path = shot_path
        self.today = date.today()
        self.selected = self.today
        self.view_mode = store.settings.get("view", "week")
        self.month_anchor = self.today.replace(day=1)
        self.week_anchor = self.today - timedelta(days=self.today.weekday())
        self.rows: dict[str, TaskRow] = {}
        self.undo_stack: list[dict] = []
        self.notified: set[str] = set()
        self.celebrated: str | None = None
        self.search_query = ""
        self.pinned = bool(store.settings.get("alwaysOnTop", True))
        self._drag_edge: str | None = None
        self._drag_origin = QPoint()
        self._drag_geometry = QRect()
        self.hotkey: GlobalHotkey | None = None
        self._shown_once = False
        self._fade_timer = QTimer(self)
        self._fade_timer.setSingleShot(True)
        self._fade_timer.timeout.connect(self._apply_fade)

        self.setWindowTitle("桌面便签 Lite")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(MIN_WIDTH, MIN_HEIGHT)
        self.setMouseTracking(True)

        self._build_ui()
        self._restore_geometry()
        self._build_tray()
        self._install_hotkey()
        self._setup_timers()
        self.render_all(animate=False)
        self.setStyleSheet(self.theme.stylesheet())
        if self.store.errors:
            self.toast.show_message(self.store.errors[-1], timeout=6000)

    # ------------------------------------------------------------------ 构建

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(15, 11, 15, 13)
        outer.setSpacing(0)

        outer.addWidget(self._build_titlebar())
        outer.addSpacing(6)
        outer.addWidget(self._build_hero())
        outer.addSpacing(8)
        outer.addWidget(self._build_calendar())
        outer.addSpacing(7)
        outer.addWidget(HLine(self.theme, 20))
        outer.addSpacing(2)
        outer.addWidget(self._build_carry_row())

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_list())
        self.stack.addWidget(self._build_empty_state())
        outer.addWidget(self.stack, 1)

        outer.addWidget(self._build_add_area())
        self.preview = QLabel("")
        self.preview.setObjectName("previewLabel")
        self.preview.setContentsMargins(3, 2, 3, 0)
        self.preview.setVisible(False)
        outer.addWidget(self.preview)
        outer.addSpacing(2)
        outer.addWidget(self._build_footer())

        self.toast = Toast(self.theme, self)
        self.celebration = Celebration(self.theme, self)
        self.popover = Popover(self.theme, self)

    def _build_titlebar(self) -> QWidget:
        bar = TitleBar(self)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(1, 0, 0, 0)
        layout.setSpacing(6)

        layout.addWidget(BrandDot(self.theme, 13))
        self.brand = QLabel("便签")
        layout.addWidget(self.brand)
        layout.addStretch()

        self.search_btn = IconButton(self.theme, "search", 24, "搜索（Ctrl+F）")
        self.search_btn.clicked.connect(self.open_search)
        layout.addWidget(self.search_btn)

        self.settings_btn = IconButton(self.theme, "settings", 24, "设置")
        self.settings_btn.clicked.connect(self.toggle_settings)
        layout.addWidget(self.settings_btn)

        self.pin_btn = IconButton(self.theme, "pin", 24, "置顶")
        self.pin_btn.set_active(self.pinned)
        self.pin_btn.clicked.connect(lambda: self.toggle_setting("alwaysOnTop", not self.pinned))
        layout.addWidget(self.pin_btn)

        self.close_btn = IconButton(self.theme, "close", 24, "隐藏到托盘（Esc）")
        self.close_btn.clicked.connect(self.hide_to_tray)
        layout.addWidget(self.close_btn)
        return bar

    def _build_hero(self) -> QWidget:
        hero = QWidget()
        hero.setFixedHeight(74)
        layout = QHBoxLayout(hero)
        layout.setContentsMargins(2, 4, 3, 2)
        layout.setSpacing(8)

        text_box = QVBoxLayout()
        text_box.setSpacing(1)
        self.date_label = QLabel("")
        self.date_label.setObjectName("heroDate")
        text_box.addWidget(self.date_label)

        sub_row = QHBoxLayout()
        sub_row.setSpacing(6)
        self.week_label = QLabel("")
        self.week_label.setObjectName("heroWeek")
        sub_row.addWidget(self.week_label)
        self.streak_label = QLabel("")
        self.streak_label.setObjectName("heroStreak")
        sub_row.addWidget(self.streak_label)
        sub_row.addStretch()
        text_box.addLayout(sub_row)
        text_box.addStretch()
        layout.addLayout(text_box, 1)

        self.ring = ProgressRing(self.theme, 62, 5.0)
        layout.addWidget(self.ring)
        return hero

    def _build_calendar(self) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(2)
        self.prev_btn = IconButton(self.theme, "chevron_left", 22, "上一页")
        self.prev_btn.clicked.connect(lambda: self.shift_period(-1))
        head.addWidget(self.prev_btn)

        self.period_label = QPushButton("")
        self.period_label.setObjectName("monthTitle")
        self.period_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.period_label.setFixedHeight(22)
        self.period_label.clicked.connect(self.toggle_view)
        self.period_label.setToolTip("点击切换周 / 月视图")
        head.addWidget(self.period_label)

        self.next_btn = IconButton(self.theme, "chevron_right", 22, "下一页")
        self.next_btn.clicked.connect(lambda: self.shift_period(1))
        head.addWidget(self.next_btn)
        head.addStretch()

        self.today_btn = QPushButton("今天")
        self.today_btn.setObjectName("todayBtn")
        self.today_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.today_btn.clicked.connect(self.go_today)
        head.addWidget(self.today_btn)
        layout.addLayout(head)

        self.week_strip = QWidget()
        week_layout = QHBoxLayout(self.week_strip)
        week_layout.setContentsMargins(0, 0, 0, 0)
        week_layout.setSpacing(1)
        self.week_cells: list[DayCell] = []
        for _ in range(7):
            cell = DayCell(self.theme, compact=True)
            cell.clicked.connect(lambda _=False, c=cell: self.select_date(c.day))
            week_layout.addWidget(cell, 1)
            self.week_cells.append(cell)
        layout.addWidget(self.week_strip)

        self.month_grid = QWidget()
        grid = QGridLayout(self.month_grid)
        grid.setContentsMargins(0, 2, 0, 0)
        grid.setHorizontalSpacing(1)
        grid.setVerticalSpacing(2)
        self.month_headers: list[QLabel] = []
        for index, name in enumerate(WEEKDAY_SHORT):
            label = QLabel(name)
            label.setObjectName("weekday")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(label, 0, index)
            self.month_headers.append(label)
        self.month_cells: list[DayCell] = []
        for index in range(42):
            cell = DayCell(self.theme, compact=False)
            cell.clicked.connect(lambda _=False, c=cell: self.select_date(c.day))
            grid.addWidget(cell, 1 + index // 7, index % 7)
            self.month_cells.append(cell)
        layout.addWidget(self.month_grid)
        self.month_grid.setVisible(self.view_mode == "month")
        self.week_strip.setVisible(self.view_mode == "week")
        return box

    def _build_carry_row(self) -> QWidget:
        self.carry_row = QWidget()
        self.carry_row.setFixedHeight(26)
        layout = QHBoxLayout(self.carry_row)
        layout.setContentsMargins(3, 0, 3, 0)
        layout.setSpacing(6)
        self.carry_hint = QLabel("")
        self.carry_hint.setObjectName("carryHint")
        layout.addWidget(self.carry_hint)
        layout.addStretch()
        self.carry_btn = QPushButton("搬到今天")
        self.carry_btn.setObjectName("carryBtn")
        self.carry_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.carry_btn.clicked.connect(self.carry_over)
        layout.addWidget(self.carry_btn)
        self.carry_row.setVisible(False)
        return self.carry_row

    def _build_list(self) -> QWidget:
        self.scroll = QScrollArea()
        self.scroll.setObjectName("scrollArea")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.viewport().setAutoFillBackground(False)

        self.list_container = QWidget()
        self.list_container.setObjectName("listContainer")
        self.list_container.setAutoFillBackground(False)
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 2, 0, 2)
        self.list_layout.setSpacing(1)
        self.list_layout.addStretch()
        self.scroll.setWidget(self.list_container)
        return self.scroll

    def _build_empty_state(self) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addStretch()
        self.empty_title = QLabel("今天还没有待办")
        self.empty_title.setObjectName("emptyTitle")
        self.empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty_title)
        self.empty_hint = QLabel("在下方输入，回车即可添加")
        self.empty_hint.setObjectName("emptyHint")
        self.empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty_hint)
        layout.addStretch()
        return box

    def _build_add_area(self) -> QWidget:
        self.add_bar = QFrame()
        self.add_bar.setObjectName("addBar")
        self.add_bar.setFixedHeight(40)
        self.add_bar.setProperty("focused", "false")
        layout = QHBoxLayout(self.add_bar)
        layout.setContentsMargins(12, 0, 6, 0)
        layout.setSpacing(6)

        self.input = QLineEdit()
        self.input.setObjectName("addInput")
        self.input.setMaxLength(MAX_TEXT + 40)
        self.input.setPlaceholderText("添加待办，回车保存　·　试试：明天 15:00 !!")
        self.input.textChanged.connect(self.on_input_changed)
        self.input.returnPressed.connect(self.add_from_input)
        self.input.installEventFilter(self)
        layout.addWidget(self.input, 1)

        self.add_btn = AccentFab(self.theme, 26)
        self.add_btn.clicked.connect(self.add_from_input)
        layout.addWidget(self.add_btn)

        self.search_bar = QFrame()
        self.search_bar.setObjectName("searchBar")
        self.search_bar.setFixedHeight(36)
        search_layout = QHBoxLayout(self.search_bar)
        search_layout.setContentsMargins(12, 0, 8, 0)
        search_layout.setSpacing(6)
        self.search_input = QLineEdit()
        self.search_input.setObjectName("searchInput")
        self.search_input.setPlaceholderText("搜索所有待办…")
        self.search_input.textChanged.connect(self.on_search_changed)
        self.search_input.returnPressed.connect(self.jump_to_first_result)
        self.search_input.installEventFilter(self)
        search_layout.addWidget(self.search_input, 1)
        self.search_close = IconButton(self.theme, "close", 20, "关闭搜索")
        self.search_close.clicked.connect(self.close_search)
        search_layout.addWidget(self.search_close)
        self.search_bar.setVisible(False)

        wrapper = QWidget()
        wrap_layout = QVBoxLayout(wrapper)
        wrap_layout.setContentsMargins(0, 0, 0, 0)
        wrap_layout.setSpacing(3)
        wrap_layout.addWidget(self.search_bar)
        wrap_layout.addWidget(self.add_bar)
        return wrapper

    def _build_footer(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(22)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(3, 0, 1, 0)
        layout.setSpacing(6)
        self.footer_label = QLabel("")
        self.footer_label.setObjectName("footerStat")
        layout.addWidget(self.footer_label)
        layout.addStretch()
        self.heatmap = Heatmap(self.theme, 28)
        layout.addWidget(self.heatmap)
        return bar

    # --------------------------------------------------- 托盘 / 热键 / 计时器

    def _icon(self) -> QIcon:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for name in ("tray.png", "icon.png", "icon.ico"):
            path = os.path.join(base, "assets", name)
            if os.path.exists(path):
                return QIcon(path)
        return QIcon()

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(self._icon(), self)
        self.tray.setToolTip("桌面便签 Lite")
        menu = QMenu()
        action_show = QAction("显示便签", self)
        action_show.triggered.connect(self.show_and_focus)
        menu.addAction(action_show)

        action_new = QAction("记录一条待办", self)
        action_new.triggered.connect(self.show_and_focus)
        menu.addAction(action_new)

        self.act_pin = QAction("窗口置顶", self)
        self.act_pin.setCheckable(True)
        self.act_pin.setChecked(self.pinned)
        self.act_pin.toggled.connect(
            lambda checked: self.toggle_setting("alwaysOnTop", checked, from_action=True)
        )
        menu.addAction(self.act_pin)

        self.act_auto = QAction("开机自启", self)
        self.act_auto.setCheckable(True)
        self.act_auto.setChecked(self.autostart_enabled())
        self.act_auto.toggled.connect(
            lambda checked: self.toggle_setting("autostart", checked, from_action=True)
        )
        menu.addAction(self.act_auto)

        menu.addSeparator()
        action_quit = QAction("退出", self)
        action_quit.triggered.connect(self.quit_app)
        menu.addAction(action_quit)

        self.tray_menu = menu
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            if self.isVisible() and not self.isMinimized():
                self.hide()
            else:
                self.show_and_focus()

    def _install_hotkey(self) -> None:
        sequence = self.store.settings.get("hotkey", "Ctrl+Alt+N")
        self.hotkey = GlobalHotkey(int(self.winId()), sequence)
        if not self.hotkey.register():
            self.store.crash_log(f"热键注册失败：{self.hotkey.error}")
        else:
            QApplication.instance().installNativeEventFilter(self.hotkey)
            self.hotkey.triggered.connect(self.show_and_focus)

    def _setup_timers(self) -> None:
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(AUTOSAVE_MS)
        self.save_timer.timeout.connect(self.store.save)

        self.midnight_timer = QTimer(self)
        self.midnight_timer.setInterval(MIDNIGHT_CHECK_MS)
        self.midnight_timer.timeout.connect(self.check_rollover)
        self.midnight_timer.start()

        self.reminder_timer = QTimer(self)
        self.reminder_timer.setInterval(REMINDER_CHECK_MS)
        self.reminder_timer.timeout.connect(self.check_reminders)
        self.reminder_timer.start()

        self.snap_timer = QTimer(self)
        self.snap_timer.setSingleShot(True)
        self.snap_timer.setInterval(180)
        self.snap_timer.timeout.connect(self._apply_snap)

        self.geometry_timer = QTimer(self)
        self.geometry_timer.setSingleShot(True)
        self.geometry_timer.setInterval(700)
        self.geometry_timer.timeout.connect(self._save_geometry)

    def touch(self) -> None:
        self.store.touch()
        self.save_timer.start()

    # ------------------------------------------------------------- 渲染

    def render_all(self, animate: bool = False) -> None:
        self.render_header(animate=animate)
        self.render_calendar()
        self.render_tasks(animate=animate)
        self.render_footer()
        self.render_carry()

    def render_header(self, animate: bool = False) -> None:
        day = self.selected
        self.date_label.setText(
            f"{day.month}月{day.day}日"
            if day.year == self.today.year
            else f"{day.year}年{day.month}月{day.day}日"
        )
        delta = (day - self.today).days
        weekday = WEEKDAY_FULL[day.weekday()]
        if delta == 0:
            weekday = f"{weekday} · 今天"
        elif delta == -1:
            weekday = f"{weekday} · 昨天"
        elif delta == 1:
            weekday = f"{weekday} · 明天"
        self.week_label.setText(weekday)

        streak = self.store.streak()
        self.streak_label.setText(f"连续 {streak} 天清零" if streak else "")

        items = self.store.peek_tasks(day)
        done = sum(1 for item in items if item.get("done"))
        self.ring.set_data(done, len(items), animate=animate)

    def render_calendar(self) -> None:
        if self.view_mode == "week":
            end = self.week_anchor + timedelta(days=6)
            self.period_label.setText(
                f"{self.week_anchor.month}月{self.week_anchor.day}日 – {end.month}月{end.day}日"
            )
            for index, cell in enumerate(self.week_cells):
                day = self.week_anchor + timedelta(days=index)
                self._configure_cell(
                    cell,
                    day,
                    in_month=True,
                    selected=(day == self.selected),
                    weekday_label=WEEKDAY_SHORT[index],
                )
            self.week_strip.setVisible(True)
            self.month_grid.setVisible(False)
        else:
            self.period_label.setText(f"{self.month_anchor.year}年{self.month_anchor.month}月")
            first = self.month_anchor
            start = first - timedelta(days=first.weekday())
            for index, cell in enumerate(self.month_cells):
                day = start + timedelta(days=index)
                self._configure_cell(
                    cell,
                    day,
                    in_month=(day.month == first.month),
                    selected=(day == self.selected),
                )
            self.week_strip.setVisible(False)
            self.month_grid.setVisible(True)

    def _configure_cell(
        self, cell: DayCell, day: date, *, in_month: bool, selected: bool, weekday_label: str = ""
    ) -> None:
        items = self.store.peek_tasks(day)
        if not items:
            marker = 0
        elif all(item.get("done") for item in items):
            marker = 2
        else:
            marker = 1
        cell.configure(
            day,
            in_month=in_month,
            is_today=(day == self.today),
            selected=selected,
            marker=marker,
            weekday_label=weekday_label,
        )

    def render_tasks(self, animate: bool = False) -> None:
        if self.search_query:
            self._render_search_results()
            return
        items = sorted(
            self.store.peek_tasks(self.selected), key=lambda task: bool(task.get("done"))
        )
        wanted = {task.get("id") for task in items if task.get("id")}
        for task_id in list(self.rows):
            if task_id not in wanted:
                row = self.rows.pop(task_id)
                self._drop_row(row)

        for index, task in enumerate(items):
            task_id = task.get("id") or ""
            row = self.rows.get(task_id)
            if row is None:
                row = self._make_row(task)
                self.rows[task_id] = row
                self.list_layout.insertWidget(index, row)
            else:
                row.set_task(task)
                if self.list_layout.indexOf(row) != index:
                    self.list_layout.removeWidget(row)
                    self.list_layout.insertWidget(index, row)
        self.stack.setCurrentIndex(0 if items else 1)
        if not items:
            self.empty_title.setText("这天还没有待办")
            self.empty_hint.setText("在下方输入，回车即可添加")

    def _make_row(self, task: dict, show_date: str = "") -> TaskRow:
        row = TaskRow(self.theme, task, show_date=show_date)
        row.toggled.connect(self.toggle_task)
        row.deleted.connect(self.delete_task)
        row.edited.connect(self.edit_task)
        row.menuRequested.connect(self.show_row_menu)
        return row

    def _drop_row(self, row: TaskRow) -> None:
        self.list_layout.removeWidget(row)
        row.setParent(None)
        row.deleteLater()

    def _render_search_results(self) -> None:
        query = self.search_query.lower()
        hits: list[tuple[date, dict]] = []
        for key, items in self.store.data["tasks"].items():
            try:
                day = date.fromisoformat(key)
            except ValueError:
                continue
            for task in items:
                if query in (task.get("text") or "").lower():
                    hits.append((day, task))
        hits.sort(key=lambda pair: pair[0], reverse=True)
        hits = hits[:40]

        for row in list(self.rows.values()):
            self._drop_row(row)
        self.rows.clear()
        for index, (day, task) in enumerate(hits):
            row = self._make_row(task, show_date=format_day(day, self.today))
            self.list_layout.insertWidget(index, row)
            self.rows[task.get("id") or f"hit-{index}"] = row
        self.stack.setCurrentIndex(0 if hits else 1)
        if not hits:
            self.empty_title.setText("没有匹配的待办")
            self.empty_hint.setText(f"「{self.search_query}」在全部日期里都没找到")

    def render_footer(self) -> None:
        total, done = self.store.month_stats(self.today.year, self.today.month)
        streak = self.store.streak()
        parts = [f"本月 {done}/{total}" if total else "本月暂无待办"]
        if streak:
            parts.append(f"连续 {streak} 天清零")
        self.footer_label.setText("　·　".join(parts))
        self.heatmap.set_data(self.store.heatmap(28, self.today))

    def render_carry(self) -> None:
        yesterday = self.selected - timedelta(days=1)
        pending = self.store.pending(yesterday) if self.selected == self.today else []
        if not pending:
            self.carry_row.setVisible(False)
            return
        self.carry_hint.setText(f"昨天还有 {len(pending)} 项未完成")
        self.carry_row.setVisible(True)

    # ------------------------------------------------------------- 交互

    def select_date(self, day: date | None) -> None:
        if day is None:
            return
        self.selected = day
        self.week_anchor = day - timedelta(days=day.weekday())
        self.month_anchor = day.replace(day=1)
        self.render_all(animate=True)
        self._mark_interaction()

    def go_today(self) -> None:
        self.today = date.today()
        self.select_date(self.today)

    def shift_period(self, step: int) -> None:
        if self.view_mode == "week":
            self.week_anchor = self.week_anchor + timedelta(days=7 * step)
            self.select_date(self.week_anchor + timedelta(days=self.selected.weekday()))
        else:
            month = self.month_anchor
            new_month = month.month + step
            year = month.year + (new_month - 1) // 12
            new_month = (new_month - 1) % 12 + 1
            self.month_anchor = date(year, new_month, 1)
            self.render_calendar()

    def toggle_view(self) -> None:
        self.view_mode = "month" if self.view_mode == "week" else "week"
        self.week_anchor = self.selected - timedelta(days=self.selected.weekday())
        self.month_anchor = self.selected.replace(day=1)
        self.store.set_setting("view", self.view_mode)
        self.touch()
        self.render_calendar()

    def on_input_changed(self, text: str) -> None:
        parsed = parse_quick_add(text, self.today)
        summary = parsed.summary()
        if summary and parsed.text:
            self.preview.setText(f"→ {summary}")
            self.preview.setVisible(True)
        else:
            self.preview.setVisible(False)
        self._mark_interaction()

    def add_from_input(self) -> None:
        raw = self.input.text().strip()
        if not raw:
            return
        parsed = parse_quick_add(raw, self.today)
        text = parsed.text or raw
        target = parsed.target_date or self.selected
        if parsed.series is not None:
            series = self.store.add_series(
                text,
                rule=parsed.series.get("rule", "daily"),
                weekdays=parsed.series.get("weekdays") or [],
                day_of_month=parsed.series.get("dayOfMonth") or 1,
                priority=parsed.priority,
                remind_at=parsed.remind_at,
            )
            if series is None:
                return
            self.push_undo({"type": "series_add", "id": series["id"]})
        else:
            task = self.store.add_task(
                target, text, priority=parsed.priority, remind_at=parsed.remind_at
            )
            if task is None:
                return
            self.push_undo({"type": "add", "date": target.isoformat(), "id": task["id"]})
        self.input.clear()
        self.preview.setVisible(False)
        if target != self.selected:
            self.select_date(target)
        else:
            self.render_all(animate=True)
        self.touch()

    def toggle_task(self, task_id: str, done: bool) -> None:
        task = self.store.set_done(self.selected, task_id, done)
        if task is None:
            return
        self.push_undo(
            {"type": "toggle", "date": self.selected.isoformat(), "id": task_id, "done": not done}
        )
        self.render_header(animate=True)
        self.render_footer()
        self.render_calendar()
        self.touch()
        if done:
            items = self.store.peek_tasks(self.selected)
            if (
                items
                and all(item.get("done") for item in items)
                and self.celebrated != self.selected.isoformat()
            ):
                self.celebrated = self.selected.isoformat()
                self.celebration.play("今日清零 ✓")

    def delete_task(self, task_id: str) -> None:
        row = self.rows.pop(task_id, None)
        removed = self.store.delete_task(self.selected, task_id)
        if removed is None:
            return
        index, task = removed
        self.push_undo(
            {"type": "delete", "date": self.selected.isoformat(), "index": index, "task": task}
        )
        if row is not None:
            self._drop_row(row)
        self.render_all(animate=True)
        self.touch()
        preview = (task.get("text") or "")[:14]
        self.toast.show_message(f"已删除「{preview}」", "撤销", self.undo, 5000)

    def edit_task(self, task_id: str, text: str) -> None:
        text = " ".join(text.split()).strip()[:MAX_TEXT]
        if not text:
            return
        found = self.store.find_task(self.selected, task_id)
        if found is None:
            return
        old = found[1].get("text", "")
        if old == text:
            return
        self.store.update_task(self.selected, task_id, text=text)
        self.push_undo(
            {"type": "edit", "date": self.selected.isoformat(), "id": task_id, "text": old}
        )
        self.render_tasks()
        self.touch()

    def carry_over(self) -> None:
        yesterday = self.selected - timedelta(days=1)
        moved = self.store.carry_over(yesterday, self.selected)
        if not moved:
            return
        self.push_undo(
            {
                "type": "carry",
                "from": yesterday.isoformat(),
                "to": self.selected.isoformat(),
                "tasks": moved,
            }
        )
        self.render_all(animate=True)
        self.touch()
        self.toast.show_message(f"已搬来 {len(moved)} 项", "撤销", self.undo, 5000)

    def show_row_menu(self, task_id: str, pos: QPoint) -> None:
        found = self.store.find_task(self.selected, task_id)
        if found is None:
            return
        task = found[1]
        menu = QMenu(self)
        act_today = menu.addAction("移到今天")
        act_tomorrow = menu.addAction("移到明天")
        menu.addSeparator()
        priority_menu = menu.addMenu("优先级")
        priority_actions = {}
        for value, label in ((0, "普通"), (1, "高"), (2, "紧急")):
            action = priority_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(task.get("priority", 0) == value)
            priority_actions[action] = value
        menu.addSeparator()
        act_delete = menu.addAction("删除")

        chosen = menu.exec(pos)
        if chosen is None:
            return
        if chosen is act_today:
            self._move_task(self.selected, date.today(), task)
        elif chosen is act_tomorrow:
            self._move_task(self.selected, date.today() + timedelta(days=1), task)
        elif chosen is act_delete:
            self.delete_task(task_id)
        elif chosen in priority_actions:
            old = task.get("priority", 0)
            self.store.update_task(self.selected, task_id, priority=priority_actions[chosen])
            self.push_undo(
                {"type": "priority", "date": self.selected.isoformat(), "id": task_id, "value": old}
            )
            self.render_tasks()
            self.touch()

    def _move_task(self, source: date, target: date, task: dict) -> None:
        if source == target:
            return
        removed = self.store.delete_task(source, task["id"])
        if removed is None:
            return
        index, removed_task = removed
        self.store.insert_task(target, 10_000, removed_task)
        self.push_undo(
            {
                "type": "move",
                "from": source.isoformat(),
                "to": target.isoformat(),
                "index": index,
                "id": task["id"],
            }
        )
        self.render_all(animate=True)
        self.touch()
        self.toast.show_message(f"已移到 {format_day(target, self.today)}", "撤销", self.undo)

    # ------------------------------------------------------------- 撤销

    def push_undo(self, operation: dict) -> None:
        self.undo_stack.append(operation)
        if len(self.undo_stack) > MAX_UNDO:
            self.undo_stack.pop(0)

    def undo(self) -> None:
        if not self.undo_stack:
            self.toast.show_message("没有可撤销的操作")
            return
        operation = self.undo_stack.pop()
        kind = operation.get("type")
        if kind == "add":
            self.store.delete_task(date.fromisoformat(operation["date"]), operation["id"])
        elif kind == "delete":
            self.store.insert_task(
                date.fromisoformat(operation["date"]), operation["index"], operation["task"]
            )
        elif kind == "toggle":
            self.store.set_done(
                date.fromisoformat(operation["date"]), operation["id"], operation["done"]
            )
        elif kind == "edit":
            self.store.update_task(
                date.fromisoformat(operation["date"]), operation["id"], text=operation["text"]
            )
        elif kind == "priority":
            self.store.update_task(
                date.fromisoformat(operation["date"]), operation["id"], priority=operation["value"]
            )
        elif kind == "move":
            source = date.fromisoformat(operation["from"])
            target = date.fromisoformat(operation["to"])
            found = self.store.find_task(target, operation["id"])
            if found is not None:
                _, task = found
                self.store.delete_task(target, task["id"])
                self.store.insert_task(source, operation["index"], task)
        elif kind == "carry":
            self.store.undo_carry(
                operation["tasks"],
                date.fromisoformat(operation["from"]),
                date.fromisoformat(operation["to"]),
            )
        elif kind == "series_add":
            self.store.delete_series(operation["id"], keep_existing=False)
        self.render_all(animate=True)
        self.touch()
        self.toast.show_message("已撤销")

    # ------------------------------------------------------------- 搜索

    def open_search(self) -> None:
        self.search_bar.setVisible(True)
        self.add_bar.setVisible(False)
        self.search_input.setFocus()
        self.search_input.selectAll()

    def close_search(self) -> None:
        self.search_query = ""
        self.search_input.clear()
        self.search_bar.setVisible(False)
        self.add_bar.setVisible(True)
        self.render_tasks()

    def on_search_changed(self, text: str) -> None:
        self.search_query = text.strip()
        self.render_tasks()

    def jump_to_first_result(self) -> None:
        if not self.search_query:
            return
        query = self.search_query.lower()
        for key, items in self.store.data["tasks"].items():
            try:
                day = date.fromisoformat(key)
            except ValueError:
                continue
            for task in items:
                if query in (task.get("text") or "").lower():
                    self.close_search()
                    self.select_date(day)
                    return

    # ------------------------------------------------------------- 设置

    def toggle_settings(self) -> None:
        if self.popover.isVisible():
            self.popover.hide()
            return
        self.popover.refresh()
        self.popover.move(self.width() - self.popover.width() - 13, 44)
        self.popover.show()
        self.popover.raise_()

    def set_theme_mode(self, mode: str) -> None:
        self.store.set_setting("theme", mode)
        self.theme.set_mode(mode)
        self.rebuild_styles()
        self.popover.hide()
        self.touch()

    def set_accent(self, color: str) -> None:
        self.store.set_setting("accent", color)
        self.theme.set_accent(color)
        self.rebuild_styles()
        self.popover.hide()
        self.touch()

    def pick_accent(self) -> None:
        color = QColorDialog.getColor(self.theme.accent, self, "选择强调色")
        if color.isValid():
            self.set_accent(color.name())

    def set_opacity(self, value: int) -> None:
        self.store.set_setting("opacity", int(value))
        self.popover.opacity_value.setText(f"{int(value)}%")
        self.update()
        self.touch()

    def toggle_setting(self, key: str, value, from_action: bool = False) -> None:
        self.store.set_setting(key, value)
        self.touch()
        if key == "alwaysOnTop":
            self.pinned = bool(value)
            self.apply_topmost(self.pinned)
            self.pin_btn.set_active(self.pinned)
            if not from_action and self.act_pin.isChecked() != self.pinned:
                self.act_pin.setChecked(self.pinned)
        elif key == "autostart":
            enabled = self.apply_autostart(bool(value))
            if enabled != bool(value):
                self.store.set_setting("autostart", enabled)
                self.touch()
                self.toast.show_message("启动项写入失败，详情见 crash.log")
            switch = getattr(self.popover, "switch_autostart", None)
            if switch is not None:
                switch.set_checked(enabled, animate=False)
            if not from_action and self.act_auto.isChecked() != enabled:
                self.act_auto.setChecked(enabled)
        elif key == "autoFade":
            if not value:
                self.setWindowOpacity(1.0)
            switch = getattr(self.popover, "switch_autoFade", None)
            if switch is not None:
                switch.set_checked(bool(value), animate=False)
        elif key == "snap":
            switch = getattr(self.popover, "switch_snap", None)
            if switch is not None:
                switch.set_checked(bool(value), animate=False)

    def rebuild_styles(self) -> None:
        self.setStyleSheet(self.theme.stylesheet())
        self.brand.setStyleSheet(
            "color: rgba(%d, %d, %d, %d); font-size: 11.5px; font-weight: 600; letter-spacing: 0.5px;"
            % (
                self.theme.muted.red(),
                self.theme.muted.green(),
                self.theme.muted.blue(),
                self.theme.muted.alpha(),
            )
        )
        for row in self.rows.values():
            row.theme = self.theme
            row.label.theme = self.theme
            row.label._apply_style()
        self.render_all()
        for widget in (self.heatmap, self.ring, self.add_btn):
            widget.update()
        self.update()

    def open_data_dir(self) -> None:
        try:
            os.startfile(self.store.directory)  # type: ignore[attr-defined]
        except OSError as exc:
            self.toast.show_message(f"打开失败：{exc}")

    def export_markdown(self) -> None:
        default = os.path.join(os.path.expanduser("~"), "桌面便签导出.md")
        path, _ = QFileDialog.getSaveFileName(self, "导出为 Markdown", default, "Markdown (*.md)")
        if not path:
            return
        try:
            self.store.export_markdown(path)
            self.toast.show_message("已导出 Markdown")
        except OSError as exc:
            self.toast.show_message(f"导出失败：{exc}")

    # ------------------------------------------------------------- 系统集成

    def _python_launcher(self) -> str:
        exe = sys.executable or "python.exe"
        if exe.lower().endswith("python.exe"):
            candidate = exe[: -len("python.exe")] + "pythonw.exe"
            if os.path.exists(candidate):
                return candidate
        return exe

    def _autostart_command(self) -> str:
        main_py = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py"
        )
        return f'"{self._python_launcher()}" "{main_py}"'

    def apply_autostart(self, enabled: bool) -> bool:
        try:
            import winreg  # noqa: PLC0415 - 仅 Windows 需要

            key = winreg.CreateKeyEx(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE,
            )
            try:
                if enabled:
                    winreg.SetValueEx(
                        key, "DesktopNotesLite", 0, winreg.REG_SZ, self._autostart_command()
                    )
                else:
                    try:
                        winreg.DeleteValue(key, "DesktopNotesLite")
                    except FileNotFoundError:
                        pass
            finally:
                winreg.CloseKey(key)
            return bool(enabled)
        except (ImportError, OSError) as exc:
            self.store.crash_log(f"开机自启设置失败：{exc}")
            return False

    def autostart_enabled(self) -> bool:
        try:
            import winreg  # noqa: PLC0415

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"
            )
            try:
                winreg.QueryValueEx(key, "DesktopNotesLite")
                return True
            finally:
                winreg.CloseKey(key)
        except (ImportError, OSError):
            return False

    def apply_topmost(self, enabled: bool) -> None:
        try:
            import ctypes  # noqa: PLC0415

            hwnd = int(self.winId())
            flag = -1 if enabled else -2  # HWND_TOPMOST / HWND_NOTOPMOST
            ctypes.windll.user32.SetWindowPos(hwnd, flag, 0, 0, 0, 0, 0x0003)
        except (AttributeError, OSError):
            pass

    def show_and_focus(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.input.setFocus()
        self.setWindowOpacity(1.0)

    def hide_to_tray(self) -> None:
        self.hide()
        if self.tray.supportsMessages():
            self.tray.showMessage(
                "桌面便签还在运行",
                "点击托盘图标可以重新打开；退出请右键托盘图标。",
                QSystemTrayIcon.MessageIcon.Information,
                3000,
            )

    def quit_app(self) -> None:
        self.store.save()
        if self.hotkey is not None:
            self.hotkey.unregister()
        self.tray.hide()
        QApplication.instance().quit()

    # ------------------------------------------------------------- 计时器

    def check_rollover(self) -> None:
        current = date.today()
        if current == self.today:
            return
        was_today = self.selected == self.today
        self.today = current
        if was_today:
            self.selected = current
        self.week_anchor = self.selected - timedelta(days=self.selected.weekday())
        self.month_anchor = self.selected.replace(day=1)
        self.store.materialize(span=28)
        self.render_all()
        self.touch()

    def check_reminders(self) -> None:
        now = datetime.now()
        stamp = now.strftime("%H:%M")
        day_key = now.strftime("%Y-%m-%d")
        for task in self.store.peek_tasks(self.today):
            remind = task.get("remindAt")
            if not remind or task.get("done") or remind > stamp:
                continue
            key = f"{day_key}:{task.get('id')}"
            if key in self.notified:
                continue
            self.notified.add(key)
            text = task.get("text", "")
            self.toast.show_message(f"⏰ {text[:16]}", "查看", self.show_and_focus, 6000)
            if self.tray.supportsMessages():
                self.tray.showMessage(
                    "待办提醒", text, QSystemTrayIcon.MessageIcon.Information, 5000
                )

    def _mark_interaction(self) -> None:
        if self.windowOpacity() < 1.0:
            self.setWindowOpacity(1.0)

    def _apply_fade(self) -> None:
        if not self.store.settings.get("autoFade"):
            return
        if self.underMouse() or self.input.hasFocus() or self.search_input.hasFocus():
            return
        self.setWindowOpacity(0.45)

    # ------------------------------------------------------------- 事件

    def eventFilter(self, obj, event) -> bool:
        search_input = getattr(self, "search_input", None)
        watched = [widget for widget in (getattr(self, "input", None), search_input) if widget]
        if obj in watched:
            if event.type() == event.Type.FocusIn:
                self.add_bar.setProperty("focused", "true")
                repolish(self.add_bar)
                self._mark_interaction()
            elif event.type() == event.Type.FocusOut:
                self.add_bar.setProperty("focused", "false")
                repolish(self.add_bar)
            elif event.type() == event.Type.KeyPress:
                if event.key() == Qt.Key.Key_Escape:
                    if obj is search_input and search_input is not None:
                        self.close_search()
                    else:
                        self.input.clear()
                        self.preview.setVisible(False)
                    return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key == Qt.Key.Key_Escape:
            if self.popover.isVisible():
                self.popover.hide()
            elif self.search_bar.isVisible():
                self.close_search()
            else:
                self.hide_to_tray()
            return
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if key == Qt.Key.Key_N:
                self.show_and_focus()
                return
            if key == Qt.Key.Key_F:
                self.open_search()
                return
            if key == Qt.Key.Key_Z:
                self.undo()
                return
        super().keyPressEvent(event)

    def enterEvent(self, event) -> None:
        self._fade_timer.stop()
        if self.store.settings.get("autoFade"):
            self.setWindowOpacity(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        if self.store.settings.get("autoFade"):
            self._fade_timer.start(5000)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if self.popover.isVisible() and not self.popover.geometry().contains(
            event.position().toPoint()
        ):
            self.popover.hide()
        if event.button() == Qt.MouseButton.LeftButton:
            edge = self._edge_at(event.position().toPoint())
            if edge:
                self._drag_edge = edge
                self._drag_origin = event.globalPosition().toPoint()
                self._drag_geometry = self.geometry()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_edge:
            self._resize_to(event.globalPosition().toPoint())
            return
        self.setCursor(self._cursor_for_edge(self._edge_at(event.position().toPoint())))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._drag_edge:
            self._drag_edge = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.geometry_timer.start()
            return
        super().mouseReleaseEvent(event)

    def _edge_at(self, pos: QPoint) -> str | None:
        margin = RESIZE_MARGIN
        edge = ""
        if pos.y() <= margin:
            edge += "t"
        if pos.y() >= self.height() - margin:
            edge += "b"
        if pos.x() <= margin:
            edge += "l"
        if pos.x() >= self.width() - margin:
            edge += "r"
        return edge or None

    @staticmethod
    def _cursor_for_edge(edge: str | None):
        if not edge:
            return Qt.CursorShape.ArrowCursor
        if edge in ("tl", "br"):
            return Qt.CursorShape.SizeFDiagCursor
        if edge in ("tr", "bl"):
            return Qt.CursorShape.SizeBDiagCursor
        if edge in ("l", "r"):
            return Qt.CursorShape.SizeHorCursor
        return Qt.CursorShape.SizeVerCursor

    def _resize_to(self, global_pos: QPoint) -> None:
        if self._drag_edge is None:
            return
        delta = global_pos - self._drag_origin
        geometry = QRect(self._drag_geometry)
        edge = self._drag_edge
        if "l" in edge:
            geometry.setLeft(min(geometry.left() + delta.x(), geometry.right() - MIN_WIDTH))
        if "r" in edge:
            geometry.setRight(max(geometry.left() + MIN_WIDTH, geometry.right() + delta.x()))
        if "t" in edge:
            geometry.setTop(min(geometry.top() + delta.y(), geometry.bottom() - MIN_HEIGHT))
        if "b" in edge:
            geometry.setBottom(max(geometry.top() + MIN_HEIGHT, geometry.bottom() + delta.y()))
        self.setGeometry(geometry)

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        self.snap_timer.start()
        self.geometry_timer.start()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "popover") and self.popover.isVisible():
            self.popover.move(self.width() - self.popover.width() - 13, 44)
        self.geometry_timer.start()

    def _apply_snap(self) -> None:
        if not self.store.settings.get("snap"):
            return
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        geometry = self.geometry()
        margin = 16
        moved = False
        if abs(geometry.left() - available.left()) < margin:
            geometry.moveLeft(available.left())
            moved = True
        elif abs(available.right() - geometry.right()) < margin:
            geometry.moveRight(available.right())
            moved = True
        if abs(geometry.top() - available.top()) < margin:
            geometry.moveTop(available.top())
            moved = True
        elif abs(available.bottom() - geometry.bottom()) < margin:
            geometry.moveBottom(available.bottom())
            moved = True
        if moved:
            self.setGeometry(geometry)

    def _restore_geometry(self) -> None:
        state = self.store.load_window_state()
        width = max(MIN_WIDTH, min(1600, int(state.get("width") or DEFAULT_WIDTH)))
        height = max(MIN_HEIGHT, min(1600, int(state.get("height") or DEFAULT_HEIGHT)))
        self.resize(width, height)
        screen = self.screen() or QApplication.primaryScreen()
        if screen is not None and state.get("x") is not None and state.get("y") is not None:
            available = screen.availableGeometry()
            x, y = int(state["x"]), int(state["y"])
            if available.contains(QPoint(x + 40, y + 20)):
                self.move(x, y)
        self.apply_topmost(self.pinned)

    def _save_geometry(self) -> None:
        geometry = self.geometry()
        self.store.save_window_state(geometry.x(), geometry.y(), geometry.width(), geometry.height())

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._shown_once:
            self._shown_once = True
            self.input.setFocus()
        self._mark_interaction()

    def closeEvent(self, event) -> None:
        self._save_geometry()
        self.store.save()
        if self.hotkey is not None:
            self.hotkey.unregister()
        event.accept()

    # ------------------------------------------------------------- 绘制

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        opacity = int(self.store.settings.get("opacity", 80))
        shell = QColor(self.theme.shell)
        shell.setAlpha(max(40, min(255, int(255 * opacity / 100))))
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(shell)
        painter.drawRoundedRect(rect, 18, 18)

        glow = QColor(self.theme.accent)
        glow.setAlpha(int(6 + 14 * opacity / 100))
        gradient = QRadialGradient(
            rect.left() + rect.width() * 0.2, rect.top() - 10, rect.width() * 0.75
        )
        gradient.setColorAt(0.0, glow)
        gradient.setColorAt(1.0, QColor(0, 0, 0, 0))
        path = QPainterPath()
        path.addRoundedRect(rect, 18, 18)
        painter.setClipPath(path)
        painter.setBrush(gradient)
        painter.drawRect(rect)
        painter.setClipping(False)

        painter.setPen(QPen(with_alpha(self.theme.text, 26), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, 18, 18)
