"""介面多語系。

做法很單純：程式裡的繁體中文原文就是 key，`tr("原文")` 會依目前語言
回傳翻譯；沒有翻譯的字串就原樣顯示，所以漏翻也不會壞掉。

    tr("開啟影片…")
    tr("已載入 {n} 個旗標", n=3)      # 有參數時用 str.format

模組層級的常數（在 import 時就求值，那時語言還沒決定）用 `N_()` 標記，
等實際顯示時再 `tr(常數)`。

語言在程式啟動時決定一次（`init()`），切換語言要重新啟動才會生效。
"""
from __future__ import annotations

import sys
from typing import Dict, Optional

from .locales import en as _en
from .locales import ja as _ja
from .locales import zh_CN as _zh_CN

SOURCE_LANG = "zh_TW"
SETTINGS_KEY = "language"      # QSettings 裡的鍵；空字串 = 跟隨系統

# (代碼, 用該語言自己寫的名稱)
LANGUAGES = [
    ("zh_TW", "繁體中文"),
    ("zh_CN", "简体中文"),
    ("en", "English"),
    ("ja", "日本語"),
]

_TABLES: Dict[str, Dict[str, str]] = {
    "zh_TW": {},
    "zh_CN": _zh_CN.T,
    "en": _en.T,
    "ja": _ja.T,
}

_lang = SOURCE_LANG
_qt_translators: list = []


def N_(text: str) -> str:
    """只做標記，給翻譯清單抓字串用；實際翻譯要等顯示時再 tr()。"""
    return text


def tr(text: str, **kw) -> str:
    s = _TABLES.get(_lang, {}).get(text, text)
    return s.format(**kw) if kw else s


def tr_for(lang: str, text: str, **kw) -> str:
    """用指定語言翻譯（例如切換語言時，用「新語言」顯示提示）。"""
    s = _TABLES.get(lang, {}).get(text, text)
    return s.format(**kw) if kw else s


def current_language() -> str:
    return _lang


def set_language(lang: str) -> str:
    global _lang
    _lang = lang if lang in _TABLES else SOURCE_LANG
    return _lang


def _match(name: str) -> Optional[str]:
    n = name.replace("-", "_").lower()
    if n.startswith("zh"):
        if "hans" in n or n.startswith(("zh_cn", "zh_sg", "zh_my")):
            return "zh_CN"
        return "zh_TW"          # zh_TW / zh_HK / zh_Hant / 單純 zh
    if n.startswith("ja"):
        return "ja"
    if n.startswith("en"):
        return "en"
    return None


def detect_system_language() -> str:
    """依系統的偏好語言清單挑第一個支援的；都不支援就用英文。"""
    names: list[str] = []
    try:
        from PySide6.QtCore import QLocale
        names = list(QLocale.system().uiLanguages())
    except Exception:
        pass
    if not names:
        try:
            import locale
            loc = locale.getlocale()[0] or ""
            if sys.platform == "win32" and not loc:
                import ctypes
                lcid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
                loc = locale.windows_locale.get(lcid, "")
            names = [loc]
        except Exception:
            names = []
    for name in names:
        m = _match(name or "")
        if m:
            return m
    return "en"


def saved_choice(settings) -> str:
    """使用者手動選的語言；空字串 = 跟隨系統。"""
    v = settings.value(SETTINGS_KEY, "", str) or ""
    return v if v in _TABLES else ""


def save_choice(settings, lang: str) -> None:
    settings.setValue(SETTINGS_KEY, lang if lang in _TABLES else "")


def init(app=None, settings=None) -> str:
    """啟動時呼叫一次：決定語言，並載入 Qt 內建對話框（是 / 否、開檔視窗…）的翻譯。"""
    if settings is None:
        from PySide6.QtCore import QSettings
        settings = QSettings("PlayCut", "PlayCut")
    lang = set_language(saved_choice(settings) or detect_system_language())
    if app is not None:
        _install_qt_translations(app, lang)
    return lang


def _install_qt_translations(app, lang: str) -> None:
    try:
        from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
    except Exception:
        return
    for t in _qt_translators:
        app.removeTranslator(t)
    _qt_translators.clear()
    if lang == "en":
        QLocale.setDefault(QLocale(QLocale.English, QLocale.UnitedStates))
        return
    QLocale.setDefault(QLocale(lang))
    try:
        path = QLibraryInfo.path(QLibraryInfo.TranslationsPath)
    except Exception:
        return
    for base in ("qtbase", "qt"):
        t = QTranslator(app)
        if t.load(f"{base}_{lang}", path):
            app.installTranslator(t)
            _qt_translators.append(t)
            break
