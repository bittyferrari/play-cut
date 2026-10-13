"""PlayCut 進入點。"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playcut.compat import apply_legacy_env  # noqa: E402
from playcut.i18n import tr  # noqa: E402

apply_legacy_env()


def _icon_path() -> Path | None:
    """找出 icon 檔（原始碼執行或 PyInstaller 打包後都適用）。"""
    bases = [Path(__file__).resolve().parent / "resources"]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        bases.insert(0, Path(meipass) / "playcut" / "resources")
    for base in bases:
        for name in ("icon.ico", "icon.png"):
            p = base / name
            if p.exists():
                return p
    return None


def _set_windows_app_id() -> None:
    """讓 Windows 工作列顯示自己的 icon，而不是 python 的。"""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "PlayCut.PlayCut")
        except Exception:
            pass


def _crash(title: str, detail: str) -> int:
    """用 pythonw 啟動時沒有主控台，所以把錯誤寫檔＋跳視窗。"""
    try:
        if sys.platform == "darwin":
            # .app 內部通常是唯讀的，改寫到 ~/Library/Logs
            logdir = Path.home() / "Library" / "Logs" / "PlayCut"
            logdir.mkdir(parents=True, exist_ok=True)
            logpath = logdir / "playcut_error.log"
        else:
            from .ffio import app_root
            logpath = Path(app_root()) / "playcut_error.log"
    except Exception:
        logpath = Path.cwd() / "playcut_error.log"
    try:
        logpath.write_text(f"{title}\n\n{detail}\n", encoding="utf-8")
    except Exception:
        logpath = None

    msg = f"{title}\n\n{detail}"
    if logpath:
        msg += "\n\n" + tr("詳細內容已存到：\n{path}", path=logpath)
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        app = QApplication.instance() or QApplication([])
        QMessageBox.critical(None, tr("PlayCut 啟動失敗"), msg)
    except Exception:
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, msg, tr("PlayCut 啟動失敗"), 0x10)
        except Exception:
            print(msg, file=sys.stderr)
    return 1


def _install_mac_file_open(app, win) -> None:
    """macOS 用 Finder「打開方式」或拖到 Dock 圖示開檔時，
    檔案路徑不會出現在 argv，而是送一個 QFileOpenEvent 給 QApplication。"""
    from PySide6.QtCore import QEvent, QObject

    class _FileOpenFilter(QObject):
        def eventFilter(self, obj, ev):
            if ev.type() == QEvent.FileOpen:
                path = ev.file()
                if path and os.path.exists(path):
                    win.load(path)
                    win.raise_()
                    win.activateWindow()
                return True
            return False

    flt = _FileOpenFilter(app)
    app.installEventFilter(flt)
    app._playcut_file_open = flt  # 保留參考，避免被 GC


def _file_args(argv: list[str]) -> list[str]:
    return [a for a in argv[1:] if not a.startswith("-") and os.path.exists(a)]


def _install_tray(app, win) -> None:
    """系統匣常駐 + 接收其他 PlayCut 程序送來的檔案。失敗就當一般程式跑。"""
    try:
        from playcut.tray import (SingleInstanceServer, TrayController,
                                     tray_supported)
        server = SingleInstanceServer(app)
        listening = server.listen()
        if not tray_supported():
            if listening:
                server.activated.connect(lambda files: _bring_up(win, files))
            return
        tc = TrayController(app, win, app)
        tc.server = server
        server.activated.connect(tc.show_window)
        app._playcut_tray = tc   # 保留參考，避免被 GC
    except Exception:
        traceback.print_exc()


def _bring_up(win, files):
    if not win.isFullScreen():
        win.showMaximized()   # 叫回前景時一律放到最大
    else:
        win.show()
    win.raise_()
    win.activateWindow()
    for f in files:
        if os.path.exists(f):
            win.load(f)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)

    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
    except Exception as exc:
        from playcut import i18n
        i18n.set_language(i18n.detect_system_language())
        return _crash(
            tr("找不到 PySide6 套件。"),
            tr("請重新執行 {script}。", script='setup_mac.command' if sys.platform == 'darwin' else 'setup.bat')
            + f"\n\n{exc}\n\n{traceback.format_exc()}")

    try:
        from playcut.glformat import configure_surface_format
        configure_surface_format()

        _set_windows_app_id()
        app = QApplication(argv)

        # Windows：已經有 PlayCut 在背景（系統匣）的話，把檔案交給它就結束。
        # 這一步在載入 libmpv / 建主視窗之前做，所以第二次開啟幾乎是瞬間。
        single = sys.platform == "win32" and "--new-instance" not in argv
        if single:
            from playcut.tray import forward_to_running_instance
            if forward_to_running_instance(_file_args(argv)):
                return 0
        app.setApplicationName("PlayCut")
        app.setOrganizationName("PlayCut")
        from playcut.compat import migrate_settings
        migrate_settings()
        from playcut import i18n
        i18n.init(app)
        icon_file = _icon_path()
        if icon_file:
            from PySide6.QtGui import QIcon
            app.setWindowIcon(QIcon(str(icon_file)))

        from playcut import mainwindow as _mw
        from playcut.mainwindow import MainWindow, apply_dark_theme
        _mw.EXIT_WATCHDOG_ENABLED = True
        apply_dark_theme(app)
        win = MainWindow()
    except Exception as exc:
        return _crash(str(exc), traceback.format_exc())

    if single:
        _install_tray(app, win)

    win.showMaximized()   # 每次開啟都放到最大

    files = _file_args(argv)
    if files:
        win.load(files[0])

    if sys.platform == "darwin":
        _install_mac_file_open(app, win)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
