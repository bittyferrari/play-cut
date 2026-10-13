"""自訂快捷鍵：設定存取 + 設定對話框。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor, QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox,
                               QHBoxLayout, QHeaderView, QKeySequenceEdit,
                               QLabel, QLineEdit, QMessageBox, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout)

from .i18n import tr

SETTINGS_GROUP = "shortcuts"


@dataclass
class ShortcutEntry:
    aid: str          # 穩定的識別碼，存設定用
    category: str     # 選單名稱，例如「播放」
    text: str         # 功能名稱
    default: str      # 預設快捷鍵（PortableText），可為空字串


def seq_text(s: str) -> str:
    """把 PortableText 轉成給人看的文字。"""
    return QKeySequence(s).toString(QKeySequence.NativeText) if s else ""


def load_overrides(settings: QSettings) -> Dict[str, str]:
    out: Dict[str, str] = {}
    settings.beginGroup(SETTINGS_GROUP)
    for k in settings.childKeys():
        v = settings.value(k, "", str)
        out[k] = v or ""
    settings.endGroup()
    return out


def save_overrides(settings: QSettings, entries: List[ShortcutEntry],
                   current: Dict[str, str]):
    """只把「跟預設不同」的存起來，預設值之後改了也會跟著更新。"""
    settings.beginGroup(SETTINGS_GROUP)
    settings.remove("")
    for e in entries:
        cur = current.get(e.aid, e.default)
        if QKeySequence(cur) != QKeySequence(e.default):
            settings.setValue(e.aid, cur)
    settings.endGroup()


def find_conflicts(entries: List[ShortcutEntry],
                   current: Dict[str, str]) -> Dict[str, List[str]]:
    """回傳 {按鍵文字: [衝突的功能名稱, ...]}。"""
    by_key: Dict[str, List[str]] = {}
    for e in entries:
        s = current.get(e.aid, "")
        if not s:
            continue
        key = QKeySequence(s).toString(QKeySequence.PortableText)
        by_key.setdefault(key, []).append(f"{e.category} → {e.text}")
    return {k: v for k, v in by_key.items() if len(v) > 1}


class ShortcutDialog(QDialog):
    COL_CAT, COL_NAME, COL_KEY, COL_DEFAULT = range(4)

    def __init__(self, parent, entries: List[ShortcutEntry],
                 current: Dict[str, str]):
        super().__init__(parent)
        self.setWindowTitle(tr("自訂快捷鍵"))
        self.resize(640, 620)
        self.entries = entries
        self._edits: Dict[str, QKeySequenceEdit] = {}

        v = QVBoxLayout(self)
        tip = QLabel(tr("點一下「快捷鍵」欄位，直接按下想要的按鍵組合即可。"
                     "清空 = 不指定快捷鍵。重複的按鍵會標成紅色。"))
        tip.setWordWrap(True)
        tip.setStyleSheet("color:#9fb0c8;")
        v.addWidget(tip)

        self.filter = QLineEdit()
        self.filter.setPlaceholderText(tr("搜尋功能或按鍵…"))
        self.filter.setClearButtonEnabled(True)
        self.filter.textChanged.connect(self._apply_filter)
        v.addWidget(self.filter)

        self.tbl = QTableWidget(len(entries), 4)
        self.tbl.setHorizontalHeaderLabels([tr("分類"), tr("功能"), tr("快捷鍵"), tr("預設")])
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        hh = self.tbl.horizontalHeader()
        hh.setSectionResizeMode(self.COL_CAT, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(self.COL_NAME, QHeaderView.Stretch)
        hh.setSectionResizeMode(self.COL_KEY, QHeaderView.Fixed)
        hh.setSectionResizeMode(self.COL_DEFAULT, QHeaderView.ResizeToContents)
        self.tbl.setColumnWidth(self.COL_KEY, 170)

        for r, e in enumerate(entries):
            for c, text in ((self.COL_CAT, e.category), (self.COL_NAME, e.text),
                            (self.COL_DEFAULT, seq_text(e.default) or "—")):
                it = QTableWidgetItem(text)
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                self.tbl.setItem(r, c, it)
            ed = QKeySequenceEdit(QKeySequence(current.get(e.aid, e.default)))
            ed.setMaximumSequenceLength(1)
            ed.setClearButtonEnabled(True)
            le = ed.findChild(QLineEdit)
            if le is not None:
                le.setPlaceholderText(tr("按下按鍵…"))
            ed.keySequenceChanged.connect(self._update_conflicts)
            self.tbl.setCellWidget(r, self.COL_KEY, ed)
            self._edits[e.aid] = ed
        self.tbl.verticalHeader().setDefaultSectionSize(34)
        v.addWidget(self.tbl, 1)

        self.lbl_conflict = QLabel("")
        self.lbl_conflict.setWordWrap(True)
        self.lbl_conflict.setStyleSheet("color:#f06e6e;")
        v.addWidget(self.lbl_conflict)

        row = QHBoxLayout()
        b = QPushButton(tr("此項恢復預設"))
        b.clicked.connect(self._reset_selected)
        row.addWidget(b)
        b = QPushButton(tr("全部恢復預設"))
        b.clicked.connect(self._reset_all)
        row.addWidget(b)
        row.addStretch(1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("套用"))
        bb.button(QDialogButtonBox.Cancel).setText(tr("取消"))
        bb.accepted.connect(self._try_accept)
        bb.rejected.connect(self.reject)
        row.addWidget(bb)
        v.addLayout(row)

        self._update_conflicts()

    # ------------------------------------------------------------------
    def values(self) -> Dict[str, str]:
        return {aid: ed.keySequence().toString(QKeySequence.PortableText)
                for aid, ed in self._edits.items()}

    def _reset_selected(self):
        r = self.tbl.currentRow()
        if 0 <= r < len(self.entries):
            e = self.entries[r]
            self._edits[e.aid].setKeySequence(QKeySequence(e.default))

    def _reset_all(self):
        for e in self.entries:
            self._edits[e.aid].setKeySequence(QKeySequence(e.default))

    def _apply_filter(self, text: str):
        t = text.strip().lower()
        for r, e in enumerate(self.entries):
            key = self._edits[e.aid].keySequence().toString(QKeySequence.NativeText)
            hay = f"{e.category} {e.text} {key}".lower()
            self.tbl.setRowHidden(r, bool(t) and t not in hay)

    def _update_conflicts(self, *_):
        conflicts = find_conflicts(self.entries, self.values())
        bad = set()
        for names in conflicts.values():
            bad.update(names)
        for r, e in enumerate(self.entries):
            color = QColor("#f06e6e") if f"{e.category} → {e.text}" in bad else QColor("#e6ecf5")
            for c in (self.COL_CAT, self.COL_NAME):
                self.tbl.item(r, c).setForeground(color)
        if conflicts:
            lines = [seq_text(k) + tr("：") + tr("、").join(v) for k, v in conflicts.items()]
            self.lbl_conflict.setText(tr("按鍵重複：\n") + "\n".join(lines))
        else:
            self.lbl_conflict.setText("")
        return conflicts

    def _try_accept(self):
        if self._update_conflicts():
            QMessageBox.warning(self, tr("快捷鍵重複"),
                                tr("有功能用了同一個按鍵，請先修正紅色標示的項目。"))
            return
        self.accept()
