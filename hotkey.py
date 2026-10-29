"""全局热键：Win32 RegisterHotKey + Qt 原生事件过滤器。

改造前完全没有这个能力 —— 想记一条待办必须先找到那个小窗口。现在 Ctrl+Alt+N
可以从任何程序里把便签召唤到前台并聚焦输入行。
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal

WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
ERROR_HOTKEY_ALREADY_REGISTERED = 1409

VK_CODES = {chr(code): code for code in range(ord("A"), ord("Z") + 1)}
VK_CODES.update({str(digit): ord(str(digit)) for digit in range(10)})
VK_CODES.update({f"F{i}": 0x6F + i for i in range(1, 25)})
VK_CODES["SPACE"] = 0x20


def parse_sequence(sequence: str) -> tuple[int, int] | None:
    """'Ctrl+Alt+N' → (modifiers, vk)。无法识别时返回 None。"""
    if not sequence:
        return None
    parts = [part.strip() for part in sequence.split("+") if part.strip()]
    if not parts:
        return None
    modifiers = 0
    for part in parts[:-1]:
        key = part.upper()
        if key in ("CTRL", "CONTROL"):
            modifiers |= MOD_CONTROL
        elif key == "ALT":
            modifiers |= MOD_ALT
        elif key == "SHIFT":
            modifiers |= MOD_SHIFT
        elif key in ("WIN", "META", "SUPER"):
            modifiers |= MOD_WIN
        else:
            return None
    vk = VK_CODES.get(parts[-1].upper())
    if vk is None:
        return None
    return modifiers, vk


class GlobalHotkey(QObject, QAbstractNativeEventFilter):
    """按下热键时发出 `triggered`。

    QAbstractNativeEventFilter 本身不是 QObject，所以这里同时继承 QObject
    才能带信号；installNativeEventFilter 只认前者，两者互不影响。
    """

    triggered = Signal()

    def __init__(self, hwnd: int, sequence: str = "Ctrl+Alt+N", parent: QObject | None = None) -> None:
        QObject.__init__(self, parent)
        QAbstractNativeEventFilter.__init__(self)
        self.hwnd = int(hwnd or 0)
        self.sequence = sequence
        self.registered = False
        self.error = ""
        self._hotkey_id = 0xB17E

    def register(self) -> bool:
        parsed = parse_sequence(self.sequence)
        if parsed is None:
            self.error = f"无法解析热键 {self.sequence!r}"
            return False
        if not self.hwnd:
            self.error = "窗口句柄不可用"
            return False
        modifiers, vk = parsed
        try:
            ok = ctypes.windll.user32.RegisterHotKey(self.hwnd, self._hotkey_id, modifiers, vk)
        except (AttributeError, OSError) as exc:  # 非 Windows 或权限异常
            self.error = str(exc)
            return False
        if not ok:
            code = ctypes.windll.kernel32.GetLastError()
            if code == ERROR_HOTKEY_ALREADY_REGISTERED:
                self.error = f"{self.sequence} 已被其他程序占用"
            else:
                self.error = f"注册失败（错误码 {code}）"
            return False
        self.registered = True
        return True

    def unregister(self) -> None:
        if not self.registered:
            return
        try:
            ctypes.windll.user32.UnregisterHotKey(self.hwnd, self._hotkey_id)
        except (AttributeError, OSError):
            pass
        self.registered = False

    def nativeEventFilter(self, event_type, message):  # noqa: N802 - Qt 覆写
        if not self.registered:
            return False, 0
        try:
            msg = wintypes.MSG.from_address(int(message))
        except (TypeError, ValueError):
            return False, 0
        if msg.message == WM_HOTKEY and int(msg.wParam) == self._hotkey_id:
            self.triggered.emit()
            return True, 0
        return False, 0
