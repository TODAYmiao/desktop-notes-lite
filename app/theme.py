"""配色、明暗对比和全局 QSS。"""

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
TEXT_HEX = "#f4efe7"


def normalize_hex(value) -> str:
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
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {max(0, min(255, alpha))})"


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


@dataclass
class Theme:
    accent_hex: str = DEFAULT_ACCENT
    accent: QColor = field(init=False)
    ink: QColor = field(init=False)
    ink_hex: str = field(init=False)
    accent_text_hex: str = field(init=False)

    def __post_init__(self) -> None:
        self.set_accent(self.accent_hex)

    def set_accent(self, value: str) -> None:
        self.accent_hex = normalize_hex(value)
        self.accent = QColor(self.accent_hex)
        self.ink = QColor("#241a10") if luminance(self.accent) > 0.35 else QColor("#ffffff")
        self.ink_hex = self.ink.name()
        self.accent_text_hex = mix_hex(self.accent_hex, TEXT_HEX, 0.22)

    @property
    def text(self) -> QColor:
        return QColor(244, 239, 231)

    @property
    def muted(self) -> QColor:
        return QColor(244, 239, 231, 107)

    @property
    def faint(self) -> QColor:
        return QColor(244, 239, 231, 82)

    @property
    def line(self) -> QColor:
        return QColor(255, 255, 255, 23)

    def soft(self) -> QColor:
        return with_alpha(self.accent, 36)

    def stylesheet(self) -> str:
        return (
            BASE_QSS.replace("__TEXT__", TEXT_HEX)
            .replace("__LINE__", rgba(QColor(255, 255, 255), 23))
            .replace("__MUTED__", rgba(QColor(244, 239, 231), 107))
            .replace("__ACCENT_TEXT__", self.accent_text_hex)
            .replace("__ACCENT_50__", rgba(self.accent, 128))
            .replace("__ACCENT_10__", rgba(self.accent, 26))
            .replace("__ACCENT__", self.accent_hex)
        )


BASE_QSS = """
QWidget {
    color: __TEXT__;
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI";
}
QLabel { background: transparent; }
QPushButton { background: transparent; border: none; }

#panel {
    background: rgba(255, 255, 255, 8);
    border: 1px solid __LINE__;
    border-radius: 14px;
}
#monthCard {
    background: rgba(255, 255, 255, 9);
    border: 1px solid __LINE__;
    border-radius: 12px;
}
#scrollArea, #listContainer { background: transparent; border: none; }
#scrollArea QWidget { background: transparent; }

QScrollBar:vertical {
    width: 4px;
    background: transparent;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: rgba(255, 255, 255, 36);
    border-radius: 2px;
    min-height: 24px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
    background: transparent;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
}

#addBar {
    background: rgba(255, 255, 255, 13);
    border: 1px solid __LINE__;
    border-radius: 10px;
}
#addBar[focused="true"] {
    border: 1px solid __ACCENT_50__;
    background: rgba(255, 255, 255, 17);
}
#addInput {
    background: transparent;
    border: none;
    color: __TEXT__;
    font-size: 12px;
}

#popover {
    background: #202027;
    border: 1px solid rgba(255, 255, 255, 31);
    border-radius: 12px;
}
#popTitle { color: __MUTED__; font-size: 11px; }
#popValue { color: __ACCENT_TEXT__; font-size: 11px; font-weight: 600; }
#popDivider { background: __LINE__; border: none; }
#settingLabel { color: __MUTED__; font-size: 11px; }

QSlider::groove:horizontal {
    height: 4px;
    background: rgba(255, 255, 255, 18);
    border-radius: 2px;
}
QSlider::sub-page:horizontal { background: __ACCENT__; border-radius: 2px; }
QSlider::add-page:horizontal { background: rgba(255, 255, 255, 18); border-radius: 2px; }
QSlider::handle:horizontal {
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
    background: __ACCENT__;
}

#monthTitle { font-size: 13px; font-weight: 600; border-radius: 8px; }
#monthTitle:hover { background: rgba(255, 255, 255, 16); }
#todayBtn { color: __ACCENT_TEXT__; font-size: 11px; border-radius: 6px; }
#todayBtn:hover { background: __ACCENT_10__; }
#weekday { color: rgba(244, 239, 231, 82); font-size: 10px; }
#monthTitleSmall { color: rgba(244, 239, 231, 87); font-size: 10px; }
#monthStat { color: rgba(244, 239, 231, 158); font-size: 11px; }
#selDate { font-size: 16px; font-weight: 600; }
#selWeek { color: __MUTED__; font-size: 10px; }
#countLabel { color: __MUTED__; font-size: 10px; }
#emptyTitle { color: rgba(244, 239, 231, 133); font-size: 12px; }
#emptyHint { color: rgba(244, 239, 231, 77); font-size: 11px; }

QMenu {
    background: #202027;
    color: __TEXT__;
    border: 1px solid rgba(255, 255, 255, 31);
    padding: 4px;
}
QMenu::item { padding: 6px 22px 6px 12px; border-radius: 6px; }
QMenu::item:selected { background: rgba(255, 255, 255, 24); }
QMenu::separator { height: 1px; background: __LINE__; margin: 4px 8px; }

QToolTip {
    background: #202027;
    color: __TEXT__;
    border: 1px solid rgba(255, 255, 255, 31);
    padding: 4px 6px;
    border-radius: 6px;
}
"""
