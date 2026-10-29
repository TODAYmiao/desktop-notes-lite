"""桌面便签 Lite —— PySide6 原生实现入口。"""

import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from app.store import Store
from app.window import NotesWindow

SERVER_NAME = "DesktopNotesLite.App"


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


def screenshot_path():
    if "--shot" in sys.argv:
        index = sys.argv.index("--shot")
        if index + 1 < len(sys.argv):
            return sys.argv[index + 1]
    return None


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("桌面便签 Lite")
    app.setFont(QFont("Microsoft YaHei UI", 9))

    if activate_existing():
        return 0

    QLocalServer.removeServer(SERVER_NAME)
    server = QLocalServer(app)
    server.listen(SERVER_NAME)

    window = NotesWindow(Store())

    def handle_connection() -> None:
        connection = server.nextPendingConnection()
        if connection is None:
            return
        connection.waitForReadyRead(100)
        connection.readAll()
        connection.disconnectFromServer()
        window.show_from_tray()

    server.newConnection.connect(handle_connection)
    window.show()

    shot = screenshot_path()
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
