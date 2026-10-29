"""桌面便签 Lite —— PySide6 原生实现入口。

0.1 版依赖 `pythonw.exe main.py` 时 PYTHONPATH 里恰好有 PySide6，开机自启因此必然
失败。现在入口自己把仓库目录和仓库内的 .pylibs（便携依赖目录）塞进 sys.path，
所以用任何 Python 解释器直接跑都不会 ImportError。
"""

from __future__ import annotations

import os
import sys
import traceback

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
for _candidate in (os.path.join(REPO_ROOT, ".pylibs"), REPO_ROOT):
    if os.path.isdir(_candidate) and _candidate not in sys.path:
        sys.path.insert(0, _candidate)

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtGui import QFont  # noqa: E402
from PySide6.QtNetwork import QLocalServer, QLocalSocket  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.store import Store  # noqa: E402
from app.theme import Theme  # noqa: E402
from app.window import NotesWindow  # noqa: E402

SERVER_NAME = "DesktopNotesLite.App"


def argument(name: str, default: str | None = None) -> str | None:
    """读取 `--name value` 形式的命令行参数。"""
    if name in sys.argv:
        index = sys.argv.index(name)
        if index + 1 < len(sys.argv):
            return sys.argv[index + 1]
    for item in sys.argv:
        if item.startswith(f"{name}="):
            return item.split("=", 1)[1]
    return default


def activate_existing() -> bool:
    socket = QLocalSocket()
    socket.connectToServer(SERVER_NAME)
    if not socket.waitForConnected(300):
        return False
    socket.write(b"show")
    socket.flush()
    socket.waitForBytesWritten(300)
    socket.disconnectFromServer()
    return True


def install_excepthook(store: Store) -> None:
    """pythonw 下没有控制台，异常必须留痕，否则只会「窗口莫名其妙消失」。"""

    def hook(exc_type, exc_value, exc_tb) -> None:
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        store.crash_log(text)
        sys.stderr.write(text)

    sys.excepthook = hook


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("桌面便签 Lite")
    app.setApplicationDisplayName("桌面便签 Lite")
    app.setFont(QFont("Microsoft YaHei UI", 9))

    data_dir = argument("--data")
    if data_dir:
        store = Store(directory=data_dir)
    else:
        store = Store()
    install_excepthook(store)

    theme = Theme(mode=store.settings.get("theme", "dark"), accent_hex=store.settings.get("accent"))

    shot = argument("--shot")
    if not shot and activate_existing():
        return 0

    QLocalServer.removeServer(SERVER_NAME)
    server = QLocalServer(app)
    server.listen(SERVER_NAME)

    window = NotesWindow(store, theme, shot_path=shot)
    window.store.materialize()

    def handle_connection() -> None:
        connection = server.nextPendingConnection()
        if connection is None:
            return
        connection.waitForReadyRead(100)
        connection.readAll()
        connection.disconnectFromServer()
        window.show_and_focus()

    server.newConnection.connect(handle_connection)
    if argument("--view"):
        window.view_mode = argument("--view", window.view_mode)
        window.store.set_setting("view", window.view_mode)
        window.render_calendar()
    window.show()

    if shot:

        def capture() -> None:
            window.repaint()
            window.grab().save(shot)
            print(f"SHOT_SAVED {shot}", flush=True)
            window.quit_app()

        QTimer.singleShot(1200, capture)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
