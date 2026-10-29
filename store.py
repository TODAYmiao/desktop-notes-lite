"""数据层：schema v2、迁移备份、原子写入与重复任务物化。

相对原版的改动：

* 文件格式升到 v2，新增 priority / remindAt / rolledFrom / seriesId 字段和
  `series`（重复规则）。v1 文件先备份成 `notes.v1.bak.json` 再迁移。
* 每次落盘都是「写 tmp → flush → fsync → os.replace」，不会出现半截 JSON。
* 读取到坏文件时不再静默丢弃：原文件改名成 `notes.corrupt-<时间戳>.json` 留档，
  并在 `Store.errors` 里记录原因，方便排查。
* 时间一律用本地日历日（date），跨零点后 `today` 由窗口定时器推动。
"""

from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from datetime import date, datetime, timedelta

SCHEMA_VERSION = 2
DEFAULT_SETTINGS = {
    "opacity": 80,
    "alwaysOnTop": True,
    "accent": "#ffb26b",
    "theme": "dark",
    "autoFade": False,
    "snap": True,
    "hotkey": "Ctrl+Alt+N",
    "autostart": False,
    "view": "week",
}
MAX_TEXT = 200
WINDOW_STATE_DEFAULT = {"x": None, "y": None, "width": 420, "height": 660}


def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _parse_day(value) -> date | None:
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def _valid_remind(value) -> str | None:
    if not isinstance(value, str) or len(value) != 5 or value[2] != ":":
        return None
    try:
        hour = int(value[:2])
        minute = int(value[3:])
    except ValueError:
        return None
    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return f"{hour:02d}:{minute:02d}"
    return None


def make_task(
    text: str,
    priority: int = 0,
    remind_at: str | None = None,
    series_id: str | None = None,
    rolled_from: str | None = None,
) -> dict:
    return {
        "id": uuid.uuid4().hex[:12],
        "text": (text or "").strip()[:MAX_TEXT],
        "done": False,
        "createdAt": _now_iso(),
        "doneAt": None,
        "priority": int(priority) if priority in (0, 1, 2) else 0,
        "remindAt": _valid_remind(remind_at),
        "rolledFrom": rolled_from,
        "seriesId": series_id,
    }


def sanitize_task(raw: dict) -> dict | None:
    if not isinstance(raw, dict):
        return None
    text = raw.get("text")
    if not isinstance(text, str):
        return None
    text = " ".join(text.split()).strip()
    if not text:
        return None
    task = {
        "id": str(raw.get("id") or uuid.uuid4().hex[:12])[:64],
        "text": text[:MAX_TEXT],
        "done": bool(raw.get("done")),
        "createdAt": raw.get("createdAt") if isinstance(raw.get("createdAt"), str) else None,
        "doneAt": raw.get("doneAt") if isinstance(raw.get("doneAt"), str) else None,
        "priority": raw.get("priority") if raw.get("priority") in (0, 1, 2) else 0,
        "remindAt": _valid_remind(raw.get("remindAt")),
        "rolledFrom": raw.get("rolledFrom") if isinstance(raw.get("rolledFrom"), str) else None,
        "seriesId": raw.get("seriesId") if isinstance(raw.get("seriesId"), str) else None,
    }
    if task["done"] and not task["doneAt"]:
        task["doneAt"] = _now_iso()
    if not task["done"]:
        task["doneAt"] = None
    return task


def sanitize_series(raw: dict) -> dict | None:
    if not isinstance(raw, dict):
        return None
    text = raw.get("text")
    if not isinstance(text, str) or not text.strip():
        return None
    rule = raw.get("rule")
    if rule not in ("daily", "weekdays", "weekly", "monthly"):
        rule = "daily"
    weekdays: list[int] = []
    for item in raw.get("weekdays") or []:
        if isinstance(item, int) and 0 <= item <= 6 and item not in weekdays:
            weekdays.append(item)
    if rule == "daily":
        weekdays = list(range(7))
    elif rule == "weekdays":
        weekdays = [0, 1, 2, 3, 4]
    elif rule == "weekly" and not weekdays:
        weekdays = [0]
    day_of_month = raw.get("dayOfMonth")
    if not isinstance(day_of_month, int) or not (1 <= day_of_month <= 28):
        day_of_month = 1
    return {
        "id": str(raw.get("id") or uuid.uuid4().hex[:12])[:64],
        "text": " ".join(text.split()).strip()[:MAX_TEXT],
        "priority": raw.get("priority") if raw.get("priority") in (0, 1, 2) else 0,
        "remindAt": _valid_remind(raw.get("remindAt")),
        "rule": rule,
        "weekdays": sorted(weekdays),
        "dayOfMonth": day_of_month,
        "createdAt": raw.get("createdAt") if isinstance(raw.get("createdAt"), str) else _now_iso(),
        "active": bool(raw.get("active", True)),
    }


def series_matches(series: dict, day: date) -> bool:
    rule = series.get("rule")
    if rule == "daily":
        return True
    if rule == "weekdays":
        return day.weekday() < 5
    if rule == "weekly":
        return day.weekday() in (series.get("weekdays") or [])
    if rule == "monthly":
        return day.day == series.get("dayOfMonth")
    return False


def app_data_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, "DesktopNotesLite")
    os.makedirs(path, exist_ok=True)
    return path


def atomic_write(path: str, payload: dict) -> None:
    """tmp + flush + fsync + replace，进程被强杀也不会写坏文件。"""
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=1)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


class Store:
    def __init__(self, directory: str | None = None) -> None:
        self.directory = directory or app_data_dir()
        os.makedirs(self.directory, exist_ok=True)
        self.path = os.path.join(self.directory, "notes.json")
        self.state_path = os.path.join(self.directory, "window-state.json")
        self.errors: list[str] = []
        self.dirty = False
        self._backed_up = False
        self.data = self._load()
        self._materialize_all()
        # 迁移/修复过就立刻落盘，否则下次启动会再迁移一遍，文件也一直是旧格式
        if self.dirty:
            self.save()

    # ---------- 载入 / 迁移 ----------

    def _default_data(self) -> dict:
        return {
            "version": SCHEMA_VERSION,
            "tasks": {},
            "series": [],
            "settings": dict(DEFAULT_SETTINGS),
        }

    def _load(self) -> dict:
        if not os.path.exists(self.path):
            return self._default_data()
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            self._quarantine(f"读取失败：{exc}")
            return self._default_data()
        if not isinstance(raw, dict):
            self._quarantine("顶层不是对象")
            return self._default_data()
        return self._normalize(raw)

    def _quarantine(self, reason: str) -> None:
        self.errors.append(f"notes.json {reason}")
        suffix = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = os.path.join(self.directory, f"notes.corrupt-{suffix}.json")
        try:
            shutil.move(self.path, target)
            self.errors.append(f"已留档为 {os.path.basename(target)}")
        except OSError as exc:
            self.errors.append(f"留档失败：{exc}")

    def _normalize(self, raw: dict) -> dict:
        version = raw.get("version")
        data = self._default_data()
        settings = raw.get("settings") if isinstance(raw.get("settings"), dict) else {}
        for key, value in DEFAULT_SETTINGS.items():
            if key in settings:
                data["settings"][key] = settings[key]
        data["settings"] = self._sanitize_settings(data["settings"])

        if version == 1 or "todos" in raw:
            # v1：{"version":1,"todos":{date:[{id,text,done}]}}
            self._backup_v1()
            todos = raw.get("todos") if isinstance(raw.get("todos"), dict) else {}
            for key, items in todos.items():
                day = _parse_day(key)
                if day is None or not isinstance(items, list):
                    continue
                cleaned = []
                for item in items:
                    task = sanitize_task(item)
                    if task is not None:
                        cleaned.append(task)
                    else:
                        self.errors.append(f"{key} 丢弃 1 条无效任务")
                if cleaned:
                    data["tasks"][day.isoformat()] = cleaned
            self.dirty = True
            return data

        tasks = raw.get("tasks") if isinstance(raw.get("tasks"), dict) else {}
        for key, items in tasks.items():
            day = _parse_day(key)
            if day is None or not isinstance(items, list):
                self.errors.append(f"忽略非法日期键 {key!r}")
                continue
            cleaned = []
            for item in items:
                task = sanitize_task(item)
                if task is not None:
                    cleaned.append(task)
                else:
                    self.errors.append(f"{key} 丢弃 1 条无效任务")
            if cleaned:
                data["tasks"][day.isoformat()] = cleaned
        for item in raw.get("series") or []:
            series = sanitize_series(item)
            if series is not None:
                data["series"].append(series)
        data["version"] = SCHEMA_VERSION
        return data

    def _backup_v1(self) -> None:
        target = os.path.join(self.directory, "notes.v1.bak.json")
        if os.path.exists(target) or not os.path.exists(self.path):
            return
        try:
            shutil.copy2(self.path, target)
            self.errors.append("v1 数据已备份为 notes.v1.bak.json")
        except OSError as exc:
            self.errors.append(f"v1 备份失败：{exc}")

    def _sanitize_settings(self, settings: dict) -> dict:
        out = dict(DEFAULT_SETTINGS)
        opacity = settings.get("opacity")
        if isinstance(opacity, (int, float)):
            out["opacity"] = max(35, min(100, int(opacity)))
        accent = settings.get("accent")
        if isinstance(accent, str) and len(accent) == 7 and accent.startswith("#"):
            try:
                int(accent[1:], 16)
                out["accent"] = accent.lower()
            except ValueError:
                pass
        theme = settings.get("theme")
        if theme in ("dark", "light"):
            out["theme"] = theme
        view = settings.get("view")
        if view in ("week", "month"):
            out["view"] = view
        for flag in ("alwaysOnTop", "autoFade", "snap", "autostart"):
            if isinstance(settings.get(flag), bool):
                out[flag] = settings[flag]
        hotkey = settings.get("hotkey")
        if isinstance(hotkey, str) and hotkey.strip():
            out["hotkey"] = hotkey.strip()[:32]
        return out

    # ---------- 设置 ----------

    @property
    def settings(self) -> dict:
        return self.data["settings"]

    def set_setting(self, key: str, value) -> None:
        if key not in DEFAULT_SETTINGS:
            return
        if self.settings.get(key) == value:
            return
        self.settings[key] = value
        self.touch()

    # ---------- 任务 ----------

    def tasks_for(self, day: date) -> list[dict]:
        return self.data["tasks"].setdefault(day.isoformat(), [])

    def peek_tasks(self, day: date) -> list[dict]:
        return self.data["tasks"].get(day.isoformat(), [])

    def add_task(
        self,
        day: date,
        text: str,
        priority: int = 0,
        remind_at: str | None = None,
        series_id: str | None = None,
        index: int | None = None,
    ) -> dict | None:
        text = " ".join((text or "").split()).strip()
        if not text:
            return None
        task = make_task(text, priority, remind_at, series_id)
        items = self.tasks_for(day)
        if index is None or index >= len(items):
            items.append(task)
        else:
            items.insert(max(0, index), task)
        self.touch()
        return task

    def find_task(self, day: date, task_id: str) -> tuple[int, dict] | None:
        for index, task in enumerate(self.peek_tasks(day)):
            if task.get("id") == task_id:
                return index, task
        return None

    def set_done(self, day: date, task_id: str, done: bool) -> dict | None:
        found = self.find_task(day, task_id)
        if found is None:
            return None
        task = found[1]
        task["done"] = bool(done)
        task["doneAt"] = _now_iso() if done else None
        self.touch()
        return task

    def update_task(self, day: date, task_id: str, **fields) -> dict | None:
        found = self.find_task(day, task_id)
        if found is None:
            return None
        task = found[1]
        for key, value in fields.items():
            if key == "text":
                value = " ".join(str(value).split()).strip()[:MAX_TEXT]
                if not value:
                    return None
            elif key == "priority":
                value = value if value in (0, 1, 2) else task.get("priority", 0)
            elif key == "remindAt":
                value = _valid_remind(value)
            task[key] = value
        self.touch()
        return task

    def delete_task(self, day: date, task_id: str) -> tuple[int, dict] | None:
        items = self.peek_tasks(day)
        for index, task in enumerate(items):
            if task.get("id") == task_id:
                items.pop(index)
                if not items:
                    self.data["tasks"].pop(day.isoformat(), None)
                self.touch()
                return index, task
        return None

    def insert_task(self, day: date, index: int, task: dict) -> None:
        items = self.tasks_for(day)
        items.insert(max(0, min(index, len(items))), dict(task))
        self.touch()

    def pending(self, day: date) -> list[dict]:
        return [task for task in self.peek_tasks(day) if not task.get("done")]

    def carry_over(self, source: date, target: date) -> list[dict]:
        """把 source 的未完成任务搬到 target，返回被搬动的任务副本。"""
        moved: list[dict] = []
        for task in list(self.pending(source)):
            self.delete_task(source, task["id"])
            clone = dict(task)
            clone["rolledFrom"] = source.isoformat()
            clone["done"] = False
            clone["doneAt"] = None
            self.tasks_for(target).append(clone)
            moved.append(clone)
        if moved:
            self.touch()
        return moved

    def undo_carry(self, moved: list[dict], source: date, target: date) -> None:
        ids = {task["id"] for task in moved}
        items = self.peek_tasks(target)
        self.data["tasks"][target.isoformat()] = [
            task for task in items if task.get("id") not in ids
        ]
        if not self.data["tasks"][target.isoformat()]:
            self.data["tasks"].pop(target.isoformat(), None)
        for task in moved:
            restore = dict(task)
            restore["rolledFrom"] = None
            self.tasks_for(source).append(restore)
        self.touch()

    def month_stats(self, year: int, month: int) -> tuple[int, int]:
        total = done = 0
        for key, items in self.data["tasks"].items():
            day = _parse_day(key)
            if day is None or day.year != year or day.month != month:
                continue
            for task in items:
                total += 1
                if task.get("done"):
                    done += 1
        return total, done

    def heatmap(self, days: int = 28, end: date | None = None) -> list[dict]:
        end = end or date.today()
        out = []
        for offset in range(days - 1, -1, -1):
            day = end - timedelta(days=offset)
            items = self.peek_tasks(day)
            out.append(
                {
                    "date": day,
                    "total": len(items),
                    "done": sum(1 for task in items if task.get("done")),
                }
            )
        return out

    def streak(self, end: date | None = None) -> int:
        """连续「清零」天数：当天有任务且全部完成才算数。"""
        day = end or date.today()
        items = self.peek_tasks(day)
        if not items or any(not task.get("done") for task in items):
            day -= timedelta(days=1)
        count = 0
        for _ in range(370):
            items = self.peek_tasks(day)
            if not items or any(not task.get("done") for task in items):
                break
            count += 1
            day -= timedelta(days=1)
        return count

    # ---------- 重复任务 ----------

    def series_list(self) -> list[dict]:
        return self.data["series"]

    def add_series(
        self,
        text: str,
        rule: str = "daily",
        weekdays: list[int] | None = None,
        day_of_month: int = 1,
        priority: int = 0,
        remind_at: str | None = None,
        start: date | None = None,
    ) -> dict | None:
        series = sanitize_series(
            {
                "text": text,
                "rule": rule,
                "weekdays": weekdays or [],
                "dayOfMonth": day_of_month,
                "priority": priority,
                "remindAt": remind_at,
            }
        )
        if series is None:
            return None
        self.data["series"].append(series)
        self.touch()
        self.materialize(span=28)
        return series

    def delete_series(self, series_id: str, keep_existing: bool = True) -> bool:
        before = len(self.data["series"])
        self.data["series"] = [
            series for series in self.data["series"] if series.get("id") != series_id
        ]
        if len(self.data["series"]) == before:
            return False
        if not keep_existing:
            for key, items in list(self.data["tasks"].items()):
                kept = [task for task in items if task.get("seriesId") != series_id]
                if kept:
                    self.data["tasks"][key] = kept
                else:
                    self.data["tasks"].pop(key, None)
        self.touch()
        return True

    def set_series_active(self, series_id: str, active: bool) -> None:
        for series in self.data["series"]:
            if series.get("id") == series_id:
                series["active"] = bool(active)
                self.touch()
                return

    def materialize(
        self,
        days: list[date] | None = None,
        span: int = 21,
        series: dict | None = None,
    ) -> int:
        """把重复规则展开成具体任务；已存在同 seriesId 的日期不重复添加。"""
        targets = days or [date.today() + timedelta(days=offset) for offset in range(-7, span)]
        created = 0
        for item in [series] if series else self.data["series"]:
            if not item.get("active", True):
                continue
            for day in targets:
                if not series_matches(item, day):
                    continue
                items = self.peek_tasks(day)
                if any(task.get("seriesId") == item["id"] for task in items):
                    continue
                task = make_task(
                    item["text"],
                    item.get("priority", 0),
                    item.get("remindAt"),
                    series_id=item["id"],
                )
                self.tasks_for(day).append(task)
                created += 1
        if created:
            self.touch()
        return created

    def _materialize_all(self) -> None:
        self.materialize(span=28)

    # ---------- 落盘 ----------

    def touch(self) -> None:
        self.dirty = True

    def save(self) -> None:
        if not self.dirty:
            return
        payload = dict(self.data)
        payload["version"] = SCHEMA_VERSION
        try:
            atomic_write(self.path, payload)
            self.dirty = False
        except OSError as exc:
            self.errors.append(f"保存失败：{exc}")

    def export_markdown(self, target: str) -> str:
        lines = ["# 桌面便签导出", ""]
        for key in sorted(self.data["tasks"]):
            items = self.data["tasks"][key]
            if not items:
                continue
            lines.append(f"## {key}")
            for task in items:
                mark = "x" if task.get("done") else " "
                extra = ""
                if task.get("remindAt"):
                    extra += f" ⏰{task['remindAt']}"
                if task.get("priority"):
                    extra += " " + "!" * task["priority"]
                lines.append(f"- [{mark}] {task['text']}{extra}")
            lines.append("")
        with open(target, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines))
        return target

    # ---------- 窗口位置 ----------

    def load_window_state(self) -> dict:
        state = dict(WINDOW_STATE_DEFAULT)
        try:
            with open(self.state_path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
            if isinstance(raw, dict):
                for key in ("x", "y"):
                    if isinstance(raw.get(key), int):
                        state[key] = raw[key]
                for key in ("width", "height"):
                    if isinstance(raw.get(key), int) and 300 <= raw[key] <= 2000:
                        state[key] = raw[key]
        except (OSError, json.JSONDecodeError):
            pass
        return state

    def save_window_state(self, x: int, y: int, width: int, height: int) -> None:
        try:
            atomic_write(
                self.state_path,
                {"x": int(x), "y": int(y), "width": int(width), "height": int(height)},
            )
        except OSError as exc:
            self.errors.append(f"窗口位置保存失败：{exc}")

    def crash_log(self, text: str) -> None:
        try:
            with open(os.path.join(self.directory, "crash.log"), "a", encoding="utf-8") as handle:
                handle.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {text}\n")
        except OSError:
            pass
