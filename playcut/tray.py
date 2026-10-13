"""系統匣常駐 + 單一實例。

• 關閉視窗時不真的結束，而是縮到 Windows 右下角的系統匣，
  下次開啟（雙擊 exe、雙擊影片檔、點系統匣圖示）幾乎是瞬間出現。
• 縮到系統匣後超過 IDLE_MINUTES 分鐘沒被叫出來，就自己完全結束，釋放記憶體。
• 第二次啟動 PlayCut 時，會把要開的檔案交給已經在跑的那一個，然後自己馬上離開。
"""
from __future__ import annotations

import getpass
import json
import os
import sys

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from .i18n import tr

IDLE_MINUTES = 5


def tray_supported() -> bool:
    """目前只在 Windows 啟用（macOS 關視窗本來就留在 Dock，不需要）。"""
    if sys.platform != "win32":
        return False
    from PySide6.QtWidgets import QSystemTrayIcon
    return QSystemTrayIcon.isSystemTrayAvailable()


def _server_name() -> str:
    try:
        user = getpass.getuser()
    except Exception:
        user = "user"
    safe = "".join(c if c.isalnum() else "_" for c in user)
    return f"PlayCut-single-instance-{safe}"


def forward_to_running_instance(files: list[str], timeout_ms: int = 800) -> bool:
    """如果已經有 PlayCut 在跑，把檔案交給它並回傳 True（呼叫端就可以直接離開）。"""
    sock = QLocalSocket()
    sock.connectToServer(_server_name())
    if sys.platform == "win32":
        # 我們是使用者剛開的程式（有前景權），把前景權讓給背景那個 PlayCut
        try:
            import ctypes
            ctypes.windll.user32.AllowSetForegroundWindow(-1)  # ASFW_ANY
        except Exception:
            pass
    if not sock.waitForConnected(timeout_ms):
        return False
    payload = json.dumps({"files": [os.path.abspath(f) for f in files]}).encode("utf-8")
    sock.write(payload + b"\n")
    sock.flush()
    if sock.bytesToWrite():
        # 注意：資料若已經瞬間送完，waitForBytesWritten 會回 False，所以不能拿它判斷成敗
        sock.waitForBytesWritten(timeout_ms)
    # 等對方回 "ok"，確定它真的收到了（不然可能正好在結束中）
    reply = b""
    deadline = timeout_ms * 3
    while b"\n" not in reply and sock.waitForReadyRead(deadline):
        reply += sock.readAll().data()
    ok = reply.startswith(b"ok")
    sock.disconnectFromServer()
    return ok


class SingleInstanceServer(QObject):
    """收其他 PlayCut 程序送來的「請打開這些檔案」。"""

    activated = Signal(list)   # list[str]：要開的檔案（可能是空的，只是要叫出視窗）

    def __init__(self, parent=None):
        super().__init__(parent)
        self._server = QLocalServer(self)
        self._server.setSocketOptions(QLocalServer.UserAccessOption)
        self._buffers: dict[QLocalSocket, bytes] = {}
        self._server.newConnection.connect(self._on_new_connection)

    def listen(self) -> bool:
        name = _server_name()
        if self._server.listen(name):
            return True
        # 上次當掉留下的殘骸（主要是 Unix socket 檔）
        QLocalServer.removeServer(name)
        return self._server.listen(name)

    def close(self):
        self._server.close()

    def _on_new_connection(self):
        while self._server.hasPendingConnections():
            sock = self._server.nextPendingConnection()
            self._buffers[sock] = b""
            sock.readyRead.connect(lambda s=sock: self._on_ready_read(s))
            sock.disconnected.connect(lambda s=sock: self._drop(s))

    def _drop(self, sock):
        self._buffers.pop(sock, None)
        sock.deleteLater()

    def _on_ready_read(self, sock):
        self._buffers[sock] = self._buffers.get(sock, b"") + sock.readAll().data()
        buf = self._buffers[sock]
        if b"\n" not in buf:
            return
        line = buf.split(b"\n", 1)[0]
        self._buffers[sock] = b""
        try:
            files = [f for f in json.loads(line.decode("utf-8")).get("files", [])
                     if isinstance(f, str)]
        except Exception:
            files = []
        sock.write(b"ok\n")
        sock.flush()
        self.activated.emit(files)


class TrayController(QObject):
    """系統匣圖示、關窗時縮小、閒置自動結束。"""

    def __init__(self, app, win, parent=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QMenu, QSystemTrayIcon

        self.app = app
        self.win = win
        self.server = None          # SingleInstanceServer，由 __main__ 設定
        self._quitting = False

        self.tray = QSystemTrayIcon(app.windowIcon(), self)
        self.tray.setToolTip("PlayCut")
        menu = QMenu()
        self.act_show = menu.addAction(tr("開啟 PlayCut"))
        self.act_show.triggered.connect(lambda: self.show_window())
        menu.addSeparator()
        self.act_quit = menu.addAction(tr("完全結束"))
        self.act_quit.triggered.connect(self.quit)
        self._menu = menu   # 保留參考
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

        self.idle = QTimer(self)
        self.idle.setSingleShot(True)
        self.idle.setInterval(IDLE_MINUTES * 60 * 1000)
        self.idle.timeout.connect(self.quit)

        app.setQuitOnLastWindowClosed(False)
        win.tray_controller = self

    # ------------------------------------------------------------------
    @property
    def quitting(self) -> bool:
        return self._quitting

    def _on_tray_activated(self, reason):
        from PySide6.QtWidgets import QSystemTrayIcon
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.show_window()

    def window_hidden(self):
        """主視窗縮到系統匣後呼叫：開始倒數。"""
        self.idle.start()
        s = self.win.settings
        if not s.value("trayHintShown", False, bool):
            s.setValue("trayHintShown", True)
            self.tray.showMessage(
                "PlayCut",
                tr("PlayCut 已縮到系統匣，下次開啟會更快。\n"
                   "{n} 分鐘內沒再使用就會自動結束。", n=IDLE_MINUTES),
                self.tray.icon(), 5000)

    def show_window(self, files: list[str] | None = None):
        if self._quitting:
            return
        self.idle.stop()
        w = self.win
        if w.isFullScreen():
            w.show()
        else:
            w.showMaximized()   # 從系統匣叫回來也一律放到最大
        w.raise_()
        w.activateWindow()
        _force_foreground(w)
        for f in files or []:
            if os.path.exists(f):
                w.load(f)

    def stop_listening(self):
        """重新啟動前先放掉單一實例的名稱，新程序才不會把檔案又丟回來給我們。"""
        if self.server is not None:
            self.server.close()

    def start_listening(self):
        if self.server is not None:
            self.server.listen()

    def quit(self):
        """真的結束程式（系統匣選單「完全結束」、閒置逾時、檔案 → 離開）。"""
        if self._quitting:
            return
        self._quitting = True
        from .mainwindow import _arm_exit_watchdog
        _arm_exit_watchdog()      # 萬一收尾卡住，也保證行程會結束、放掉影片檔
        self.idle.stop()
        self.stop_listening()
        self.win.close()          # quitting=True → 走正常的存檔 + 關閉 mpv 流程
        self.tray.hide()
        self.app.quit()


def _force_foreground(win):
    """Windows 會擋背景程式搶焦點，只讓工作列閃一下。用 AllowSetForegroundWindow
    搭配 SetForegroundWindow 讓視窗真的跳到最前面。"""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = int(win.winId())
        SW_RESTORE = 9
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetForegroundWindow(hwnd)
    except Exception:
        pass
