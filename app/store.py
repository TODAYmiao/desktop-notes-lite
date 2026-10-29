"""本地 JSON 存储。"""

import json
import os
import re
import uuid
from pathlib import Path

from .theme import DEFAULT_ACCENT, normalize_hex

APP_FOLDER = "DesktopNotesLite"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def app_data_dir() -> Path:
    base = os.environ.get("APPDATA")
    if base:
        return Path(base) / APP_FOLDER
    return Path.home() / "AppData" / "Roaming" / APP_FOLDER


def _default_data() -> dict:
    return {
        "version": 1,
        "todos": {},
        "settings": {"opacity": 80, "alwaysOnTop": True, "accent": DEFAULT_ACCENT},
    }


def sanitize(raw) -> dict:
    out = _default_data()
    if not isinstance(raw, dict):
        return out

    todos = raw.get("todos")
    if isinstance(todos, dict):
        for key, items in todos.items():
            if not isinstance(key, str) or not DATE_RE.match(key) or not isinstance(items, list):
                continue
            clean = []
            for item in items:
                if not isinstance(item, dict) or not isinstance(item.get("text"), str):
                    continue
                text = item["text"].strip()[:500]
                if not text:
                    continue
                clean.append(
                    {
                        "id": item.get("id") if isinstance(item.get("id"), str) and item.get("id") else str(uuid.uuid4()),
                        "text": text,
                        "done": item.get("done") is True,
                        "createdAt": item.get("createdAt") if isinstance(item.get("createdAt"), (int, float)) else 0,
                    }
                )
            if clean:
                out["todos"][key] = clean

    settings = raw.get("settings")
    if isinstance(settings, dict):
        try:
            opacity = int(settings.get("opacity", 80))
            out["settings"]["opacity"] = max(35, min(95, opacity))
        except (TypeError, ValueError):
            pass
        out["settings"]["alwaysOnTop"] = settings.get("alwaysOnTop") is not False
        out["settings"]["accent"] = normalize_hex(settings.get("accent"))

    return out


class Store:
    def __init__(self) -> None:
        self.dir = app_data_dir()
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "notes.json"
        self.window_path = self.dir / "window-state.json"
        self.data = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            try:
                return sanitize(json.loads(self.path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                return _default_data()

        data = _default_data()
        self._write(data)
        return data

    def _write(self, data: dict) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    def save(self) -> None:
        self._write(self.data)

    @property
    def todos(self) -> dict:
        return self.data["todos"]

    @property
    def settings(self) -> dict:
        return self.data["settings"]

    def items_for(self, key: str) -> list:
        return self.data["todos"].get(key, [])

    def load_window_pos(self):
        try:
            raw = json.loads(self.window_path.read_text(encoding="utf-8"))
            return int(raw["x"]), int(raw["y"])
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def save_window_pos(self, x: int, y: int) -> None:
        try:
            self.window_path.write_text(
                json.dumps({"x": int(x), "y": int(y)}), encoding="utf-8"
            )
        except OSError:
            pass
