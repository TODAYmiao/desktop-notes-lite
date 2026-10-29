"""界面冒烟测试：不需要真人点，只验证「构建 → 渲染 → 交互 → 落盘」不崩。"""

from __future__ import annotations

import tempfile
import unittest
from datetime import date, timedelta

from tests import *  # noqa: F401,F403

from PySide6.QtWidgets import QApplication

from app.store import Store
from app.theme import Theme
from app.window import NotesWindow

APP = QApplication.instance() or QApplication([])


class WindowSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = Store(directory=self._tmp.name)
        self.theme = Theme()
        self.window = NotesWindow(self.store, self.theme)
        self.window.show()
        APP.processEvents()

    def tearDown(self) -> None:
        self.window.hotkey.unregister()
        self.window.close()
        self.window.deleteLater()
        APP.processEvents()
        self._tmp.cleanup()

    # ---------- 结构 ----------

    def test_structure(self) -> None:
        self.assertEqual(len(self.window.week_cells), 7)
        self.assertEqual(len(self.window.month_cells), 42)
        self.assertGreaterEqual(self.window.minimumWidth(), 360)
        self.assertGreaterEqual(self.window.minimumHeight(), 520)

    def test_grab_returns_pixels(self) -> None:
        pixmap = self.window.grab()
        self.assertFalse(pixmap.isNull())
        self.assertGreater(pixmap.width(), 300)

    # ---------- 添加 / 勾选 / 删除 / 撤销 ----------

    def test_add_from_input_parses_date(self) -> None:
        self.window.select_date(date.today())
        self.window.input.setText("明天 @15:00 交报告 !!")
        self.window.add_from_input()
        APP.processEvents()

        self.assertEqual(self.window.input.text(), "")
        created = self.store.peek_tasks(date.today() + timedelta(days=1))
        self.assertTrue(created)
        task = created[-1]
        self.assertEqual(task["text"], "交报告")
        self.assertEqual(task["remindAt"], "15:00")
        self.assertEqual(task["priority"], 2)

    def test_add_plain_text_goes_to_selected_day(self) -> None:
        self.window.select_date(date.today())
        self.window.input.setText("随手记一条")
        self.window.add_from_input()
        APP.processEvents()
        self.assertEqual(
            [t["text"] for t in self.store.peek_tasks(date.today())], ["随手记一条"]
        )

    def test_preview_follows_input(self) -> None:
        self.window.on_input_changed("明天 @9:30 复盘 !!")
        APP.processEvents()
        self.assertTrue(self.window.preview.isVisibleTo(self.window))
        text = self.window.preview.text()
        self.assertIn("明天", text)
        self.assertIn("09:30", text)
        self.window.on_input_changed("")
        APP.processEvents()
        self.assertFalse(self.window.preview.isVisibleTo(self.window))

    def test_toggle_and_delete_then_undo(self) -> None:
        day = self.window.selected
        task = self.store.add_task(day, "勾掉我")
        self.window.render_all()
        APP.processEvents()
        self.assertIn(task["id"], self.window.rows)

        self.window.toggle_task(task["id"], True)
        APP.processEvents()
        self.assertTrue(self.store.peek_tasks(day)[0]["done"])

        self.window.delete_task(task["id"])
        APP.processEvents()
        self.assertEqual(self.store.peek_tasks(day), [])

        self.window.undo()
        APP.processEvents()
        self.assertEqual([t["text"] for t in self.store.peek_tasks(day)], ["勾掉我"])
        # 删除前的勾选状态一并恢复，撤销不应该顺手把「已完成」抹掉
        self.assertTrue(self.store.peek_tasks(day)[0]["done"])

    def test_edit_task(self) -> None:
        day = self.window.selected
        task = self.store.add_task(day, "旧标题")
        self.window.render_all()
        self.window.edit_task(task["id"], "新标题")
        APP.processEvents()
        self.assertEqual(self.store.peek_tasks(day)[0]["text"], "新标题")
        self.window.undo()
        APP.processEvents()
        self.assertEqual(self.store.peek_tasks(day)[0]["text"], "旧标题")

    # ---------- 日历 ----------

    def test_select_date_and_shifts(self) -> None:
        target = date(2026, 11, 3)
        self.window.select_date(target)
        APP.processEvents()
        self.assertEqual(self.window.selected, target)
        self.assertEqual(self.window.week_anchor, target - timedelta(days=target.weekday()))

        before = self.window.week_anchor
        self.window.shift_period(1)
        APP.processEvents()
        self.assertGreater(self.window.week_anchor, before)

        self.window.go_today()
        APP.processEvents()
        self.assertEqual(self.window.selected, date.today())

    def test_toggle_view(self) -> None:
        self.assertEqual(self.window.view_mode, "week")
        self.window.toggle_view()
        APP.processEvents()
        self.assertEqual(self.window.view_mode, "month")
        self.assertFalse(self.window.week_strip.isVisibleTo(self.window))
        self.window.toggle_view()
        APP.processEvents()
        self.assertEqual(self.window.view_mode, "week")

    # ---------- 主题 / 设置 ----------

    def test_theme_modes_and_accent(self) -> None:
        self.window.set_theme_mode("light")
        APP.processEvents()
        self.assertEqual(self.window.theme.mode, "light")
        self.window.set_accent("#63d6c0")
        APP.processEvents()
        self.assertEqual(self.window.theme.accent_hex, "#63d6c0")
        self.assertEqual(self.store.settings["accent"], "#63d6c0")
        self.window.set_theme_mode("dark")
        APP.processEvents()
        self.assertEqual(self.window.theme.mode, "dark")

    def test_settings_popover_and_opacity(self) -> None:
        self.window.toggle_settings()
        APP.processEvents()
        self.assertTrue(self.window.popover.isVisibleTo(self.window))
        self.assertIsNotNone(self.window.popover.content)

        self.window.set_opacity(55)
        APP.processEvents()
        self.assertEqual(self.store.settings["opacity"], 55)

        self.window.toggle_settings()
        APP.processEvents()
        self.assertFalse(self.window.popover.isVisibleTo(self.window))

    # ---------- 搜索 ----------

    def test_search_finds_across_days(self) -> None:
        today = date.today()
        self.store.add_task(today, "买咖啡豆")
        self.store.add_task(today.replace(day=1), "买牛奶")
        self.window.open_search()
        APP.processEvents()
        self.assertTrue(self.window.search_bar.isVisibleTo(self.window))

        self.window.search_input.setText("买")
        self.window.on_search_changed("买")
        APP.processEvents()
        self.assertGreaterEqual(len(self.window.rows), 2)

        self.window.search_input.setText("绝不存在的词")
        self.window.on_search_changed("绝不存在的词")
        APP.processEvents()
        self.assertEqual(len(self.window.rows), 0)

        self.window.close_search()
        APP.processEvents()
        self.assertFalse(self.window.search_bar.isVisibleTo(self.window))

    # ---------- 顺延 ----------

    def test_carry_over_button(self) -> None:
        today = date.today()
        yesterday = today - timedelta(days=1)
        self.store.add_task(yesterday, "昨天没做完")
        self.window.select_date(today)
        self.window.render_all()
        APP.processEvents()
        self.assertTrue(self.window.carry_row.isVisibleTo(self.window))

        self.window.carry_over()
        APP.processEvents()
        self.assertEqual(self.store.peek_tasks(yesterday), [])
        moved = self.store.peek_tasks(today)
        self.assertEqual([t["text"] for t in moved], ["昨天没做完"])
        self.assertEqual(moved[0]["rolledFrom"], yesterday.isoformat())

        self.window.undo()
        APP.processEvents()
        self.assertEqual([t["text"] for t in self.store.peek_tasks(yesterday)], ["昨天没做完"])

    # ---------- 持久化 ----------

    def test_geometry_saved(self) -> None:
        self.window._save_geometry()
        state = self.store.load_window_state()
        self.assertIsInstance(state["width"], int)
        self.assertGreater(state["width"], 300)


if __name__ == "__main__":
    unittest.main()
