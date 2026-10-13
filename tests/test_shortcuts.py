"""自訂快捷鍵、滑鼠中鍵全螢幕、全螢幕隱藏控制列。"""
import os, sys
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from PySide6.QtCore import QSettings, Qt, QPointF, QEvent
from PySide6.QtGui import QKeySequence, QMouseEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest

from playcut.mpvwidget import configure_surface_format
configure_surface_format()
app = QApplication(sys.argv)
import tempfile
import playcut.mainwindow as MW
from playcut.mainwindow import MainWindow
from playcut.shortcuts import ShortcutDialog
# 用暫存的 ini 檔，不要動到使用者真正的設定（Windows 上是登錄檔）
_INI = str(Path(tempfile.mkdtemp(prefix="fp_sc_")) / "test.ini")
def _Settings(*_a, **_k):
    return QSettings(_INI, QSettings.IniFormat)
MW.QSettings = _Settings

ok = True
def check(n, c, d=""):
    global ok; ok &= bool(c); print(("✅" if c else "❌"), n, d)

w = MainWindow(); w.resize(900, 600); w.show(); QTest.qWait(300)
check("預設 M = 插旗標", w._key("add_marker") == "M")
check("按鈕文字帶鍵", w.btn_flag.toolTip().endswith("(M)"), w.btn_flag.toolTip())

# 改鍵
w.apply_shortcuts({"add_marker": "G", "fullscreen": "Ctrl+Shift+F"})
check("改成 G", w._actions["add_marker"][0].shortcut() == QKeySequence("G"))
s = _Settings()
check("有存進設定", s.value("shortcuts/add_marker") == "G", str(s.value("shortcuts/add_marker")))
check("沒改的不存", s.value("shortcuts/play_pause") is None)
check("提示跟著更新", "(G)" in w.btn_flag.toolTip(), w.btn_flag.toolTip())
w.close(); QTest.qWait(200)

w2 = MainWindow(); w2.show(); QTest.qWait(200)
check("重開後讀回自訂鍵", w2._key("add_marker") == "G")
check("重開後讀回 Ctrl+Shift+F", w2._actions["fullscreen"][0].shortcut() == QKeySequence("Ctrl+Shift+F"))
check("打字讓路判斷", w2._yields_to_typing(QKeySequence("G")) and not w2._yields_to_typing(QKeySequence("Ctrl+G")) and not w2._yields_to_typing(QKeySequence("F1")))

# 對話框：衝突偵測
entries = [e for _, e in w2._actions.values()]
cur = {aid: a.shortcut().toString(QKeySequence.PortableText) for aid, (a, _) in w2._actions.items()}
dlg = ShortcutDialog(w2, entries, cur)
check("對話框初始無衝突", not dlg._update_conflicts())
dlg._edits["set_in"].setKeySequence(QKeySequence("G"))
c = dlg._update_conflicts()
check("偵測到 G 重複", "G" in c, str(c))
dlg._reset_all()
check("全部恢復預設後無衝突", not dlg._update_conflicts())
check("恢復預設 = M", dlg.values()["add_marker"] == "M")
dlg.close()

# 中鍵全螢幕 + 控制列隱藏
v = w2.video
QTest.mouseClick(v, Qt.MiddleButton, Qt.NoModifier, v.rect().center()); QTest.qWait(400)
check("中鍵進入全螢幕", w2.isFullScreen())
check("全螢幕隱藏控制列", not w2.bottom_bar.isVisible())
QTest.mouseClick(v, Qt.MiddleButton, Qt.NoModifier, v.rect().center()); QTest.qWait(400)
check("中鍵離開全螢幕", not w2.isFullScreen())
check("離開後控制列回來", w2.bottom_bar.isVisible())
w2.toggle_fullscreen(); QTest.qWait(300)
w2.close(); QTest.qWait(200)
w3 = MainWindow(); w3.show(); QTest.qWait(200)
check("全螢幕中關閉，重開控制列仍在", w3.bottom_bar.isVisible())
w3.close()
sys.exit(0 if ok else 1)
