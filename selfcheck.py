"""改造清单自检：把 README「为什么重做」里的承诺逐条对着代码核一遍。

用法：python tools/selfcheck.py
退出码 0 表示清单全部落地；1 表示有缺项（并打印缺哪一条）。
"""

from __future__ import annotations

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (编号, 名称, 文件, 必须同时出现的片段)
CHECKS: list[tuple[str, str, str, tuple[str, ...]]] = [
    ("01", "迷你月带（周条）", "app/window.py", ("week_strip", "render_calendar", "week_cells")),
    ("02", "今日进度环", "app/widgets.py", ("class ProgressRing", "def set_data")),
    ("03", "三层信息（大日期/周几/连续天数）", "app/window.py", ("heroDate", "heroWeek", "heroStreak")),
    ("04", "浅色主题", "app/theme.py", ("LIGHT", '"light"', "set_mode")),
    ("05", "深色主题", "app/theme.py", ("DARK", "PALETTES")),
    ("06", "勾选动画", "app/widgets.py", ("class CheckButton", "QVariantAnimation", "setDuration(170)")),
    ("07", "清零庆祝", "app/widgets.py", ("class Celebration", "def play")),
    ("08", "清零庆祝已接线", "app/window.py", ("celebration.play", "celebrated")),
    ("09", "全局热键", "app/hotkey.py", ("RegisterHotKey", "WM_HOTKEY")),
    ("10", "自然语言快速添加", "app/quickadd.py", ("def parse_quick_add", "def parse_reminder", "~")),
    ("11", "输入实时预览", "app/window.py", ("def on_input_changed", "preview.setVisible")),
    ("12", "自动淡化", "app/window.py", ("def _apply_fade", "autoFade", "setWindowOpacity")),
    ("13", "贴边吸附", "app/window.py", ("def _apply_snap", "snap")),
    ("14", "未完成顺延", "app/store.py", ("def carry_over", "rolledFrom")),
    ("15", "顺延可撤销", "app/window.py", ("def carry_over", '"type": "carry"')),
    ("16", "撤销栈", "app/window.py", ("def push_undo", "MAX_UNDO", "def undo")),
    ("17", "跨日期搜索", "app/window.py", ("def open_search", "def on_search_changed")),
    ("18", "可缩放窗口", "app/window.py", ("MIN_WIDTH = 360", "def _resize_to", "RESIZE_MARGIN")),
    ("19", "重复任务", "app/store.py", ("def materialize", "series_matches")),
    ("20", "定时提醒", "app/window.py", ("def check_reminders", "REMINDER_CHECK_MS")),
    ("21", "跨零点刷新", "app/window.py", ("def check_rollover", "MIDNIGHT_CHECK_MS")),
    ("22", "原子写入", "app/store.py", ("def atomic_write", "fsync", "os.replace")),
    ("23", "v1 迁移备份", "app/store.py", ("notes.v1.bak.json", "_backup_v1")),
    ("24", "坏文件留档", "app/store.py", ("notes.corrupt-", "_quarantine")),
    ("25", "自启可用（自举 sys.path）", "main.py", ("sys.path.insert", ".pylibs", "pythonw")),
]

# 目录/文件存在性
PATHS = [
    ("tests/test_quickadd.py", "解析器测试"),
    ("tests/test_store.py", "数据层测试"),
    ("tests/test_window.py", "界面测试"),
    ("tools/smoke.py", "冒烟截图脚本"),
    ("docs/改造记录.md", "过程记录"),
    ("README.md", "使用说明"),
    ("CHANGELOG.md", "变更日志"),
    ("LICENSE", "许可证"),
]


def read(rel: str) -> str:
    try:
        with open(os.path.join(REPO_ROOT, rel), "r", encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return ""


def main() -> int:
    failures: list[str] = []
    print(f"仓库：{REPO_ROOT}")
    print(f"{'编号':<4}{'检查项':<28}{'结果'}")
    print("-" * 58)

    for code, name, rel, needles in CHECKS:
        text = read(rel)
        missing = [needle for needle in needles if needle not in text]
        if not text:
            failures.append(f"{code} {name}：找不到 {rel}")
            print(f"{code:<4}{name:<28}缺文件")
        elif missing:
            failures.append(f"{code} {name}：{rel} 缺少 {missing}")
            print(f"{code:<4}{name:<28}缺 {','.join(missing)}")
        else:
            print(f"{code:<4}{name:<28}OK")

    print("-" * 58)
    for rel, label in PATHS:
        path = os.path.join(REPO_ROOT, rel)
        exists = os.path.exists(path)
        print(f"{'--':<4}{label:<28}{'OK' if exists else '缺失'}")
        if not exists:
            failures.append(f"缺少文件 {rel}")

    tests = [
        name
        for name in os.listdir(os.path.join(REPO_ROOT, "tests"))
        if name.startswith("test_") and name.endswith(".py")
    ]
    print("-" * 58)
    print(f"测试文件：{len(tests)} 个 -> {sorted(tests)}")
    if len(tests) < 3:
        failures.append("测试文件少于 3 个")

    print()
    if failures:
        print(f"FAIL：{len(failures)} 项未达标")
        for line in failures:
            print("  -", line)
        return 1
    print(f"PASS：{len(CHECKS)} 条功能清单 + {len(PATHS)} 个交付文件全部落地")
    return 0


if __name__ == "__main__":
    sys.exit(main())
