"""数据层测试：迁移、sanitize、原子写、顺延、重复任务、统计。"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from tests import *  # noqa: F401,F403
from app.store import SCHEMA_VERSION, Store, atomic_write


class StoreTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name
        self.store = Store(directory=self.dir)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # ---------- 基础 ----------

    def test_defaults(self) -> None:
        self.assertEqual(self.store.data["version"], SCHEMA_VERSION)
        self.assertEqual(self.store.settings["opacity"], 80)
        self.assertEqual(self.store.settings["theme"], "dark")
        self.assertTrue(self.store.settings["alwaysOnTop"])
        self.assertEqual(self.store.tasks_for(date(2026, 10, 30)), [])

    def test_add_and_complete(self) -> None:
        day = date(2026, 10, 30)
        task = self.store.add_task(day, "  写   测试  ", priority=1, remind_at="09:05")
        self.assertIsNotNone(task)
        self.assertEqual(task["text"], "写 测试")
        self.assertEqual(task["priority"], 1)
        self.assertEqual(task["remindAt"], "09:05")
        self.assertFalse(task["done"])
        # 格式不规范的时间一律按「没有提醒」处理，而不是存进去炸掉渲染
        self.assertIsNone(self.store.add_task(day, "不合格时间", remind_at="9:5")["remindAt"])

        self.store.set_done(day, task["id"], True)
        stored = self.store.peek_tasks(day)[0]
        self.assertTrue(stored["done"])
        self.assertIsNotNone(stored["doneAt"])

        self.store.set_done(day, task["id"], False)
        self.assertIsNone(self.store.peek_tasks(day)[0]["doneAt"])

    def test_add_empty_is_rejected(self) -> None:
        self.assertIsNone(self.store.add_task(date(2026, 10, 30), "   "))

    def test_delete_and_restore_order(self) -> None:
        day = date(2026, 10, 30)
        first = self.store.add_task(day, "第一条")
        second = self.store.add_task(day, "第二条")
        removed = self.store.delete_task(day, first["id"])
        self.assertIsNotNone(removed)
        index, task = removed
        self.assertEqual(index, 0)
        self.assertEqual(task["text"], "第一条")
        self.assertEqual([t["text"] for t in self.store.peek_tasks(day)], ["第二条"])

        self.store.insert_task(day, index, task)
        self.assertEqual(
            [t["text"] for t in self.store.peek_tasks(day)], ["第一条", "第二条"]
        )
        self.store.delete_task(day, second["id"])
        self.store.delete_task(day, first["id"])
        self.assertNotIn(day.isoformat(), self.store.data["tasks"])

    def test_update_task_clamps(self) -> None:
        day = date(2026, 10, 30)
        task = self.store.add_task(day, "原标题")
        self.store.update_task(day, task["id"], text="x" * 500)
        self.assertEqual(len(self.store.peek_tasks(day)[0]["text"]), 200)
        self.store.update_task(day, task["id"], priority=9)
        self.assertEqual(self.store.peek_tasks(day)[0]["priority"], 0)
        self.store.update_task(day, task["id"], remindAt="25:99")
        self.assertIsNone(self.store.peek_tasks(day)[0]["remindAt"])

    # ---------- 顺延 ----------

    def test_carry_over_moves_only_pending(self) -> None:
        source = date(2026, 10, 29)
        target = date(2026, 10, 30)
        done = self.store.add_task(source, "已经做完")
        self.store.set_done(source, done["id"], True)
        self.store.add_task(source, "没做完 A")
        self.store.add_task(source, "没做完 B")

        moved = self.store.carry_over(source, target)
        self.assertEqual(len(moved), 2)
        self.assertTrue(all(task["rolledFrom"] == source.isoformat() for task in moved))
        self.assertEqual(len(self.store.peek_tasks(source)), 1)  # 那条已完成的留着
        self.assertEqual(len(self.store.peek_tasks(target)), 2)

        self.store.undo_carry(moved, source, target)
        self.assertEqual(len(self.store.peek_tasks(target)), 0)
        self.assertEqual(len(self.store.peek_tasks(source)), 3)
        self.assertTrue(all(task["rolledFrom"] is None for task in self.store.peek_tasks(source)))

    # ---------- 统计 ----------

    def test_month_stats_and_heatmap(self) -> None:
        day = date(2026, 10, 30)
        a = self.store.add_task(day, "A")
        self.store.add_task(day, "B")
        self.store.add_task(date(2026, 11, 2), "C")  # 下个月，不该计入 10 月
        self.store.set_done(day, a["id"], True)

        total, done = self.store.month_stats(2026, 10)
        self.assertEqual((total, done), (2, 1))

        heat = self.store.heatmap(days=7, end=day)
        self.assertEqual(len(heat), 7)
        self.assertEqual(heat[-1]["date"], day)
        self.assertEqual((heat[-1]["total"], heat[-1]["done"]), (2, 1))

    def test_streak_counts_full_clear_days(self) -> None:
        end = date(2026, 10, 30)
        for offset in range(1, 4):  # 前三天全部完成
            day = end - timedelta(days=offset)
            task = self.store.add_task(day, f"day-{offset}")
            self.store.set_done(day, task["id"], True)
        partial = end - timedelta(days=4)  # 第四天有未完成 → 到此为止
        self.store.add_task(partial, "没做完")

        self.assertEqual(self.store.streak(end=end), 3)

    # ---------- 重复任务 ----------

    def test_series_materializes_once(self) -> None:
        series = self.store.add_series("写日报", rule="weekdays")
        self.assertIsNotNone(series)
        # add_series 已经把 [-7, +28] 天展开过一遍，这里只补测「不会重复添加」
        days = [date(2026, 11, 2), date(2026, 11, 3), date(2026, 11, 7)]  # 周一、周二、周六
        self.store.materialize(days=days, series=series)
        self.assertEqual(len(self.store.peek_tasks(date(2026, 11, 2))), 1)
        self.assertEqual(len(self.store.peek_tasks(date(2026, 11, 3))), 1)
        self.assertEqual(self.store.peek_tasks(date(2026, 11, 7)), [])  # 周六不是工作日

        self.assertEqual(self.store.materialize(days=days, series=series), 0)  # 不重复添加

        self.store.set_series_active(series["id"], False)
        self.assertEqual(self.store.materialize(days=[date(2026, 11, 4)], series=series), 0)

    def test_delete_series_keeps_or_removes_tasks(self) -> None:
        series = self.store.add_series("喝水", rule="daily")
        day = date(2026, 11, 5)
        self.store.materialize(days=[day], series=series)
        self.assertEqual(len(self.store.peek_tasks(day)), 1)

        self.assertTrue(self.store.delete_series(series["id"], keep_existing=True))
        self.assertEqual(len(self.store.peek_tasks(day)), 1)  # 已生成的保留

        series2 = self.store.add_series("拉伸", rule="daily")
        self.store.materialize(days=[day], series=series2)
        self.assertEqual(len(self.store.peek_tasks(day)), 2)
        self.store.delete_series(series2["id"], keep_existing=False)
        self.assertEqual(len(self.store.peek_tasks(day)), 1)

    # ---------- 落盘 ----------

    def test_save_and_reload(self) -> None:
        day = date(2026, 10, 30)
        task = self.store.add_task(day, "持久化")
        self.store.settings["opacity"] = 66
        self.store.touch()
        self.store.save()

        self.assertFalse(Path(self.store.path).with_suffix(".json.tmp").exists())
        reloaded = Store(directory=self.dir)
        self.assertEqual(reloaded.peek_tasks(day)[0]["text"], "持久化")
        self.assertEqual(reloaded.settings["opacity"], 66)
        self.assertEqual(reloaded.peek_tasks(day)[0]["id"], task["id"])

    def test_v1_migration_backs_up(self) -> None:
        legacy = {
            "version": 1,
            "todos": {
                "2026-10-30": [
                    {"id": "abc123", "text": "旧任务", "done": True},
                    {"text": "   "},
                ]
            },
            "window": {"x": 10, "y": 20},
        }
        with open(os.path.join(self.dir, "notes.json"), "w", encoding="utf-8") as handle:
            json.dump(legacy, handle, ensure_ascii=False)

        store = Store(directory=self.dir)
        self.assertEqual(store.data["version"], 2)
        tasks = store.peek_tasks(date(2026, 10, 30))
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["text"], "旧任务")
        self.assertTrue(tasks[0]["done"])
        self.assertTrue(tasks[0]["doneAt"])
        self.assertEqual(tasks[0]["priority"], 0)
        self.assertTrue(os.path.exists(os.path.join(self.dir, "notes.v1.bak.json")))
        self.assertTrue(any("v1" in message for message in store.errors))

    def test_corrupt_file_is_quarantined(self) -> None:
        with open(os.path.join(self.dir, "notes.json"), "w", encoding="utf-8") as handle:
            handle.write("{ this is not json")
        store = Store(directory=self.dir)
        self.assertTrue(store.errors)
        self.assertEqual(store.data["version"], SCHEMA_VERSION)
        names = [name for name in os.listdir(self.dir) if name.startswith("notes.corrupt-")]
        self.assertEqual(len(names), 1)

    def test_illegal_keys_and_settings_are_sanitized(self) -> None:
        payload = {
            "version": 2,
            "tasks": {
                "not-a-date": [{"text": "脏数据"}],
                "2026-10-30": [{"text": "ok", "priority": 7, "remindAt": "8:0"}],
            },
            "settings": {"opacity": 5, "accent": "red", "theme": "neon", "hotkey": "  Ctrl+Alt+K  "},
        }
        with open(os.path.join(self.dir, "notes.json"), "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)

        store = Store(directory=self.dir)
        self.assertNotIn("not-a-date", store.data["tasks"])
        task = store.peek_tasks(date(2026, 10, 30))[0]
        self.assertEqual(task["priority"], 0)
        self.assertIsNone(task["remindAt"])
        self.assertEqual(store.settings["opacity"], 35)  # 下限夹住
        self.assertEqual(store.settings["accent"], "#ffb26b")  # 非法颜色回退
        self.assertEqual(store.settings["theme"], "dark")
        self.assertEqual(store.settings["hotkey"], "Ctrl+Alt+K")

    def test_atomic_write_replaces_content(self) -> None:
        path = os.path.join(self.dir, "atomic.json")
        atomic_write(path, {"a": 1})
        atomic_write(path, {"a": 2})
        with open(path, "r", encoding="utf-8") as handle:
            self.assertEqual(json.load(handle), {"a": 2})
        leftovers = [name for name in os.listdir(self.dir) if name.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    def test_export_markdown(self) -> None:
        day = date(2026, 10, 30)
        task = self.store.add_task(day, "导出我", priority=1, remind_at="09:30")
        self.store.set_done(day, task["id"], True)
        target = os.path.join(self.dir, "out.md")
        self.store.export_markdown(target)
        text = Path(target).read_text(encoding="utf-8")
        self.assertIn("## 2026-10-30", text)
        self.assertIn("- [x] 导出我", text)
        self.assertIn("⏰09:30", text)

    def test_window_state_roundtrip(self) -> None:
        self.store.save_window_state(120, 80, 440, 700)
        state = self.store.load_window_state()
        self.assertEqual((state["x"], state["y"]), (120, 80))
        self.assertEqual((state["width"], state["height"]), (440, 700))
        bad = os.path.join(self.dir, "window-state.json")
        Path(bad).write_text('{"width": 10}', encoding="utf-8")
        state = self.store.load_window_state()
        self.assertEqual(state["width"], 420)  # 越界回退到默认值


if __name__ == "__main__":
    unittest.main()
