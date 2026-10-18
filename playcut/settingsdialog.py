"""設定視窗：把散在選單裡的選項集中在一起，再加上可調的微調間隔與快捷鍵。

設定值一律用 dict 傳進傳出（key 就是 QSettings 裡的鍵），
真正套用到播放器的工作由主視窗的 apply_prefs() 負責。
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog,
                               QDoubleSpinBox, QFileDialog, QFormLayout,
                               QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QPushButton, QRadioButton,
                               QSpinBox, QStackedWidget, QVBoxLayout, QWidget)

from . import i18n
from .i18n import N_, tr
from .shortcuts import ShortcutEditor, ShortcutEntry

# QSettings 鍵 -> 預設值（型別也由預設值決定）
DEFAULTS: Dict[str, object] = {
    # 播放
    "seekSmall": 1.0,          # 倒退 / 快轉（小），秒
    "seekMedium": 5.0,         # 倒退 / 快轉（中）
    "seekLarge": 10.0,         # 倒退 / 快轉（大）
    "speedStep": 0.1,          # 加速 / 降速一次加減多少
    "swipeSpan": 120,          # 整個螢幕寬的滑動 = 幾秒
    "pausedBadge": False,
    # 聲音
    "audioDelayStep": 10,      # 聲音延遲微調，ms
    "volumeStep": 5,           # 音量微調，%
    # 字幕
    "subDelayStep": 100,       # 字幕延遲微調，ms
    # 截圖
    "screenshotFormat": "png",
    "screenshotClipboard": False,
    "screenshotDir": "",       # 空字串 = 影片所在的資料夾
    # 畫面
    "hdrToneMapping": "hable",
    "hdrPeakDetect": True,
    "hdrBoost": True,
    # 一般
    "closeToTray": True,
    "language": "",            # 空字串 = 跟隨系統
}

# 各欄位的範圍（最小, 最大）
LIMITS = {
    "seekSmall": (0.1, 600.0), "seekMedium": (0.1, 600.0), "seekLarge": (0.1, 3600.0),
    "speedStep": (0.05, 1.0), "swipeSpan": (10, 600),
    "audioDelayStep": (1, 1000), "volumeStep": (1, 50), "subDelayStep": (10, 5000),
}

SHOT_FORMATS = [("png", "PNG"), ("jpg", "JPG")]   # 截圖格式（副檔名, 顯示名稱）
HDR_CHOICES = [
    ("hable", N_("Hable（柔和，最不易過曝，推薦）")),
    ("mobius", N_("Mobius（保留中間調，較亮）")),
    ("reinhard", N_("Reinhard（簡單壓縮亮部）")),
    ("bt.2390", N_("BT.2390（mpv 預設，較亮）")),
    ("clip", N_("不轉換（直接裁切，會過曝）")),
]


def clamp(key: str, value):
    lo, hi = LIMITS.get(key, (None, None))
    if lo is None:
        return value
    return type(DEFAULTS[key])(min(hi, max(lo, value)))


def load_prefs(settings: QSettings) -> Dict[str, object]:
    out: Dict[str, object] = {}
    for k, d in DEFAULTS.items():
        if k == "language":
            out[k] = i18n.saved_choice(settings)
            continue
        try:
            v = settings.value(k, d, type(d))
        except (TypeError, ValueError):
            v = d
        out[k] = clamp(k, v)
    return out


def _fmt_num(x: float) -> str:
    return f"{x:g}"


class SettingsDialog(QDialog):
    """左邊是分頁清單，右邊是內容；下面有「恢復本頁預設 / 確定 / 取消 / 套用」。"""

    # (偏好設定 dict, 快捷鍵 {aid: PortableText})
    applied = Signal(dict, dict)

    PAGE_PLAYBACK, PAGE_AUDIO, PAGE_SUBS, PAGE_SHOTS, PAGE_DISPLAY, \
        PAGE_GENERAL, PAGE_KEYS = range(7)

    def __init__(self, parent, prefs: Dict[str, object],
                 entries: List[ShortcutEntry], shortcuts: Dict[str, str],
                 names_for: Optional[Callable[[Dict[str, object]], Dict[str, str]]] = None,
                 page: int = 0):
        super().__init__(parent)
        self.setWindowTitle(tr("設定"))
        self.resize(820, 620)
        self.setMinimumSize(640, 480)
        self._prefs = dict(prefs)
        self._names_for = names_for
        # key -> (取值, 設值)
        self._fields: Dict[str, tuple] = {}
        self._page_keys: List[List[str]] = []

        root = QVBoxLayout(self)
        body = QHBoxLayout()
        root.addLayout(body, 1)

        self.nav = QListWidget()
        self.nav.setFixedWidth(150)
        self.nav.setStyleSheet(
            "QListWidget { background:#232830; border:1px solid #3c4450; border-radius:8px;"
            " padding:4px; outline:0; }"
            "QListWidget::item { padding:8px 10px; border-radius:6px; }"
            "QListWidget::item:selected { background:#31527f; color:#ffffff; }"
            "QListWidget::item:hover:!selected { background:#2b313b; }")
        body.addWidget(self.nav)

        self.stack = QStackedWidget()
        body.addWidget(self.stack, 1)

        self._add_page(tr("播放"), self._build_playback())
        self._add_page(tr("聲音"), self._build_audio())
        self._add_page(tr("字幕"), self._build_subs())
        self._add_page(tr("截圖"), self._build_shots())
        self._add_page(tr("畫面"), self._build_display())
        self._add_page(tr("一般"), self._build_general())
        self.keys = ShortcutEditor(self, entries, shortcuts)
        self._add_page(tr("快捷鍵"), self.keys, keys=[])
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)

        # ---- 下方按鈕 ----
        row = QHBoxLayout()
        self.btn_reset = QPushButton(tr("恢復本頁預設"))
        self.btn_reset.clicked.connect(self.reset_page)
        row.addWidget(self.btn_reset)
        row.addStretch(1)
        self.btn_ok = QPushButton(tr("確定"))
        self.btn_ok.setDefault(True)
        self.btn_ok.clicked.connect(self._ok)
        self.btn_cancel = QPushButton(tr("取消"))
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_apply = QPushButton(tr("套用"))
        self.btn_apply.clicked.connect(self.apply)
        for b in (self.btn_ok, self.btn_cancel, self.btn_apply):
            b.setAutoDefault(False)
            b.setMinimumWidth(84)
            row.addWidget(b)
        root.addLayout(row)

        self.set_values(self._prefs)
        self.nav.setCurrentRow(max(0, min(page, self.stack.count() - 1)))
        self._update_names()

    # ==================================================================
    # 建立欄位的小工具
    # ==================================================================
    def _add_page(self, title: str, widget: QWidget, keys: Optional[List[str]] = None):
        self.nav.addItem(title)
        self.stack.addWidget(widget)
        self._page_keys.append(keys if keys is not None else list(self._pending_keys))
        self._pending_keys = []

    _pending_keys: List[str] = []

    def _register(self, key: str, getter, setter):
        self._fields[key] = (getter, setter)
        self._pending_keys = self._pending_keys + [key]

    @staticmethod
    def _page() -> tuple:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(12, 0, 0, 0)
        v.setSpacing(12)
        return w, v

    @staticmethod
    def _group(title: str) -> tuple:
        g = QGroupBox(title)
        f = QFormLayout(g)
        f.setContentsMargins(12, 14, 12, 12)
        f.setHorizontalSpacing(16)
        f.setVerticalSpacing(10)
        f.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return g, f

    @staticmethod
    def _note(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("color:#9fb0c8;")
        return lbl

    def _int(self, key: str, suffix: str, step: int = 1) -> QSpinBox:
        lo, hi = LIMITS[key]
        sp = QSpinBox()
        sp.setRange(int(lo), int(hi))
        sp.setSingleStep(step)
        sp.setSuffix(suffix)
        sp.setFixedWidth(130)
        sp.valueChanged.connect(self._update_names)
        self._register(key, sp.value, lambda v, s=sp: s.setValue(int(v)))
        return sp

    def _float(self, key: str, suffix: str, step: float, decimals: int = 2,
               prefix: str = "") -> QDoubleSpinBox:
        lo, hi = LIMITS[key]
        sp = QDoubleSpinBox()
        sp.setRange(lo, hi)
        sp.setDecimals(decimals)
        sp.setSingleStep(step)
        sp.setPrefix(prefix)
        sp.setSuffix(suffix)
        sp.setFixedWidth(130)
        sp.valueChanged.connect(self._update_names)
        self._register(key, lambda s=sp: round(s.value(), decimals),
                       lambda v, s=sp: s.setValue(float(v)))
        return sp

    def _check(self, key: str, text: str) -> QCheckBox:
        cb = QCheckBox(text)
        self._register(key, cb.isChecked, lambda v, c=cb: c.setChecked(bool(v)))
        return cb

    def _combo(self, key: str, items) -> QComboBox:
        cb = QComboBox()
        for data, label in items:
            cb.addItem(label, data)
        cb.setMinimumWidth(260)

        def setter(v, c=cb):
            i = c.findData(v)
            c.setCurrentIndex(i if i >= 0 else 0)
        self._register(key, lambda c=cb: c.currentData(), setter)
        return cb

    # ==================================================================
    # 各分頁
    # ==================================================================
    def _build_playback(self) -> QWidget:
        w, v = self._page()
        sec = tr(" 秒")

        g, f = self._group(tr("倒退 / 快轉的秒數"))
        f.addRow(tr("小（預設 Shift+← / →）"), self._float("seekSmall", sec, 0.5, 1))
        f.addRow(tr("中（預設 ← / →）"), self._float("seekMedium", sec, 1, 1))
        f.addRow(tr("大（預設不指定按鍵）"), self._float("seekLarge", sec, 5, 1))
        f.addRow(self._note(tr("選單與快捷鍵的名稱會跟著這裡的秒數變。")))
        v.addWidget(g)

        g, f = self._group(tr("播放速度"))
        f.addRow(tr("加速 / 降速間隔"), self._float("speedStep", "×", 0.05, 2, prefix="± "))
        v.addWidget(g)

        g, f = self._group(tr("觸控與畫面"))
        f.addRow(tr("觸控滑動靈敏度"), self._int("swipeSpan", sec, 10))
        f.addRow(self._note(tr("手指從螢幕最左滑到最右 = 移動幾秒。數字越小越好微調。")))
        f.addRow(self._check("pausedBadge", tr("暫停時左上角顯示「已暫停」")))
        v.addWidget(g)
        v.addStretch(1)
        return w

    def _build_audio(self) -> QWidget:
        w, v = self._page()
        g, f = self._group(tr("微調間隔"))
        f.addRow(tr("聲音延遲每次調整"), self._int("audioDelayStep", " ms", 5))
        f.addRow(self._note(tr("按「聲音提早 / 延後」快捷鍵，或控制列延遲欄旁邊的 − / + 時，"
                               "每次調整的量。正值 = 聲音延後播放。")))
        f.addRow(tr("音量每次調整"), self._int("volumeStep", " %", 1))
        v.addWidget(g)
        v.addStretch(1)
        return w

    def _build_subs(self) -> QWidget:
        w, v = self._page()
        g, f = self._group(tr("微調間隔"))
        f.addRow(tr("字幕延遲每次調整"), self._int("subDelayStep", " ms", 50))
        f.addRow(self._note(tr("按「字幕提早 / 延後」快捷鍵時每次調整的量。")))
        v.addWidget(g)
        v.addStretch(1)
        return w

    def _build_shots(self) -> QWidget:
        w, v = self._page()
        g, f = self._group(tr("截圖"))
        f.addRow(tr("圖檔格式"), self._combo("screenshotFormat", SHOT_FORMATS))
        f.addRow(self._check("screenshotClipboard", tr("截圖後同時複製到剪貼簿")))
        v.addWidget(g)

        g = QGroupBox(tr("存放位置"))
        gv = QVBoxLayout(g)
        gv.setContentsMargins(12, 14, 12, 12)
        self.rb_beside = QRadioButton(tr("存到影片所在的資料夾"))
        self.rb_custom = QRadioButton(tr("存到這個資料夾："))
        grp = QButtonGroup(g)
        grp.addButton(self.rb_beside)
        grp.addButton(self.rb_custom)
        gv.addWidget(self.rb_beside)
        gv.addWidget(self.rb_custom)
        row = QHBoxLayout()
        row.setContentsMargins(24, 0, 0, 0)
        self.ed_shot_dir = QLineEdit()
        self.ed_shot_dir.setPlaceholderText(tr("選擇截圖資料夾…"))
        row.addWidget(self.ed_shot_dir, 1)
        btn = QPushButton(tr("瀏覽…"))
        btn.clicked.connect(self._browse_shot_dir)
        row.addWidget(btn)
        gv.addLayout(row)
        self.rb_custom.toggled.connect(self._sync_shot_dir_ui)
        self.ed_shot_dir.textEdited.connect(
            lambda t: t and self.rb_custom.setChecked(True))
        v.addWidget(g)

        def get_dir():
            t = self.ed_shot_dir.text().strip()
            return str(Path(t)) if self.rb_custom.isChecked() and t else ""

        def set_dir(val):
            val = str(val or "")
            self.ed_shot_dir.setText(val)
            (self.rb_custom if val else self.rb_beside).setChecked(True)
            self._sync_shot_dir_ui()
        self._register("screenshotDir", get_dir, set_dir)
        v.addStretch(1)
        return w

    def _sync_shot_dir_ui(self, *_):
        self.ed_shot_dir.setEnabled(self.rb_custom.isChecked())

    def _browse_shot_dir(self):
        start = self.ed_shot_dir.text().strip() or str(Path.home())
        d = QFileDialog.getExistingDirectory(self, tr("選擇截圖資料夾"), start)
        if d:
            self.ed_shot_dir.setText(str(Path(d)))
            self.rb_custom.setChecked(True)

    def _build_display(self) -> QWidget:
        w, v = self._page()
        g, f = self._group(tr("HDR 影片色調映射"))
        f.addRow(tr("映射方式"), self._combo(
            "hdrToneMapping", [(k, tr(label)) for k, label in HDR_CHOICES]))
        f.addRow(self._check("hdrPeakDetect", tr("動態峰值偵測（依畫面亮度自動調整）")))
        f.addRow(self._check("hdrBoost",
                             tr("HDR 色彩增強（補回飽和度與對比，較接近 PotPlayer）")))
        v.addWidget(g)
        v.addStretch(1)
        return w

    def _build_general(self) -> QWidget:
        w, v = self._page()
        title = tr("語言")
        if i18n.current_language() != "en":
            title += " / Language"
        g, f = self._group(title)
        items = [("", tr("跟隨系統"))] + list(i18n.LANGUAGES)
        f.addRow(tr("介面語言"), self._combo("language", items))
        f.addRow(self._note(tr("切換語言需要重新啟動 PlayCut。")))
        v.addWidget(g)

        g, f = self._group(tr("視窗"))
        cb = self._check("closeToTray", tr("關閉視窗時縮到系統匣（開啟更快）"))
        f.addRow(cb)
        if sys.platform != "win32":
            g.setVisible(False)
        v.addWidget(g)
        v.addStretch(1)
        return w

    # ==================================================================
    # 讀寫
    # ==================================================================
    def values(self) -> Dict[str, object]:
        out = dict(self._prefs)
        for k, (get, _set) in self._fields.items():
            out[k] = get()
        return out

    def set_values(self, prefs: Dict[str, object]):
        for k, (_get, put) in self._fields.items():
            if k in prefs:
                put(prefs[k])

    def shortcut_values(self) -> Dict[str, str]:
        return self.keys.values()

    def reset_page(self):
        i = self.stack.currentIndex()
        if i == self.PAGE_KEYS:
            self.keys.reset_all()
            return
        self.set_values({k: DEFAULTS[k] for k in self._page_keys[i]})

    def _update_names(self, *_):
        """秒數 / 間隔一改，快捷鍵頁的功能名稱就跟著變。"""
        if self._names_for is None or not hasattr(self, "keys"):
            return
        self.keys.set_names(self._names_for(self.values()))

    def apply(self) -> bool:
        if not self.keys.check_ok(self):
            self.nav.setCurrentRow(self.PAGE_KEYS)
            return False
        self._prefs = self.values()
        self.applied.emit(dict(self._prefs), self.shortcut_values())
        return True

    def _ok(self):
        if self.apply():
            self.accept()


__all__ = ["DEFAULTS", "HDR_CHOICES", "LIMITS", "SHOT_FORMATS", "SettingsDialog",
           "clamp", "load_prefs"]
