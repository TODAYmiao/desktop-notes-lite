"""灵感板块：树状灵感，支持无限层级子灵感。"""

import html
import time
import uuid

from PySide6.QtCore import QEvent, QTimer, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .store import Store
from .theme import Theme
from .widgets import AddButton, EmptyState, IconButton, IdeaRow, repolish


class IdeasView(QWidget):
    def __init__(self, store: Store, theme: Theme, on_back):
        super().__init__()
        self.store = store
        self.theme = theme
        self.on_back = on_back
        self.path = []
        self._dirty = False

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._flush_save)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 0, 14, 14)
        outer.setSpacing(0)

        panel = QFrame()
        panel.setObjectName("panel")
        panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 10)
        layout.setSpacing(0)
        outer.addWidget(panel, 1)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)

        self.back_btn = IconButton(self.theme, "chevron_left", 24, "上一级")
        self.back_btn.clicked.connect(self.go_back)
        header.addWidget(self.back_btn, 0, Qt.AlignmentFlag.AlignTop)

        titles = QVBoxLayout()
        titles.setContentsMargins(0, 0, 0, 0)
        titles.setSpacing(3)

        self.title_label = QLabel("灵感")
        self.title_label.setObjectName("ideaTitle")
        titles.addWidget(self.title_label)

        self.breadcrumb = QLabel("")
        self.breadcrumb.setObjectName("ideaBreadcrumb")
        self.breadcrumb.setTextFormat(Qt.TextFormat.RichText)
        self.breadcrumb.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
        self.breadcrumb.setOpenExternalLinks(False)
        self.breadcrumb.linkActivated.connect(self._breadcrumb_clicked)
        titles.addWidget(self.breadcrumb)

        self.subtitle = QLabel("随手记下突然冒出的念头")
        self.subtitle.setObjectName("ideaSubtitle")
        titles.addWidget(self.subtitle)

        header.addLayout(titles)
        header.addStretch(1)

        self.count_label = QLabel("暂无")
        self.count_label.setObjectName("ideaCount")
        self.count_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop
        )
        header.addWidget(self.count_label, 0, Qt.AlignmentFlag.AlignTop)

        self.todo_btn = QPushButton("← 待办")
        self.todo_btn.setObjectName("ideaBack")
        self.todo_btn.setFlat(True)
        self.todo_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.todo_btn.clicked.connect(self.on_back)
        header.addWidget(self.todo_btn, 0, Qt.AlignmentFlag.AlignTop)

        layout.addLayout(header)
        layout.addSpacing(8)

        self.title_edit = QLineEdit()
        self.title_edit.setObjectName("ideaNodeTitle")
        self.title_edit.setPlaceholderText("灵感标题")
        self.title_edit.setMaxLength(500)
        self.title_edit.setFixedHeight(30)
        palette = self.title_edit.palette()
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(244, 239, 231, 77))
        self.title_edit.setPalette(palette)
        self.title_edit.textChanged.connect(self._on_title_changed)
        self.title_edit.editingFinished.connect(self._on_title_finished)
        layout.addWidget(self.title_edit)
        layout.addSpacing(8)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("scrollArea")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.viewport().setAutoFillBackground(False)

        self.list_widget = QWidget()
        self.list_widget.setObjectName("listContainer")
        self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.setContentsMargins(0, 4, 0, 6)
        self.list_layout.setSpacing(6)
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

        self.input = QLineEdit()
        self.input.setObjectName("addInput")
        self.input.setPlaceholderText("记下一个灵感，回车保存")
        self.input.setMaxLength(500)
        palette = self.input.palette()
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(244, 239, 231, 77))
        self.input.setPalette(palette)
        self.input.returnPressed.connect(self.add_idea)
        self.input.installEventFilter(self)

        self.add_btn = AddButton(self.theme)
        self.add_btn.clicked.connect(self.add_idea)

        bar_layout.addWidget(self.input, 1)
        bar_layout.addWidget(self.add_btn)
        layout.addWidget(self.add_bar)

        self.title_edit.returnPressed.connect(self.input.setFocus)
        self.render()

    # ---------- 数据与导航 ----------

    def _current_items(self) -> list:
        if self.path:
            return self.path[-1].get("children", []) or []
        return self.store.ideas

    def _sorted_items(self) -> list:
        return sorted(
            self._current_items(),
            key=lambda item: float(item.get("createdAt") or 0),
            reverse=True,
        )

    def _short_name(self, text: str) -> str:
        text = (text or "未命名灵感").strip()
        return text if len(text) <= 10 else text[:9] + "…"

    def _breadcrumb_html(self) -> str:
        entries = [(-1, "灵感")]
        entries += [(index, node.get("text", "")) for index, node in enumerate(self.path)]

        if len(entries) > 4:
            entries = [entries[0], (None, "…")] + entries[-2:]

        last_index = len(self.path) - 1
        parts = []
        for index, text in entries:
            name = html.escape(self._short_name(text))
            if index is None:
                parts.append('<span style="color:rgba(244,239,231,90);">…</span>')
            elif index == last_index:
                parts.append(f'<span style="color:#f4efe7;font-weight:600;">{name}</span>')
            else:
                parts.append(
                    f'<a href="{index}" style="color:{self.theme.accent_text_hex};'
                    f'text-decoration:none;">{name}</a>'
                )
        return ' <span style="color:rgba(244,239,231,90);">›</span> '.join(parts)

    def _sync_header(self) -> None:
        items = self._current_items()
        if self.path:
            self.back_btn.show()
            self.title_label.hide()
            self.breadcrumb.show()
            self.breadcrumb.setText(self._breadcrumb_html())
            self.breadcrumb.setToolTip(
                " / ".join(["灵感"] + [node.get("text", "") for node in self.path])
            )
            self.subtitle.setText("双击子灵感继续深入")
            self.count_label.setText(f"{len(items)} 条子灵感" if items else "暂无子灵感")
            self.title_edit.show()
            self.title_edit.blockSignals(True)
            self.title_edit.setText(self.path[-1].get("text", ""))
            self.title_edit.setCursorPosition(0)
            self.title_edit.blockSignals(False)
            self.input.setPlaceholderText("添加子灵感，回车保存")
        else:
            self.back_btn.hide()
            self.title_label.show()
            self.breadcrumb.hide()
            self.subtitle.setText("随手记下突然冒出的念头")
            self.count_label.setText(f"{len(items)} 条" if items else "暂无")
            self.title_edit.hide()
            self.input.setPlaceholderText("记下一个灵感，回车保存")

    def render(self, scroll_to_top: bool = False) -> None:
        scrollbar = self.scroll.verticalScrollBar()
        previous = scrollbar.value()

        while self.list_layout.count():
            entry = self.list_layout.takeAt(0)
            widget = entry.widget()
            if widget is not None:
                widget.deleteLater()

        self._sync_header()
        items = self._sorted_items()

        if not items:
            empty = (
                EmptyState("还没有子灵感", "在下方继续拆解这个想法")
                if self.path
                else EmptyState("还没有灵感记录", "在下方写下刚刚想到的点子")
            )
            self.list_layout.addWidget(empty, 1)
        else:
            for idea in items:
                row = IdeaRow(idea, self.theme)
                row.opened.connect(self.open_idea)
                row.deleted.connect(self.delete_idea)
                self.list_layout.addWidget(row)
            self.list_layout.addStretch(1)

        target = 0 if scroll_to_top else previous
        QTimer.singleShot(0, lambda: scrollbar.setValue(target))

    def open_idea(self, node) -> None:
        if not isinstance(node, dict):
            return
        if self.path and self.path[-1] is node:
            return
        self._flush_title()
        self.path.append(node)
        self.input.clear()
        self.render(scroll_to_top=True)
        self.input.setFocus()

    def go_back(self) -> None:
        self._flush_title()
        if self.path:
            self.path.pop()
        self.input.clear()
        self.render(scroll_to_top=True)
        self.input.setFocus()

    def go_root(self) -> None:
        self._flush_title()
        self.path.clear()
        self.input.clear()
        self.render(scroll_to_top=True)
        self.input.setFocus()

    def reset_to_root(self) -> None:
        self.flush()
        self.path.clear()
        self.input.clear()
        self.render(scroll_to_top=True)

    def _breadcrumb_clicked(self, href: str) -> None:
        try:
            index = int(href)
        except (TypeError, ValueError):
            return
        if index == -1:
            self.go_root()
            return
        if 0 <= index < len(self.path):
            self._flush_title()
            self.path = self.path[: index + 1]
            self.input.clear()
            self.render(scroll_to_top=True)
            self.input.setFocus()

    # ---------- 新增、删除、标题 ----------

    def add_idea(self) -> None:
        text = self.input.text().strip()
        if not text:
            return
        self._flush_title()
        node = {
            "id": str(uuid.uuid4()),
            "text": text[:500],
            "createdAt": int(time.time() * 1000),
        }
        if self.path:
            self.path[-1].setdefault("children", []).append(node)
        else:
            self.store.ideas.insert(0, node)
        self.input.clear()
        self.store.save()
        self.render(scroll_to_top=True)
        self.input.setFocus()

    def delete_idea(self, idea_id: str) -> None:
        self._flush_title()
        if self.path:
            node = self.path[-1]
            children = node.get("children") or []
            node["children"] = [idea for idea in children if idea.get("id") != idea_id]
            if not node["children"]:
                node.pop("children", None)
        else:
            self.store.data["ideas"] = [
                idea for idea in self.store.ideas if idea.get("id") != idea_id
            ]
        self.store.save()
        self.render()

    def _on_title_changed(self, text: str) -> None:
        if not self.path:
            return
        text = text.strip()
        if not text:
            return
        self.path[-1]["text"] = text[:500]
        self._dirty = True
        self._save_timer.start(400)
        self.breadcrumb.setText(self._breadcrumb_html())

    def _on_title_finished(self) -> None:
        if not self.path:
            return
        if not self.title_edit.text().strip():
            self.title_edit.blockSignals(True)
            self.title_edit.setText(self.path[-1].get("text", ""))
            self.title_edit.blockSignals(False)
            return
        self._flush_title()

    def _flush_title(self) -> None:
        if not self.path:
            self._save_timer.stop()
            return
        text = self.title_edit.text().strip()
        if text:
            self.path[-1]["text"] = text[:500]
        self._save_timer.stop()
        if self._dirty:
            self.store.save()
            self._dirty = False

    def _flush_save(self) -> None:
        self._save_timer.stop()
        if self._dirty:
            self.store.save()
            self._dirty = False

    def flush(self) -> None:
        self._flush_title()

    def refresh_theme(self) -> None:
        if self.path:
            self.breadcrumb.setText(self._breadcrumb_html())
        for row in self.findChildren(IdeaRow):
            row.update()

    def focus_input(self) -> None:
        self.input.setFocus()

    def eventFilter(self, watched, event) -> bool:
        if watched is self.input:
            if event.type() == QEvent.Type.FocusIn:
                self.add_bar.setProperty("focused", "true")
                repolish(self.add_bar)
            elif event.type() == QEvent.Type.FocusOut:
                self.add_bar.setProperty("focused", "false")
                repolish(self.add_bar)
        return super().eventFilter(watched, event)
