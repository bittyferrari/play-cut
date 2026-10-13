"""多語系測試：翻譯表完整、系統語言判斷、各語言都能建出主視窗，英文介面沒有殘留中文。

執行：python tests/test_i18n.py
（主視窗部分需要 libmpv 與可用的 OpenGL；沒有的話只跑翻譯表檢查）
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

RESULTS: list[tuple[str, bool, str]] = []
HAN = re.compile(r"[\u4e00-\u9fff]")


def check(name: str, ok: bool, detail: str = ""):
    RESULTS.append((name, bool(ok), detail))
    print(f"  {'✅' if ok else '❌'} {name}{('  — ' + detail) if detail else ''}")


def visible_texts(win) -> list[str]:
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import (QAbstractButton, QDockWidget, QGroupBox,
                                   QLabel, QMenu, QTableWidget)
    out: list[str] = [win.windowTitle()]
    if hasattr(win, "statusBar"):
        out.append(win.statusBar().currentMessage())
    for w in win.findChildren(QAbstractButton) + win.findChildren(QLabel):
        out += [w.text(), w.toolTip()]
    for w in win.findChildren(QGroupBox) + win.findChildren(QDockWidget):
        out.append(w.title() if isinstance(w, QGroupBox) else w.windowTitle())
    for m in win.findChildren(QMenu):
        out.append(m.title())
    for a in win.findChildren(QAction):
        out += [a.text(), a.toolTip()]
    for t in win.findChildren(QTableWidget):
        for c in range(t.columnCount()):
            it = t.horizontalHeaderItem(c)
            if it:
                out.append(it.text())
    return [s for s in out if s]


def main() -> int:
    import i18n_keys
    from playcut import i18n

    print("\n[1] 翻譯表")
    keys = i18n_keys.collect_keys()
    check("找得到字串", len(keys) > 200, str(len(keys)))
    for lang, table in i18n._TABLES.items():
        if lang == i18n.SOURCE_LANG:
            continue
        missing = [k for k in keys if k not in table]
        wrong = [k for k in keys if k in table
                 and i18n_keys.fields(k) != i18n_keys.fields(table[k])]
        check(f"{lang} 沒有漏翻", not missing, "; ".join(map(repr, missing[:3])))
        check(f"{lang} 參數名稱一致", not wrong, "; ".join(map(repr, wrong[:3])))

    print("\n[2] 系統語言判斷")
    cases = {"zh-Hant-TW": "zh_TW", "zh-TW": "zh_TW", "zh-HK": "zh_TW",
             "zh-Hans-CN": "zh_CN", "zh-CN": "zh_CN", "zh-SG": "zh_CN",
             "ja-JP": "ja", "en-US": "en", "en-GB": "en", "fr-FR": None}
    for name, want in cases.items():
        check(f"{name} → {want}", i18n._match(name) == want, str(i18n._match(name)))

    print("\n[3] tr()")
    i18n.set_language("en")
    check("有翻譯", i18n.tr("開啟影片…") == "Open Video…")
    check("帶參數", i18n.tr("已載入 {n} 個旗標", n=3) == "Loaded 3 flag(s)")
    check("沒翻譯就用原文", i18n.tr("不存在的字串") == "不存在的字串")
    check("tr_for 指定語言", i18n.tr_for("ja", "語言") == "言語")
    i18n.set_language("xx")
    check("不支援的語言退回繁中", i18n.current_language() == "zh_TW")

    try:
        from playcut.mpvwidget import MPV_IMPORT_ERROR, configure_surface_format
    except Exception as exc:
        print(f"\n（略過 UI 測試：{exc}）")
        MPV_IMPORT_ERROR = exc
    if MPV_IMPORT_ERROR is not None:
        return summary()

    configure_surface_format()
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    # 用獨立的設定檔，不動到真正的設定
    tmp = tempfile.mkdtemp(prefix="i18n_")
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, tmp)

    from playcut.exportdialog import ExportDialog
    from playcut.mainwindow import MainWindow, apply_dark_theme
    from playcut.markers import Segment
    from playcut.shortcuts import ShortcutDialog
    apply_dark_theme(app)

    print("\n[4] 設定存取")
    s = QSettings("PlayCut", "PlayCut")
    i18n.save_choice(s, "ja")
    check("存 / 讀手動選擇", i18n.saved_choice(s) == "ja")
    check("init() 用手動選擇", i18n.init(app, s) == "ja")
    i18n.save_choice(s, "")
    check("空字串 = 跟隨系統", i18n.saved_choice(s) == "")
    check("跟隨系統會挑一個支援的語言",
          i18n.init(app, s) in dict(i18n.LANGUAGES))

    expect_menu = {"zh_TW": "檔案(&F)", "zh_CN": "文件(&F)", "en": "&File", "ja": "ファイル(&F)"}
    for lang, _name in i18n.LANGUAGES:
        print(f"\n[5] 介面：{lang}")
        i18n.save_choice(s, lang)
        i18n.init(app, s)
        win = MainWindow()
        titles = [a.text() for a in win.menuBar().actions()]
        check("選單標題", titles and titles[0] == expect_menu[lang], str(titles))
        check("語言選單有勾目前語言",
              any(a.isChecked() and a.data() == lang for a in win._lang_menu.actions()))
        win.markers.add(5.0, "")
        win.markers.add(10.0, "")
        win._refresh_markers()
        texts = visible_texts(win)
        dlg = ShortcutDialog(win, [e for _, e in win._actions.values()],
                             {aid: "" for aid in win._actions})
        texts += [dlg.windowTitle()]
        segs = [Segment(1.0, 3.0), Segment(5.0, 8.0)]
        ed = ExportDialog(win, str(ROOT / "demo.mp4"), segs, audio_delay=0.25,
                          player_speed=2.0, default_crop="9:16")
        texts += visible_texts(ed) + [ed.mode.itemText(i) for i in range(ed.mode.count())]
        texts += [ed.crop.itemText(i) for i in range(ed.crop.count())]
        check("匯出對話框提示有「全部重新編碼」警告", "⚠" in ed.mode_hint.text(), ed.mode_hint.text()[-60:])
        if lang == "en":
            native = {name for _, name in i18n.LANGUAGES}   # 語言選單用各語言自己的名稱
            leaked = sorted({t for t in texts if HAN.search(t) and t not in native})
            check("英文介面沒有殘留中文", not leaked, " | ".join(leaked[:5]))
        ed.deleteLater()
        dlg.deleteLater()
        win.close()
        win.deleteLater()
        app.processEvents()

    i18n.save_choice(s, "")
    return summary()


def summary() -> int:
    bad = [r for r in RESULTS if not r[1]]
    print(f"\n通過 {len(RESULTS) - len(bad)}/{len(RESULTS)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
