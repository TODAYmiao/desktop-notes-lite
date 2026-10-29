"""离屏冒烟：构建主窗口、跑一遍关键交互、抓三张图，然后立刻退出。

用法：python tools/smoke.py [输出目录]
"""

from __future__ import annotations

import os
import shutil
import sys
from datetime import date, timedelta

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for candidate in (os.path.join(REPO_ROOT, ".pylibs"), REPO_ROOT):
    if os.path.isdir(candidate) and candidate not in sys.path:
        sys.path.insert(0, candidate)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.store import Store  # noqa: E402
from app.theme import Theme  # noqa: E402
from app.window import NotesWindow  # noqa: E402


def main() -> int:
    out_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO_ROOT, "screenshots")
    os.makedirs(out_dir, exist_ok=True)
    data_dir = os.path.join(REPO_ROOT, ".smoke-data")
    # 每次都从干净数据开始，否则重复任务会越跑越多、截图不可复现
    shutil.rmtree(data_dir, ignore_errors=True)
    store = Store(directory=data_dir)

    app = QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    theme = Theme()
    window = NotesWindow(store, theme)
    window.resize(420, 664)
    window.show()
    app.processEvents()

    today = date.today()
    seed = [
        (today, "整理本周计划", 1, None),
        (today, "下午 3 点项目评审", 2, "15:00"),
        (today, "买咖啡豆", 0, None),
        (today - timedelta(days=1), "昨天的遗留任务", 0, None),
        (today + timedelta(days=1), "明天的会议", 0, None),
    ]
    for day, text, priority, remind in seed:
        store.add_task(day, text, priority=priority, remind_at=remind)
    done_task = store.add_task(today, "早起喝水")
    if done_task:
        store.set_done(today, done_task["id"], True)
    store.add_series("写日报", rule="weekdays")
    store.settings["opacity"] = 100
    window.render_all()
    app.processEvents()

    shots = []

    def grab(name: str) -> None:
        path = os.path.join(out_dir, name)
        app.processEvents()
        window.grab().save(path)
        shots.append(path)

    grab("v2-dark-week.png")
    window.toggle_view()
    app.processEvents()
    grab("v2-dark-month.png")
    window.toggle_view()

    window.set_theme_mode("light")
    app.processEvents()
    grab("v2-light-week.png")

    # 交互冒烟：快速添加、搜索、撤销、顺延、设置浮层
    window.input.setText("明天 9点半 !! 交周报 @会议室")
    window.on_input_changed(window.input.text())
    preview = window.preview.text()
    window.add_from_input()
    app.processEvents()
    window.go_today()
    window.open_search()
    window.on_search_changed("咖啡")
    app.processEvents()
    window.close_search()
    window.carry_over()
    app.processEvents()
    window.undo()
    window.toggle_settings()
    app.processEvents()
    grab("v2-light-settings.png")
    window.popover.hide()

    errors = []
    for path in shots:
        if not os.path.exists(path) or os.path.getsize(path) < 5000:
            errors.append(f"截图异常：{path}")
    print("PREVIEW:", preview)
    print("TASKS:", len(store.peek_tasks(today)))
    for path in shots:
        print("SHOT:", path, os.path.getsize(path))
    for message in store.errors:
        errors.append(message)
    if errors:
        for message in errors:
            print("ERROR:", message)
        return 1
    print("SMOKE_OK")
    return 0


def hard_exit(code: int) -> None:
    """立刻退出，跳过 Qt 的析构顺序问题。

    正常 return 会让解释器去销毁 QApplication 与托盘图标，顺序稍有不对就是
    一段 "QPainter::begin" 之类的噪声，甚至卡住不退出。这里直接结束进程。

    注意：即便用 TerminateProcess（不发 DLL_PROCESS_DETACH），本机实测仍会
    偶发 0xC0000005 —— 那是 Qt 在进程终止瞬间的线程竞态，和脚本逻辑无关。
    所以判断通过与否只看输出里的 SMOKE_OK，不看退出码；需要干净退出码的场景
    （比如 CI）应该跑 tests/ 里的 unittest。
    """
    sys.stdout.flush()
    sys.stderr.flush()
    if os.name == "nt":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        kernel32.TerminateProcess(kernel32.GetCurrentProcess(), code)
    os._exit(code)


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    hard_exit(code)
