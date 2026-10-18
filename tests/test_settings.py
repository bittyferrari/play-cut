"""設定視窗：微調間隔、跳轉秒數、快捷鍵頁、恢復預設、存檔後重開讀回。

執行：python tests/test_settings.py
"""
import os, sys, tempfile
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from PySide6.QtCore import QSettings
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtTest import QTest

from playcut.mpvwidget import configure_surface_format
configure_surface_format()
app = QApplication(sys.argv)
import playcut.mainwindow as MW
from playcut.mainwindow import MainWindow
from playcut.settingsdialog import DEFAULTS, SettingsDialog

# 用暫存的 ini 檔，不要動到使用者真正的設定
_INI = str(Path(tempfile.mkdtemp(prefix="fp_set_")) / "test.ini")
def _Settings(*_a, **_k):
    return QSettings(_INI, QSettings.IniFormat)
MW.QSettings = _Settings

ok = True
def check(n, c, d=""):
    global ok; ok &= bool(c); print(("✅" if c else "❌"), n, d)

def make_dialog(w, page=0):
    entries = [e for _, e in w._actions.values()]
    cur = {aid: a.shortcut().toString(QKeySequence.PortableText)
           for aid, (a, _) in w._actions.items()}
    dlg = SettingsDialog(w, w.current_prefs(), entries, cur,
                         names_for=w._dyn_name_map, page=page)
    dlg.applied.connect(w._settings_applied)
    return dlg

w = MainWindow(); w.resize(1000, 640); w.show(); QTest.qWait(200)
check("預設聲音延遲間隔 10ms", w._audio_step == 10)
check("預設選單名稱", w._actions["audio_later"][0].text() == "聲音延後 10ms",
      w._actions["audio_later"][0].text())
check("延遲欄的上下鍵間隔 = 10", w.spn_delay.singleStep() == 10)

# ---- 改設定 ----
dlg = make_dialog(w)
check("有 7 個分頁", dlg.nav.count() == 7)
f = dlg._fields
f["audioDelayStep"][1](25)
f["subDelayStep"][1](250)
f["seekMedium"][1](3)
f["seekSmall"][1](0.5)
f["volumeStep"][1](10)
f["speedStep"][1](0.25)
f["swipeSpan"][1](60)
f["pausedBadge"][1](True)
f["screenshotFormat"][1]("jpg")
f["hdrToneMapping"][1]("mobius")
check("快捷鍵頁名稱即時跟著變",
      any(dlg.keys.tbl.item(r, 1).text() == "倒退 3 秒" for r in range(dlg.keys.tbl.rowCount())))
dlg.keys._edits["add_marker"].setKeySequence(QKeySequence("G"))
check("套用成功", dlg.apply())
dlg.close()

check("聲音延遲間隔 = 25", w._audio_step == 25)
check("選單名稱跟著變", w._actions["audio_later"][0].text() == "聲音延後 25ms",
      w._actions["audio_later"][0].text())
check("倒退名稱跟著變", w._actions["back5"][0].text() == "倒退 3 秒", w._actions["back5"][0].text())
check("小跳 0.5 秒", w._actions["fwd1"][0].text() == "快轉 0.5 秒", w._actions["fwd1"][0].text())
check("按鈕提示跟著變", "25ms" in w.spn_delay.toolTip(), w.spn_delay.toolTip())
check("延遲欄的上下鍵間隔 = 25", w.spn_delay.singleStep() == 25)
w.spn_delay.setValue(0)
w._actions["audio_later"][0].trigger()
w._actions["audio_later"][0].trigger()
check("快捷鍵一次 +25ms", w.spn_delay.value() == 50, str(w.spn_delay.value()))
w._actions["audio_earlier"][0].trigger()
check("快捷鍵一次 −25ms", w.spn_delay.value() == 25, str(w.spn_delay.value()))
w.spn_delay.setValue(0)
check("加速間隔 = 0.25", abs(w._speed_step - 0.25) < 1e-9)
check("選單的加速間隔有勾 0.25",
      any(a.isChecked() and abs(a.data() - 0.25) < 1e-9 for a in w._speed_step_menu.actions()))
check("滑動靈敏度 = 60", w.video.swipe_span == 60)
check("暫停標示打開", w.act_paused_badge.isChecked())
check("截圖格式 jpg", w._shot_format() == "jpg")
check("HDR = mobius", w.settings.value("hdrToneMapping") == "mobius")
check("改鍵 M → G", w._key("add_marker") == "G")
w.close(); QTest.qWait(200)

# ---- 重開讀回 ----
w2 = MainWindow(); w2.show(); QTest.qWait(200)
p = w2.current_prefs()
check("重開讀回聲音間隔", p["audioDelayStep"] == 25 and w2._audio_step == 25)
check("重開讀回字幕間隔", p["subDelayStep"] == 250)
check("重開讀回選單名稱", w2._actions["sub_later"][0].text() == "字幕延後 250ms")
check("重開讀回加速間隔", abs(w2._speed_step - 0.25) < 1e-9)
check("重開讀回快捷鍵", w2._key("add_marker") == "G")

# ---- 衝突時不能套用 ----
_orig_warn = QMessageBox.warning
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)
dlg = make_dialog(w2, SettingsDialog.PAGE_KEYS)
check("指定開在快捷鍵頁", dlg.stack.currentIndex() == SettingsDialog.PAGE_KEYS)
dlg.keys._edits["set_in"].setKeySequence(QKeySequence("G"))
check("按鍵重複 → 套用失敗", not dlg.apply())
check("重複時設定沒動", w2._key("set_in") == "I")
dlg.close()
QMessageBox.warning = _orig_warn

# ---- 恢復本頁預設 ----
dlg = make_dialog(w2, SettingsDialog.PAGE_AUDIO)
dlg.reset_page()
v = dlg.values()
check("聲音頁恢復預設", v["audioDelayStep"] == DEFAULTS["audioDelayStep"]
      and v["volumeStep"] == DEFAULTS["volumeStep"])
check("其他頁不受影響", v["subDelayStep"] == 250)
dlg.nav.setCurrentRow(SettingsDialog.PAGE_KEYS)
dlg.reset_page()
check("快捷鍵頁恢復預設", dlg.keys.values()["add_marker"] == "M")
check("確定後套用", dlg.apply())
check("套用後回到預設鍵", w2._key("add_marker") == "M")
dlg.close()

# ---- 範圍檢查：設定檔被亂改也不會壞 ----
s = _Settings(); s.setValue("audioDelayStep", 999999); s.setValue("seekMedium", -3); s.sync()
w2._load_step_prefs()
check("超出範圍會被夾住", w2._prefs["audioDelayStep"] == 1000 and w2._prefs["seekMedium"] == 0.1,
      f'{w2._prefs["audioDelayStep"]} {w2._prefs["seekMedium"]}')

if "--shot" in sys.argv:
    from playcut.mainwindow import apply_dark_theme
    apply_dark_theme(app)
    for i in range(7):
        d = make_dialog(w2, i); d.show(); QTest.qWait(100)
        d.grab().save(str(Path(_INI).parent / f"settings_{i}.png"))
        d.close()
    print("截圖:", Path(_INI).parent)
w2.close()
sys.exit(0 if ok else 1)
