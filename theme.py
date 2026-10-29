"""配色、深浅主题与全局样式表。

主题层是这次改造的基础：原来所有颜色都写成字面量（`QColor(244, 239, 231, 230)`、
`rgba(255,255,255,13)` 之类散落在各个 paintEvent 与 QSS 里），导致「浅色主题」在
结构上不可能实现。现在统一收拢到 `Palette`：一套深色、一套浅色，所有组件只从
`theme` 取色，主题切换就是换调色板 + 重建 QSS。
"""

from dataclasses import dataclass, field

from PySide6.QtGui import QColor

DEFAULT_ACCENT = "#ffb26b"
PRESET_ACCENTS = [
    "#ffb26b",
    "#ff8f70",
    "#f58fb8",
    "#b49cff",
    "#7fb0ff",
    "#63d6c0",
    "#a5d96f",
]
MODE_DARK = "dark"
MODE_LIGHT = "light"


def normalize_hex(value) -> str:
    """把任意输入收敛成合法的 #rrggbb，失败时回落到默认色。"""
    if isinstance(value, str):
        candidate = value.strip().lower()
        if len(candidate) == 7 and candidate.startswith("#"):
            try:
                int(candidate[1:], 16)
                return candidate
            except ValueError:
                pass
    return DEFAULT_ACCENT


def mix_hex(color_hex: str, target_hex: str, ratio: float) -> str:
    a = QColor(color_hex)
    b = QColor(target_hex)
    ratio = max(0.0, min(1.0, ratio))
    return QColor(
        round(a.red() * (1 - ratio) + b.red() * ratio),
        round(a.green() * (1 - ratio) + b.green() * ratio),
        round(a.blue() * (1 - ratio) + b.blue() * ratio),
    ).name()


def rgba(color: QColor, alpha: int) -> str:
    return (
        f"rgba({color.red()}, {color.green()}, {color.blue()}, "
        f"{max(0, min(255, alpha))})"
    )


def with_alpha(color: QColor, alpha: int) -> QColor:
    out = QColor(color)
    out.setAlpha(alpha)
    return out


def luminance(color: QColor) -> float:
    def linear(value: int) -> float:
        c = value / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return (
        0.2126 * linear(color.red())
        + 0.7152 * linear(color.green())
        + 0.0722 * linear(color.blue())
    )


@dataclass(frozen=True)
class Palette:
    """一套主题的全部中性色。文本色按 alpha 分三档，形成信息层级。"""

    mode: str
    shell: QColor          # 便签底色
    text: QColor           # 主文本（不透明）
    muted_a: int           # 副信息
    faint_a: int           # 辅助信息
    line_a: int            # 分割线 / 描边
    panel: QColor          # 卡片底
    hover: QColor          # 悬停底
    popover: QColor        # 浮层底
    track: QColor          # 滑杆 / 进度条底槽
    heat_empty: QColor     # 热力图空格

    def alpha(self, value: int) -> QColor:
        return with_alpha(self.text, value)

    @property
    def muted(self) -> QColor:
        return self.alpha(self.muted_a)

    @property
    def faint(self) -> QColor:
        return self.alpha(self.faint_a)

    @property
    def line(self) -> QColor:
        return self.alpha(self.line_a)

    @property
    def text_hex(self) -> str:
        return self.text.name()


DARK = Palette(
    mode=MODE_DARK,
    shell=QColor(20, 20, 25),
    text=QColor(244, 239, 231),
    muted_a=107,
    faint_a=82,
    line_a=23,
    panel=QColor(255, 255, 255, 8),
    hover=QColor(255, 255, 255, 13),
    popover=QColor("#202027"),
    track=QColor(255, 255, 255, 18),
    heat_empty=QColor(255, 255, 255, 16),
)

LIGHT = Palette(
    mode=MODE_LIGHT,
    shell=QColor(252, 249, 243),
    text=QColor(43, 38, 34),
    muted_a=138,
    faint_a=100,
    line_a=26,
    panel=QColor(0, 0, 0, 6),
    hover=QColor(0, 0, 0, 10),
    popover=QColor("#ffffff"),
    track=QColor(0, 0, 0, 16),
    heat_empty=QColor(0, 0, 0, 12),
)

PALETTES = {MODE_DARK: DARK, MODE_LIGHT: LIGHT}


@dataclass
class Theme:
    accent_hex: str = DEFAULT_ACCENT
    mode: str = MODE_DARK
    accent: QColor = field(init=False)
    palette: Palette = field(init=False)
    ink: QColor = field(init=False)
    ink_hex: str = field(init=False)
    accent_text_hex: str = field(init=False)

    def __post_init__(self) -> None:
        self.palette = PALETTES.get(self.mode, DARK)
        self.mode = self.palette.mode
        self.set_accent(self.accent_hex)

    # ---------- 状态 ----------

    def set_mode(self, mode: str) -> None:
        self.palette = PALETTES.get(mode, DARK)
        self.mode = self.palette.mode
        self.set_accent(self.accent_hex)

    def set_accent(self, value: str) -> None:
        self.accent_hex = normalize_hex(value)
        self.accent = QColor(self.accent_hex)
        # 强调色上的文字：亮色用深墨，暗色用白
        self.ink = QColor("#241a10") if luminance(self.accent) > 0.35 else QColor("#ffffff")
        self.ink_hex = self.ink.name()
        self.accent_text_hex = mix_hex(self.accent_hex, self.palette.text.name(), 0.24)

    # ---------- 常用色 ----------

    @property
    def text(self) -> QColor:
        return self.palette.text

    @property
    def muted(self) -> QColor:
        return self.palette.muted

    @property
    def faint(self) -> QColor:
        return self.palette.faint

    @property
    def line(self) -> QColor:
        return self.palette.line

    @property
    def hover(self) -> QColor:
        return self.palette.hover

    @property
    def track(self) -> QColor:
        return self.palette.track

    @property
    def heat_empty(self) -> QColor:
        return self.palette.heat_empty

    @property
    def shell(self) -> QColor:
        return self.palette.shell

    def soft(self, alpha: int = 36) -> QColor:
        return with_alpha(self.accent, alpha)

    # ---------- 样式表 ----------

    def stylesheet(self) -> str:
        p = self.palette
        return (
            BASE_QSS
            .replace("__TEXT__", p.text_hex)
            .replace("__TEXT_A__", rgba(p.text, 235))
            .replace("__MUTED__", rgba(p.text, p.muted_a))
            .replace("__FAINT__", rgba(p.text, p.faint_a))
            .replace("__LINE__", rgba(p.text, p.line_a))
            .replace("__PANEL__", rgba(p.panel))
            .replace("__HOVER__", rgba(p.hover))
            .replace("__POPOVER__", p.popover.name())
            .replace("__TRACK__", rgba(p.track))
            .replace("__ACCENT_TEXT__", self.accent_text_hex)
            .replace("__ACCENT_50__", rgba(self.accent, 128))
            .replace("__ACCENT_12__", rgba(self.accent, 30))
            .replace("__ACCENT__", self.accent_hex)
        )


def rgba_qcolor(color: QColor) -> str:
    """`rgba(color)` 不带 alpha 时的便捷写法（保持原 alpha）。"""
    return rgba(color, color.alpha())


# 给 `Palette` 用的小工具：`rgba(p.panel)` 这种调用需要 alpha 默认值
_original_rgba = rgba


def rgba(color: QColor, alpha: int = None) -> str:  # noqa: F811 - 有意覆盖
    if alpha is None:
        alpha = color.alpha()
    return _original_rgba(color, alpha)


BASE_QSS = """
QWidget {
    color: __TEXT_A__;
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI";
}
QLabel { background: transparent; }
QPushButton { background: transparent; border: none; }
QToolTip {
    background: __POPOVER__;
    color: __TEXT__;
    border: 1px solid __LINE__;
    padding: 4px 7px;
    border-radius: 6px;
}

#panel {
    background: __PANEL__;
    border: 1px solid __LINE__;
    border-radius: 14px;
}
#scrollArea, #listContainer { background: transparent; border: none; }
#scrollArea QWidget { background: transparent; }

QScrollBar:vertical {
    width: 5px;
    background: transparent;
    margin: 2px 0;
}
QScrollBar::handle:vertical {
    background: __TRACK__;
    border-radius: 2px;
    min-height: 26px;
}
QScrollBar::handle:vertical:hover { background: __ACCENT_12__; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
    background: transparent;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
}

#addBar {
    background: __PANEL__;
    border: 1px solid __LINE__;
    border-radius: 12px;
}
#addBar[focused="true"] {
    border: 1px solid __ACCENT_50__;
    background: __HOVER__;
}
#addInput {
    background: transparent;
    border: none;
    color: __TEXT__;
    font-size: 12.5px;
}

#searchBar {
    background: __POPOVER__;
    border: 1px solid __ACCENT_50__;
    border-radius: 10px;
}
#searchInput {
    background: transparent;
    border: none;
    color: __TEXT__;
    font-size: 12.5px;
}

#popover {
    background: __POPOVER__;
    border: 1px solid __LINE__;
    border-radius: 14px;
}
#popTitle { color: __MUTED__; font-size: 11px; }
#popValue { color: __ACCENT_TEXT__; font-size: 11px; font-weight: 600; }
#popDivider { background: __LINE__; border: none; }
#settingLabel { color: __MUTED__; font-size: 11px; }
#settingHint { color: __FAINT__; font-size: 10px; }

QSlider {
    min-height: 18px;
    max-height: 18px;
}
QSlider::groove:horizontal {
    height: 4px;
    background: __TRACK__;
    border-radius: 2px;
}
QSlider::sub-page:horizontal { background: __ACCENT__; border-radius: 2px; }
QSlider::add-page:horizontal { background: __TRACK__; border-radius: 2px; }
QSlider::handle:horizontal {
    width: 12px;
    height: 12px;
    margin: -4px 0;
    border-radius: 6px;
    background: __ACCENT__;
}
QSlider::handle:horizontal:hover { background: __ACCENT_TEXT__; }

QMenu {
    background: __POPOVER__;
    color: __TEXT__;
    border: 1px solid __LINE__;
    padding: 5px;
    border-radius: 10px;
}
QMenu::item { padding: 6px 24px 6px 12px; border-radius: 6px; }
QMenu::item:selected { background: __ACCENT_12__; color: __TEXT__; }
QMenu::separator { height: 1px; background: __LINE__; margin: 4px 8px; }

#monthTitle { font-size: 12.5px; font-weight: 600; border-radius: 8px; }
#monthTitle:hover { background: __HOVER__; }
#todayBtn { color: __ACCENT_TEXT__; font-size: 11px; border-radius: 6px; }
#todayBtn:hover { background: __ACCENT_12__; }
#weekday { color: __FAINT__; font-size: 10px; }
#monthStat { color: __MUTED__; font-size: 11px; }
#heroDate { font-size: 22px; font-weight: 600; }
#heroWeek { color: __MUTED__; font-size: 11px; }
#heroStreak { color: __ACCENT_TEXT__; font-size: 10.5px; }
#countLabel { color: __MUTED__; font-size: 10px; }
#emptyTitle { color: __MUTED__; font-size: 12.5px; }
#emptyHint { color: __FAINT__; font-size: 11px; }
#carryHint { color: __MUTED__; font-size: 11px; }
#carryBtn { color: __ACCENT_TEXT__; font-size: 11px; }
#carryBtn:hover { background: __ACCENT_12__; }
#searchEmpty { color: __FAINT__; font-size: 11.5px; }
#previewLabel { color: __ACCENT_TEXT__; font-size: 11px; }
#footerStat { color: __FAINT__; font-size: 10.5px; }
#modeBtn {
    color: __MUTED__;
    font-size: 10.5px;
    border-radius: 7px;
    padding: 4px 9px;
    background: __PANEL__;
}
#modeBtn[active="true"] { color: __ACCENT_TEXT__; background: __ACCENT_12__; font-weight: 600; }
#modeBtn:hover { background: __HOVER__; }
"""
