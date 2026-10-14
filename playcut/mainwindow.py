"""PlayCut 主視窗。"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import (QEvent, QRectF, QSettings, QSize, QStandardPaths, Qt,
                            QTimer, QUrl, Signal)
from PySide6.QtGui import (QAction, QActionGroup, QColor, QCursor, QDesktopServices, QFont, QIcon,
                           QImage, QKeySequence, QPainter,
                           QPainterPath, QPalette, QPixmap)
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox,
                               QComboBox, QDockWidget, QDoubleSpinBox,
                               QFileDialog, QHBoxLayout, QHeaderView, QLabel,
                               QMainWindow, QMenu, QMessageBox, QPushButton,
                               QSizePolicy, QSlider, QStyle, QTableWidget,
                               QTableWidgetItem, QToolBar, QToolButton, QVBoxLayout,
                               QWidget)

from . import exporter as EX
from . import subtitles as SUB
from .exportdialog import ExportDialog
from .ffio import Tools, fmt_time, parse_time, probe
from .markers import ROLE_AUTO, ROLE_IN, ROLE_OUT, MarkerList
from .shortcuts import (ShortcutDialog, ShortcutEntry, load_overrides,
                        save_overrides, seq_text)
from .timeline import Timeline
from .videoview import VideoView
from . import i18n
from . import keepawake
from . import winmax
from .i18n import N_, tr, tr_for

VIDEO_FILTER = N_("影片檔 (*.mp4 *.mkv *.mov *.avi *.wmv *.flv *.webm *.ts *.m2ts "
                "*.mpg *.mpeg *.m4v *.rmvb *.3gp *.vob *.ogv);;所有檔案 (*.*)")

SPEEDS = [0.25, 0.5, 0.75, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 4.0,
          5.0, 6.0, 8.0, 10.0]
MIN_SPEED, MAX_SPEED = 0.1, 10.0
SPEED_STEPS = [0.1, 0.2, 0.25, 0.5]   # 加速 / 降速一次加減多少
SHOT_FORMATS = [("png", "PNG"), ("jpg", "JPG")]   # 截圖格式（副檔名, 顯示名稱）

DARK_QSS = """
QMainWindow, QWidget { background:#1e222a; color:#e6ecf5; }
QDockWidget::title { background:#262b34; padding:6px; }
QToolButton, QPushButton {
    background:#2f3540; border:1px solid #3c4450; border-radius:6px;
    padding:5px 10px; color:#e6ecf5;
}
QToolButton:hover, QPushButton:hover { background:#3a424f; }
QToolButton:pressed, QPushButton:pressed { background:#4a5364; }
QComboBox, QDoubleSpinBox, QSpinBox, QLineEdit {
    background:#2a2f38; border:1px solid #3c4450; border-radius:6px;
    padding:4px 6px; color:#e6ecf5; selection-background-color:#3f7fd0;
}
QComboBox QAbstractItemView { background:#2a2f38; color:#e6ecf5;
    selection-background-color:#3f7fd0; }
QTableWidget { background:#232830; gridline-color:#39404c;
    selection-background-color:#31527f; alternate-background-color:#262c35; }
QHeaderView::section { background:#2b313b; color:#c7d2e0; border:0;
    padding:5px; }
QSlider::groove:horizontal { height:6px; background:#3a414d; border-radius:3px; }
QSlider::handle:horizontal { background:#88b7ff; width:14px; margin:-5px 0;
    border-radius:7px; }
QProgressBar { background:#2a2f38; border:1px solid #3c4450; border-radius:6px;
    text-align:center; }
QProgressBar::chunk { background:#4a90e2; border-radius:5px; }
QGroupBox { border:1px solid #3c4450; border-radius:8px; margin-top:10px;
    padding-top:10px; }
QGroupBox::title { subcontrol-origin:margin; left:10px; padding:0 4px;
    color:#9fb0c8; }
QMenuBar { background:#1e222a; } QMenuBar::item:selected { background:#333a45; }
QMenu { background:#262b34; border:1px solid #3c4450; }
QMenu::item:selected { background:#3f7fd0; }
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PlayCut")
        self.resize(1280, 780)
        self.setMinimumSize(940, 560)
        self.setAcceptDrops(True)

        self.settings = QSettings("PlayCut", "PlayCut")
        self.markers = MarkerList()
        self._placed_markers: list = []   # 依放置順序記錄，給 Ctrl+Z 復原用
        self.current_file = ""
        self._media_info = None
        self._was_paused_before_scrub = False
        self._updating_ui = False
        # 快捷鍵：aid -> (QAction, ShortcutEntry)
        self._actions: dict[str, tuple[QAction, ShortcutEntry]] = {}
        self._shortcut_overrides = load_overrides(self.settings)
        # 按鈕上的提示文字會顯示目前的快捷鍵，改鍵後要跟著更新
        self._hints: list = []
        # 影片還在載入時先收下的字幕檔，等 file-loaded 再掛上去
        self._pending_subs: list[str] = []

        self.video = VideoView(self)
        self.video.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.timeline = Timeline(self)
        self.timeline.set_markers(self.markers)

        self.setCentralWidget(self.video)

        # 進度條與控制列放在底部工具列：這樣它們會橫跨整個視窗寬度，
        # 不會被右邊的旗標面板擠到變形。
        bottom = QWidget()
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(0)
        bl.addWidget(self.timeline)
        bl.addWidget(self._build_controls())
        self.bottom_bar = QToolBar(tr("控制列"))
        self.bottom_bar.setObjectName("bottomBar")
        self.bottom_bar.setMovable(False)
        self.bottom_bar.setFloatable(False)
        self.bottom_bar.addWidget(bottom)
        self.addToolBar(Qt.BottomToolBarArea, self.bottom_bar)

        self._build_marker_dock()
        self._build_menu()
        self._wire()
        self._restore_settings()
        self._refresh_shortcut_hints()

        # 全螢幕：滑鼠不動 2 秒就隱藏指標（一動就出現），並避免螢幕關閉
        self._fs_extras = False
        self._cursor_hidden = False
        self._last_cursor_pos = None
        self._cursor_timer = QTimer(self)
        self._cursor_timer.setSingleShot(True)
        self._cursor_timer.setInterval(2000)
        self._cursor_timer.timeout.connect(self._hide_cursor)
        QApplication.instance().installEventFilter(self)

        self.statusBar().showMessage(tr("拖一個影片檔進來，或按 Ctrl+O 開啟"))
        if not Tools.available():
            QTimer.singleShot(300, self._warn_no_ffmpeg)

    # ==================================================================
    # 介面
    # ==================================================================
    def _icon(self, sp):
        return self.style().standardIcon(sp)

    def _build_controls(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(52)
        h = QHBoxLayout(bar)
        h.setContentsMargins(8, 6, 8, 6)
        h.setSpacing(5)

        self.btn_play = QToolButton()
        self.btn_play.setObjectName("btnPlay")
        self.btn_play.setFixedSize(46, 38)
        self.btn_play.setIconSize(QSize(22, 22))
        self._set_play_button(True)
        self._hint(self.btn_play, tr("播放 / 暫停"), "play_pause")
        self.btn_play.clicked.connect(self.video.toggle_pause)
        h.addWidget(self.btn_play)

        for text, tip, aid, fwd in (("◀|", tr("上一格"), "prev_frame", False),
                                    ("|▶", tr("下一格"), "next_frame", True)):
            b = QToolButton()
            b.setText(text)
            self._hint(b, tip, aid)
            b.clicked.connect(lambda _=False, f=fwd: self.video.frame_step(f))
            h.addWidget(b)

        self.lbl_time = QLabel("00:00:00.000 / 00:00:00.000")
        f = QFont({"win32": "Consolas", "darwin": "Menlo"}.get(sys.platform, "monospace"))
        f.setPointSize(10)
        self.lbl_time.setFont(f)
        self.lbl_time.setMinimumWidth(212)
        h.addWidget(self.lbl_time)

        h.addSpacing(6)
        self.cmb_speed = QComboBox()
        self.cmb_speed.setEditable(True)
        self.cmb_speed.setToolTip(tr("播放速度"))
        self.cmb_speed.setFixedWidth(78)
        for s in SPEEDS:
            self.cmb_speed.addItem(f"{s:g}×", s)
        self.cmb_speed.setCurrentIndex(SPEEDS.index(1.0))
        self.cmb_speed.activated.connect(self._speed_from_combo)
        self.cmb_speed.lineEdit().editingFinished.connect(self._speed_from_text)
        h.addWidget(self.cmb_speed)

        b = QToolButton(); b.setText("−"); self._hint(b, tr("降速"), "speed_down")
        b.clicked.connect(lambda: self._nudge_speed(-1))
        h.addWidget(b)
        b = QToolButton(); b.setText("+"); self._hint(b, tr("加速"), "speed_up")
        b.clicked.connect(lambda: self._nudge_speed(1))
        h.addWidget(b)
        b = QToolButton(); b.setText("1×"); self._hint(b, tr("恢復正常速度"), "speed_reset")
        b.clicked.connect(lambda: self.video.set_speed(1.0))
        h.addWidget(b)

        h.addSpacing(10)
        lbl_d = QLabel(tr("延遲"))
        lbl_d.setToolTip(tr("聲音延遲校正"))
        h.addWidget(lbl_d)
        self.spn_delay = QDoubleSpinBox()
        self.spn_delay.setRange(-10000, 10000)
        self.spn_delay.setDecimals(0)
        self.spn_delay.setSingleStep(10)
        self.spn_delay.setSuffix(" ms")
        self.spn_delay.setFixedWidth(92)
        self._hints.append(lambda: self.spn_delay.setToolTip(
            tr("正值 = 聲音延後播放。")
            + tr("{a} / {b} 可快速調整 ±50ms",
                 a=self._key('audio_earlier') or tr('（未設定）'),
                 b=self._key('audio_later') or tr('（未設定）'))))
        self.spn_delay.valueChanged.connect(self._delay_changed)
        h.addWidget(self.spn_delay)
        b = QToolButton(); b.setText("0"); b.setToolTip(tr("聲音延遲歸零"))
        b.clicked.connect(lambda: self.spn_delay.setValue(0))
        h.addWidget(b)

        h.addStretch(1)

        self.btn_mute = QToolButton()
        self.btn_mute.setIcon(self._icon(QStyle.SP_MediaVolume))
        self.btn_mute.setCheckable(True)
        self.btn_mute.toggled.connect(self._toggle_mute)
        h.addWidget(self.btn_mute)
        self.sld_vol = QSlider(Qt.Horizontal)
        self.sld_vol.setRange(0, 150)
        self.sld_vol.setValue(100)
        self.sld_vol.setFixedWidth(92)
        self.sld_vol.setMinimumWidth(60)
        self.sld_vol.valueChanged.connect(self.video.set_volume)
        h.addWidget(self.sld_vol)

        h.addSpacing(6)
        self.menu_sub_tracks = QMenu(tr("字幕軌"), self)
        self.menu_sub_tracks.aboutToShow.connect(self._populate_sub_menu)
        self.btn_sub = QToolButton()
        self.btn_sub.setText(tr("字幕"))
        self.btn_sub.setToolTip(tr("選擇字幕軌 / 載入字幕檔"))
        self.btn_sub.setPopupMode(QToolButton.InstantPopup)
        self.btn_sub.setMenu(self.menu_sub_tracks)
        h.addWidget(self.btn_sub)

        # 截圖：按下去 = 含字幕；右邊的小箭頭可以選「只有影片畫面」
        self.btn_shot = QToolButton()
        self.btn_shot.setText("📷")
        self.btn_shot.setPopupMode(QToolButton.MenuButtonPopup)
        self._hint(self.btn_shot, tr("截圖（含字幕）。按右邊的箭頭可以只截影片畫面"),
                   "screenshot_sub")
        self.btn_shot.clicked.connect(lambda: self.take_screenshot(True))
        h.addWidget(self.btn_shot)

        h.addSpacing(10)
        self.btn_flag = QPushButton(tr("🚩 旗標"))
        self._hint(self.btn_flag, tr("在目前位置插入旗標"), "add_marker")
        self.btn_flag.clicked.connect(self.add_marker)
        h.addWidget(self.btn_flag)

        self.btn_export = QPushButton(tr("匯出"))
        self._hint(self.btn_export, tr("依旗標匯出片段"), "export")
        self.btn_export.clicked.connect(self.export_segments)
        h.addWidget(self.btn_export)

        b = QToolButton()
        b.setText("⛶")
        self._hint(b, tr("全螢幕（播放畫面按滑鼠中鍵也可以）"), "fullscreen")
        b.clicked.connect(self.toggle_fullscreen)
        h.addWidget(b)
        return bar

    def _build_marker_dock(self):
        dock = QDockWidget(tr("旗標"), self)
        dock.setObjectName("markerDock")
        dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 8, 8, 8)

        self.tbl = QTableWidget(0, 4)
        self.tbl.setHorizontalHeaderLabels(["#", tr("角色"), tr("時間"), tr("備註")])
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setAlternatingRowColors(True)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl.setEditTriggers(QAbstractItemView.DoubleClicked |
                                 QAbstractItemView.SelectedClicked)
        hh = self.tbl.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.Stretch)
        self.tbl.itemDoubleClicked.connect(self._marker_double_clicked)
        self.tbl.itemChanged.connect(self._marker_edited)
        v.addWidget(self.tbl, 1)

        row1 = QHBoxLayout()
        for text, tip, aid, fn in (
            (tr("＋旗標"), tr("在目前位置插入旗標"), "add_marker", self.add_marker),
            (tr("起點"), tr("把目前位置設成片段起點"), "set_in",
             lambda: self.add_marker(ROLE_IN)),
            (tr("終點"), tr("把目前位置設成片段終點"), "set_out",
             lambda: self.add_marker(ROLE_OUT)),
        ):
            b = QPushButton(text)
            self._hint(b, tip, aid, label=text)
            b.clicked.connect(fn)
            row1.addWidget(b)
        v.addLayout(row1)

        row2 = QHBoxLayout()
        for text, tip, aid, fn in (
            (tr("跳到"), tr("跳到選取的旗標"), "", self.goto_selected_marker),
            (tr("刪除"), tr("刪除選取的旗標"), "delete_marker", self.delete_selected_markers),
            (tr("切換角色"), tr("在 起點 / 終點 / 自動 之間切換"), "", self.toggle_selected_role),
            (tr("清空"), tr("刪除全部旗標"), "", self.clear_markers),
        ):
            b = QPushButton(text)
            if aid:
                self._hint(b, tip, aid)
            else:
                b.setToolTip(tip)
            b.clicked.connect(fn)
            row2.addWidget(b)
        v.addLayout(row2)

        self.lbl_segments = QLabel(tr("尚無片段"))
        self.lbl_segments.setWordWrap(True)
        self.lbl_segments.setStyleSheet(
            "color:#9fb0c8; background:#232830; border:1px solid #39404c;"
            "border-radius:6px; padding:8px;")
        v.addWidget(self.lbl_segments)

        self.chk_autosave = QCheckBox(tr("自動存檔旗標（影片旁的 .playcut.json）"))
        self.chk_autosave.setChecked(False)
        v.addWidget(self.chk_autosave)

        self.tbl.setMinimumWidth(230)
        self.lbl_segments.setMinimumWidth(200)
        w.setMinimumWidth(250)
        dock.setWidget(w)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)
        self.resizeDocks([dock], [330], Qt.Horizontal)
        self.marker_dock = dock

    def _build_menu(self):
        mb = self.menuBar()

        C = tr("檔案")
        m = mb.addMenu(tr("檔案(&F)"))
        self._act(m, C, "open", tr("開啟影片…"), "Ctrl+O", self.open_file)
        m.addSeparator()
        self._act(m, C, "load_flags", tr("載入旗標檔…"), "", self.load_markers_file)
        self._act(m, C, "save_flags", tr("另存旗標檔…"), "Ctrl+S", self.save_markers_file)
        self._act(m, C, "export_csv", tr("匯出旗標為 CSV…"), "", self.export_markers_csv)
        m.addSeparator()
        self._act(m, C, "export", tr("匯出片段…"), "Ctrl+E", self.export_segments)
        m.addSeparator()
        if sys.platform == "win32":
            self.act_close_to_tray = m.addAction(tr("關閉視窗時縮到系統匣（開啟更快）"))
            self.act_close_to_tray.setCheckable(True)
            self.act_close_to_tray.setChecked(self.settings.value("closeToTray", True, bool))
            self.act_close_to_tray.toggled.connect(
                lambda on: self.settings.setValue("closeToTray", on))
        self._act(m, C, "quit", tr("離開"), "Ctrl+Q", self.quit_app)

        C = tr("播放")
        m = mb.addMenu(tr("播放(&P)"))
        self._act(m, C, "play_pause", tr("播放 / 暫停"), "Space", self.video.toggle_pause)
        self._act(m, C, "back5", tr("倒退 5 秒"), "Left", lambda: self.video.seek_relative(-5))
        self._act(m, C, "fwd5", tr("快轉 5 秒"), "Right", lambda: self.video.seek_relative(5))
        self._act(m, C, "back1", tr("倒退 1 秒"), "Shift+Left",
                  lambda: self.video.seek_relative(-1))
        self._act(m, C, "fwd1", tr("快轉 1 秒"), "Shift+Right",
                  lambda: self.video.seek_relative(1))
        self._act(m, C, "back10", tr("倒退 10 秒"), "", lambda: self.video.seek_relative(-10))
        self._act(m, C, "fwd10", tr("快轉 10 秒"), "", lambda: self.video.seek_relative(10))
        self._act(m, C, "prev_frame", tr("上一格"), ",", lambda: self.video.frame_step(False))
        self._act(m, C, "next_frame", tr("下一格"), ".", lambda: self.video.frame_step(True))
        m.addSeparator()
        self._act(m, C, "speed_down", tr("降速"), "[", lambda: self._nudge_speed(-1))
        self._act(m, C, "speed_up", tr("加速"), "]", lambda: self._nudge_speed(1))
        self._act(m, C, "speed_reset", tr("恢復 1×"), "Backspace",
                  lambda: self.video.set_speed(1.0))
        m.addSeparator()
        self._act(m, C, "vol_up", tr("音量 +5"), "", lambda: self._nudge_volume(5))
        self._act(m, C, "vol_down", tr("音量 −5"), "", lambda: self._nudge_volume(-5))
        self._act(m, C, "mute", tr("靜音"), "", self.btn_mute.toggle)
        m.addSeparator()
        self._act(m, C, "audio_earlier", tr("聲音提早 50ms"), "Ctrl+Left",
                  lambda: self.spn_delay.setValue(self.spn_delay.value() - 50))
        self._act(m, C, "audio_later", tr("聲音延後 50ms"), "Ctrl+Right",
                  lambda: self.spn_delay.setValue(self.spn_delay.value() + 50))
        m.addSeparator()
        self._act(m, C, "fullscreen", tr("全螢幕"), "F", self.toggle_fullscreen)
        self._act(m, C, "exit_fullscreen", tr("離開全螢幕"), "Esc", self.exit_fullscreen)

        C = tr("字幕")
        m = mb.addMenu(tr("字幕(&S)"))
        self._act(m, C, "load_sub", tr("載入字幕檔…"), "Ctrl+L", self.open_subtitle_file)
        m.addMenu(self.menu_sub_tracks)
        self._act(m, C, "cycle_sub", tr("切換字幕軌"), "J", self.cycle_subtitle)
        self._act(m, C, "toggle_sub", tr("顯示 / 隱藏字幕"), "V", self.toggle_subtitle)
        m.addSeparator()
        self._act(m, C, "sub_earlier", tr("字幕提早 100ms"), "Z",
                  lambda: self._nudge_sub_delay(-0.1))
        self._act(m, C, "sub_later", tr("字幕延後 100ms"), "X",
                  lambda: self._nudge_sub_delay(0.1))
        self._act(m, C, "sub_delay_reset", tr("字幕延遲歸零"), "Shift+Z",
                  lambda: self._set_sub_delay(0.0))
        m.addSeparator()
        self._act(m, C, "sub_bigger", tr("字幕放大"), "Alt+Up",
                  lambda: self._nudge_sub_scale(0.1))
        self._act(m, C, "sub_smaller", tr("字幕縮小"), "Alt+Down",
                  lambda: self._nudge_sub_scale(-0.1))
        self._act(m, C, "sub_up", tr("字幕位置上移"), "Alt+Shift+Up",
                  lambda: self._nudge_sub_pos(-2))
        self._act(m, C, "sub_down", tr("字幕位置下移"), "Alt+Shift+Down",
                  lambda: self._nudge_sub_pos(2))
        self._act(m, C, "sub_style_reset", tr("字幕大小 / 位置恢復預設"), "",
                  self._reset_sub_style)

        C = tr("截圖")
        m = mb.addMenu(tr("截圖(&C)"))
        a_sub = self._act(m, C, "screenshot_sub", tr("截圖（含字幕）"), "S",
                          lambda: self.take_screenshot(True))
        a_vid = self._act(m, C, "screenshot_video", tr("截圖（只有影片畫面）"), "Shift+S",
                          lambda: self.take_screenshot(False))
        m.addSeparator()
        self.act_shot_clip = m.addAction(tr("截圖後同時複製到剪貼簿"))
        self.act_shot_clip.setCheckable(True)
        self.act_shot_clip.toggled.connect(
            lambda on: self.settings.setValue("screenshotClipboard", bool(on)))
        sub = m.addMenu(tr("圖檔格式"))
        group = QActionGroup(self)
        group.setExclusive(True)
        for ext, name in SHOT_FORMATS:
            a = sub.addAction(name)
            a.setCheckable(True)
            a.setData(ext)
            group.addAction(a)
        group.triggered.connect(
            lambda a: self.settings.setValue("screenshotFormat", a.data()))
        self._shot_fmt_menu = sub
        m.addSeparator()
        self.act_shot_beside = m.addAction(tr("存到影片所在的資料夾"))
        self.act_shot_beside.setCheckable(True)
        self.act_shot_beside.triggered.connect(self._shot_use_video_dir)
        self.act_shot_choose = m.addAction(tr("選擇截圖資料夾…"))
        self.act_shot_choose.triggered.connect(self.choose_screenshot_dir)
        a = m.addAction(tr("開啟截圖資料夾"))
        a.triggered.connect(self.open_screenshot_dir)
        pop = QMenu(self)
        pop.addAction(a_sub)
        pop.addAction(a_vid)
        self.btn_shot.setMenu(pop)

        C = tr("旗標")
        m = mb.addMenu(tr("旗標(&M)"))
        self._act(m, C, "add_marker", tr("插入旗標"), "M", self.add_marker)
        self._act(m, C, "set_in", tr("設為起點"), "I", lambda: self.add_marker(ROLE_IN))
        self._act(m, C, "set_out", tr("設為終點"), "O", lambda: self.add_marker(ROLE_OUT))
        self._act(m, C, "prev_marker", tr("跳到上一個旗標"), "PgUp", self.goto_prev_marker)
        self._act(m, C, "next_marker", tr("跳到下一個旗標"), "PgDown", self.goto_next_marker)
        self._act(m, C, "delete_marker", tr("刪除選取旗標"), "Delete",
                  self.delete_selected_markers)
        self._act(m, C, "undo_marker", tr("復原：移除最後放置的旗標"), "Ctrl+Z",
                  self.undo_last_marker)

        C = tr("檢視")
        m = mb.addMenu(tr("檢視(&V)"))
        # 用 dock 內建的 toggleViewAction：面板用右上角 X 關掉時，勾勾會自動同步
        act = self.marker_dock.toggleViewAction()
        act.setText(tr("顯示旗標面板"))
        m.addAction(act)
        self.act_dock = act
        m.addSeparator()
        sub = m.addMenu(tr("觸控滑動靈敏度（整個螢幕寬 = ？秒）"))
        for sec in (30, 60, 90, 120, 180, 300):
            a = sub.addAction(tr("{n} 秒", n=sec))
            a.setData(sec)
            a.setCheckable(True)
            a.setChecked(sec == 120)
            a.triggered.connect(lambda _=False, s=sec: self._set_swipe_span(s, sub))
        self._swipe_menu = sub
        self.act_paused_badge = m.addAction(tr("暫停時左上角顯示「已暫停」"))
        self.act_paused_badge.setCheckable(True)
        self.act_paused_badge.toggled.connect(self._set_paused_badge)
        sub = m.addMenu(tr("加速 / 降速間隔"))
        for st in SPEED_STEPS:
            a = sub.addAction(f"± {st:g}×")
            a.setCheckable(True)
            a.setData(st)
            a.triggered.connect(lambda _=False, v=st: self._set_speed_step(v))
        self._speed_step_menu = sub
        self._speed_step = 0.1
        m.addSeparator()
        sub = m.addMenu(tr("HDR 影片色調映射"))
        group = QActionGroup(self)
        group.setExclusive(True)
        for mode, label in (
            ("hable", tr("Hable（柔和，最不易過曝，推薦）")),
            ("mobius", tr("Mobius（保留中間調，較亮）")),
            ("reinhard", tr("Reinhard（簡單壓縮亮部）")),
            ("bt.2390", tr("BT.2390（mpv 預設，較亮）")),
            ("clip", tr("不轉換（直接裁切，會過曝）")),
        ):
            a = sub.addAction(label)
            a.setCheckable(True)
            a.setData(mode)
            group.addAction(a)
        group.triggered.connect(lambda a: self._set_hdr_mode(a.data()))
        sub.addSeparator()
        self.act_hdr_peak = sub.addAction(tr("動態峰值偵測（依畫面亮度自動調整）"))
        self.act_hdr_peak.setCheckable(True)
        self.act_hdr_peak.toggled.connect(lambda on: self._set_hdr_peak(on))
        self.act_hdr_boost = sub.addAction(tr("HDR 色彩增強（補回飽和度與對比，較接近 PotPlayer）"))
        self.act_hdr_boost.setCheckable(True)
        self.act_hdr_boost.toggled.connect(lambda on: self._set_hdr_boost(on))
        self._hdr_menu = sub
        m.addSeparator()
        self._act(m, C, "customize_shortcuts", tr("自訂快捷鍵…"), "",
                  self.customize_shortcuts)
        m.addSeparator()
        self._build_language_menu(m)

        C = tr("說明")
        m = mb.addMenu(tr("說明(&H)"))
        self._act(m, C, "help", tr("快速鍵與手勢"), "F1", self.show_help)
        self._act(m, C, "about", tr("關於"), "", self.show_about)

    # 語言 -------------------------------------------------------------
    def _build_language_menu(self, parent: QMenu):
        # 選單標題一律附上英文，選錯看不懂的語言時也找得回來
        title = tr("語言")
        if i18n.current_language() != "en":
            title += " / Language"
        sub = parent.addMenu(title)
        group = QActionGroup(self)
        group.setExclusive(True)
        choice = i18n.saved_choice(self.settings)
        items = [("", tr("跟隨系統"))] + list(i18n.LANGUAGES)
        for i, (code, name) in enumerate(items):
            a = sub.addAction(name)
            a.setCheckable(True)
            a.setData(code)
            a.setChecked(code == choice)
            group.addAction(a)
            if i == 0:
                sub.addSeparator()
        group.triggered.connect(self._language_chosen)
        self._lang_menu = sub

    def _language_chosen(self, act: QAction):
        choice = act.data() or ""
        if choice == i18n.saved_choice(self.settings):
            return
        i18n.save_choice(self.settings, choice)
        self.settings.sync()
        new = choice or i18n.detect_system_language()
        cur = i18n.current_language()
        if new == cur:
            self.statusBar().showMessage(tr("語言設定已儲存"), 3000)
            return

        def both(text: str) -> str:
            # 用「新語言」為主，後面附上目前語言，兩邊的人都看得懂
            a, b = tr_for(new, text), tr(text)
            return a if a == b else f"{a} / {b}"

        key = N_("介面語言會在重新啟動 PlayCut 後切換。要現在重新啟動嗎？")
        msg = tr_for(new, key)
        if tr(key) != msg:
            msg += "\n\n" + tr(key)
        box = QMessageBox(QMessageBox.Question, both(N_("語言")), msg, parent=self)
        btn_now = box.addButton(both(N_("立即重新啟動")), QMessageBox.AcceptRole)
        box.addButton(both(N_("稍後")), QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is btn_now:
            self.restart_app()

    def restart_app(self):
        """關掉目前視窗（會照常存檔），再用同樣的方式啟動一個新的 PlayCut。"""
        from PySide6.QtCore import QProcess
        if getattr(sys, "frozen", False):
            args = []
        else:
            script = sys.argv[0] if sys.argv and sys.argv[0] else ""
            args = [script] if script and os.path.exists(script) else ["-m", "playcut"]
        args += [a for a in sys.argv[1:] if a.startswith("-")]
        if self.current_file:
            args.append(self.current_file)
        # 新的程式啟動前先把旗標與視窗設定存好
        self._save_state()
        tc = getattr(self, "tray_controller", None)
        if tc is not None:
            tc.stop_listening()   # 不然新程序會以為我們還在，把自己關掉
        if not QProcess.startDetached(sys.executable, args):
            if tc is not None:
                tc.start_listening()
            QMessageBox.information(self, tr("語言"),
                                    tr("無法自動重新啟動，請手動重新開啟 PlayCut。"))
            return
        self.quit_app()

    def _typing(self) -> bool:
        """使用者正在輸入文字時，單鍵快速鍵要讓路。"""
        from PySide6.QtWidgets import QAbstractSpinBox, QLineEdit, QTextEdit
        w = QApplication.focusWidget()
        if isinstance(w, (QLineEdit, QTextEdit, QAbstractSpinBox)):
            return True
        if self.tbl.state() == QAbstractItemView.EditingState:
            return True
        return False

    @staticmethod
    def _yields_to_typing(seq: QKeySequence) -> bool:
        """沒有 Ctrl / Alt / Win 的按鍵（M、空白、方向鍵…）在打字時要讓路。
        F1–F35 例外，打字時也照樣有效。"""
        if seq.isEmpty():
            return False
        kc = seq[0]
        if kc.keyboardModifiers() & (Qt.ControlModifier | Qt.AltModifier
                                     | Qt.MetaModifier):
            return False
        if Qt.Key_F1 <= kc.key() <= Qt.Key_F35:
            return False
        return True

    def _act(self, menu: QMenu, category: str, aid: str, text: str,
             shortcut: str, fn):
        a = QAction(text, self)
        entry = ShortcutEntry(aid, category, text, shortcut)
        self._actions[aid] = (a, entry)
        a.setShortcutContext(Qt.ApplicationShortcut)
        a.setShortcut(QKeySequence(self._shortcut_overrides.get(aid, shortcut)))

        a.triggered.connect(lambda _=False, act=a, f=fn: self._run_action(act, f))
        menu.addAction(a)
        self.addAction(a)
        return a

    def _run_action(self, act: QAction, fn):
        # 單鍵快捷鍵在打字時讓路（依「目前」的按鍵判斷，改鍵後也正確）
        # 例外：數字欄位用不到空白鍵，焦點停在那裡時空白鍵照樣播放 / 暫停
        if (self._yields_to_typing(act.shortcut()) and self._typing()
                and not self._space_in_spinbox(act.shortcut())):
            return
        fn()

    @staticmethod
    def _is_spinbox(w) -> bool:
        from PySide6.QtWidgets import QAbstractSpinBox
        return isinstance(w, QAbstractSpinBox) or (
            w is not None and isinstance(w.parent(), QAbstractSpinBox))

    def _space_in_spinbox(self, seq: QKeySequence) -> bool:
        if seq.isEmpty() or seq.count() != 1:
            return False
        kc = seq[0]
        return (kc.key() == Qt.Key_Space and not kc.keyboardModifiers()
                and self._is_spinbox(QApplication.focusWidget()))

    # ------------------------------------------------------------------
    # 全域事件：空白鍵不被數字欄位吃掉、全螢幕時滑鼠指標自動隱藏
    # ------------------------------------------------------------------
    def eventFilter(self, obj, ev):
        t = ev.type()
        if t == QEvent.ShortcutOverride:
            if (ev.key() == Qt.Key_Space and not ev.modifiers()
                    and self._is_spinbox(obj)):
                ev.ignore()      # 不讓 spinbox 搶走，交給「播放 / 暫停」快捷鍵
                return True
        elif t == QEvent.MouseMove and self._fs_extras:
            pos = QCursor.pos()
            last = self._last_cursor_pos
            # Windows 有時會送假的 MouseMove（例如換游標時），位置沒變就不理它
            if last is None or (pos - last).manhattanLength() > 2:
                self._last_cursor_pos = pos
                self._show_cursor()
                self._cursor_timer.start()
        return super().eventFilter(obj, ev)

    def _hide_cursor(self):
        if self._fs_extras and not self._cursor_hidden:
            self.video.setCursor(Qt.BlankCursor)
            self._cursor_hidden = True

    def _show_cursor(self):
        if self._cursor_hidden:
            self.video.unsetCursor()
            self._cursor_hidden = False

    def _sync_fullscreen_extras(self):
        if not hasattr(self, "_cursor_timer"):   # 建構中還沒準備好
            return
        on = self.isFullScreen() and self.isVisible()
        if on == self._fs_extras:
            return
        self._fs_extras = on
        self._update_keep_awake()
        if on:
            self._last_cursor_pos = QCursor.pos()
            self._hide_cursor()          # 一進全螢幕就先藏起來
        else:
            self._cursor_timer.stop()
            self._show_cursor()

    def changeEvent(self, ev):
        super().changeEvent(ev)
        if ev.type() == QEvent.WindowStateChange:
            self._sync_fullscreen_extras()

    def showEvent(self, ev):
        super().showEvent(ev)
        self._sync_fullscreen_extras()

    def hideEvent(self, ev):
        super().hideEvent(ev)
        self._sync_fullscreen_extras()   # 縮到系統匣時也要放掉防休眠
        self._update_keep_awake()

    def _key(self, aid: str) -> str:
        """目前指定給某功能的按鍵（給人看的文字），沒有就回傳空字串。"""
        item = self._actions.get(aid)
        if not item:
            return ""
        return item[0].shortcut().toString(QKeySequence.NativeText)

    def _hint(self, widget, tip: str, aid: str, label: str = ""):
        """登記一個會跟著快捷鍵更新的提示（label 有給的話按鈕文字也會帶按鍵）。"""
        def upd():
            k = self._key(aid)
            widget.setToolTip(f"{tip}　({k})" if k else tip)
            if label:
                widget.setText(f"{label} {k}" if k else label)
        self._hints.append(upd)

    def _refresh_shortcut_hints(self):
        for fn in self._hints:
            fn()

    def customize_shortcuts(self):
        entries = [e for _, e in self._actions.values()]
        current = {aid: a.shortcut().toString(QKeySequence.PortableText)
                   for aid, (a, _) in self._actions.items()}
        dlg = ShortcutDialog(self, entries, current)
        if not dlg.exec():
            return
        self.apply_shortcuts(dlg.values())
        self.statusBar().showMessage(tr("快捷鍵已更新"), 4000)

    def apply_shortcuts(self, values: dict):
        """套用並存檔。values = {aid: PortableText}，空字串 = 不指定。"""
        entries = []
        for aid, (a, e) in self._actions.items():
            if aid in values:
                a.setShortcut(QKeySequence(values[aid]))
            entries.append(e)
        cur = {aid: a.shortcut().toString(QKeySequence.PortableText)
               for aid, (a, _) in self._actions.items()}
        save_overrides(self.settings, entries, cur)
        self._shortcut_overrides = load_overrides(self.settings)
        self._refresh_shortcut_hints()

    def _wire(self):
        v = self.video
        v.positionChanged.connect(self._on_position)
        v.durationChanged.connect(self._on_duration)
        v.pausedChanged.connect(self._on_paused)
        v.endReached.connect(self._update_keep_awake)
        v.fileLoaded.connect(lambda _p: self._update_keep_awake())
        # 保險：關檔 / 縮到系統匣等狀況不一定有訊號，定期再檢查一次
        self._keep_awake_timer = QTimer(self)
        self._keep_awake_timer.setInterval(3000)
        self._keep_awake_timer.timeout.connect(self._update_keep_awake)
        self._keep_awake_timer.start()
        v.speedChanged.connect(self._on_speed)
        v.audioDelayChanged.connect(self._on_audio_delay)
        v.volumeChanged.connect(self._on_volume)
        v.fileLoaded.connect(self._on_file_loaded)
        v.requestFullscreenToggle.connect(self.toggle_fullscreen)
        v.mpvMessage.connect(lambda s: self.statusBar().showMessage(s, 8000))
        v.subtitleTracksChanged.connect(self._schedule_sub_ui)
        v.hdrChanged.connect(self._on_hdr_changed)
        v.subDelayChanged.connect(lambda _d: self._schedule_sub_ui())
        self._sub_ui_timer = QTimer(self)
        self._sub_ui_timer.setSingleShot(True)
        self._sub_ui_timer.setInterval(80)
        self._sub_ui_timer.timeout.connect(self._update_sub_ui)

        self.timeline.scrubbing.connect(self._on_scrub)
        self.timeline.seekRequested.connect(self._on_seek_request)
        self.timeline.markerClicked.connect(self._select_marker_row)

    # ==================================================================
    # 檔案
    # ==================================================================
    def open_file(self):
        last = self.settings.value("lastDir", "", str)
        path, _ = QFileDialog.getOpenFileName(self, tr("開啟影片"), last, tr(VIDEO_FILTER))
        if path:
            if SUB.is_subtitle(path):
                self.add_subtitle_file(path)
            else:
                self.load(path)

    def load(self, path: str):
        if getattr(self, "_unloading", False):
            # 正在關閉 / 放掉影片檔的途中（等待時會處理事件），這時不要再開新檔，
            # 不然剛放掉的檔案會被重新打開、視窗藏起來後檔案就一直被鎖著。
            return
        path = str(Path(path))
        if not os.path.exists(path):
            QMessageBox.warning(self, tr("找不到檔案"), path)
            return
        if SUB.is_subtitle(path):
            self.add_subtitle_file(path)
            return
        if self.current_file and self.chk_autosave.isChecked() and len(self.markers):
            self._autosave()

        self.current_file = path
        self.settings.setValue("lastDir", str(Path(path).parent))
        self.markers.clear()
        self._placed_markers.clear()
        data = self.markers.load(path)
        self.video.open(path)
        self.setWindowTitle(f"PlayCut — {os.path.basename(path)}")
        try:
            self._media_info = probe(path)
        except Exception:
            self._media_info = None

        if data:
            if "audio_delay" in data:
                self.spn_delay.setValue(round(float(data["audio_delay"]) * 1000))
            self.statusBar().showMessage(
                tr("已載入 {n} 個先前存下的旗標", n=len(self.markers)), 5000)
        self._refresh_markers()

    def dragEnterEvent(self, ev):
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    def dropEvent(self, ev):
        paths = [u.toLocalFile() for u in ev.mimeData().urls() if u.toLocalFile()]
        if not paths:
            return
        subs = [p for p in paths if SUB.is_subtitle(p)]
        jsons = [p for p in paths if p.lower().endswith(".json")]
        videos = [p for p in paths if p not in subs and p not in jsons]
        if videos:
            # 影片跟字幕一起拖進來：先開影片，字幕等影片載入後再掛
            self._pending_subs = list(subs)
            self.load(videos[0])
        else:
            for p in subs:
                self.add_subtitle_file(p)
        if jsons and not videos:
            self._load_marker_json(jsons[0])

    # ==================================================================
    # 字幕
    # ==================================================================
    def open_subtitle_file(self):
        if not self.current_file:
            QMessageBox.information(self, tr("還沒開啟影片"), tr("請先開啟影片，再載入字幕檔。"))
            return
        last = str(Path(self.current_file).parent)
        paths, _ = QFileDialog.getOpenFileNames(self, tr("載入字幕檔"), last, tr(SUB.SUB_FILTER))
        for p in paths:
            self.add_subtitle_file(p)

    def add_subtitle_file(self, path: str):
        path = str(Path(path))
        if not os.path.exists(path):
            QMessageBox.warning(self, tr("找不到檔案"), path)
            return
        if not self.current_file:
            QMessageBox.information(self, tr("還沒開啟影片"),
                                    tr("請先開啟影片，再把字幕檔拖進來。"))
            return
        # 已經載入過（例如同名字幕被自動載入）就直接切過去，不重複加
        norm = os.path.normcase(os.path.abspath(path))
        for t in self.video.subtitle_tracks():
            ef = t["external_filename"]
            if t["external"] and ef and os.path.normcase(os.path.abspath(ef)) == norm:
                self.video.set_subtitle_track(t["id"])
                self.video.set_subtitle_visible(True)
                self.video.flash(tr("字幕"), os.path.basename(path), msec=1500)
                return
        if self.video.add_subtitle(path):
            self.video.set_subtitle_visible(True)
            self.video.flash(tr("字幕"), os.path.basename(path), msec=1500)
            self.statusBar().showMessage(tr("已載入字幕：{name}", name=os.path.basename(path)), 5000)

    def cycle_subtitle(self):
        if not self.video.subtitle_tracks():
            self.video.flash(tr("沒有字幕"), tr("字幕 → 載入字幕檔…"), msec=1200)
            return
        t = self.video.cycle_subtitle()
        self.video.flash(tr("字幕：") + (self.video.track_label(t) if t else tr("關閉")),
                         msec=1200)

    def toggle_subtitle(self):
        vis = not self.video.is_subtitle_visible()
        self.video.set_subtitle_visible(vis)
        self.video.flash(tr("字幕：顯示") if vis else tr("字幕：隱藏"), msec=900)

    def _set_sub_delay(self, sec: float):
        self.video.set_sub_delay(sec)
        self.video.flash(tr("字幕延遲 {ms:+.0f} ms", ms=sec*1000), tr("正值 = 字幕晚出現"), msec=1000)

    def _nudge_sub_delay(self, step: float):
        self._set_sub_delay(round(self.video.get_sub_delay() + step, 3))

    def _nudge_sub_scale(self, step: float):
        sc = round(max(0.3, min(4.0, self.video.get_sub_scale() + step)), 2)
        self.video.set_sub_scale(sc)
        self.settings.setValue("subScale", sc)
        self.video.flash(tr("字幕大小 {pct:.0f}%", pct=sc*100), msec=800)

    def _nudge_sub_pos(self, step: int):
        pos = max(0, min(150, self.video.get_sub_pos() + step))
        self.video.set_sub_pos(pos)
        self.settings.setValue("subPos", pos)
        self.video.flash(tr("字幕位置 {pos}", pos=pos), tr("100 = 畫面最下方"), msec=800)

    def _reset_sub_style(self):
        self.video.set_sub_scale(1.0)
        self.video.set_sub_pos(100)
        self.settings.setValue("subScale", 1.0)
        self.settings.setValue("subPos", 100)
        self.video.flash(tr("字幕大小 / 位置已恢復預設"), msec=900)

    def _populate_sub_menu(self):
        m = self.menu_sub_tracks
        m.clear()
        tracks = self.video.subtitle_tracks() if self.current_file else []
        a = m.addAction(tr("關閉字幕"))
        a.setCheckable(True)
        a.setChecked(not any(t["selected"] for t in tracks))
        a.triggered.connect(lambda: self.video.set_subtitle_track(None))
        for t in tracks:
            a = m.addAction(self.video.track_label(t))
            a.setCheckable(True)
            a.setChecked(t["selected"])
            a.triggered.connect(lambda _=False, i=t["id"]: (
                self.video.set_subtitle_track(i),
                self.video.set_subtitle_visible(True)))
        m.addSeparator()
        a = m.addAction(tr("載入字幕檔…"))
        a.triggered.connect(self.open_subtitle_file)
        a = m.addAction(tr("顯示字幕"))
        a.setCheckable(True)
        a.setChecked(self.video.is_subtitle_visible())
        a.triggered.connect(lambda on: self.video.set_subtitle_visible(on))

    def _schedule_sub_ui(self):
        self._sub_ui_timer.start()

    def _update_sub_ui(self):
        cur = self.video.current_subtitle()
        delay = self.video.get_sub_delay()
        if cur and self.video.is_subtitle_visible():
            self.btn_sub.setText(tr("字幕 ✓"))
            tip = tr("目前字幕：{name}", name=self.video.track_label(cur))
            if abs(delay) > 1e-6:
                tip += "\n" + tr("字幕延遲 {ms:+.0f} ms", ms=delay*1000)
        else:
            self.btn_sub.setText(tr("字幕"))
            tip = tr("選擇字幕軌 / 載入字幕檔")
        self.btn_sub.setToolTip(tip)

    def _current_sub_source(self) -> Optional[SUB.SubSource]:
        """匯出用：播放器目前「有顯示」的字幕。"""
        if not self.video.is_subtitle_visible():
            return None
        t = self.video.current_subtitle()
        if not t:
            return None
        return SUB.SubSource(
            title=self.video.track_label(t),
            codec=t["codec"],
            external_path=t["external_filename"] if t["external"] else "",
            ff_index=-1 if t["external"] else t["ff_index"],
            delay=self.video.get_sub_delay(),
        )

    # ==================================================================
    # 播放狀態
    # ==================================================================
    def _on_position(self, t: float):
        self.timeline.set_position(t)
        self._update_time_label(t)

    def _on_duration(self, d: float):
        self.timeline.set_duration(d)
        self._update_time_label(self.video.position)
        self._refresh_markers()

    def _update_time_label(self, t: float):
        d = self.video.duration
        short = d < 3600  # 一小時以內就不顯示小時，省空間
        def f(x):
            txt = fmt_time(x)
            return txt[3:] if short else txt
        fps = self.video.fps
        extra = f"  #{int(round(t * fps))}" if fps else ""
        self.lbl_time.setText(f"{f(t)} / {f(d)}{extra}")
        self.lbl_time.setToolTip(f"{fmt_time(t)} / {fmt_time(d)}")

    def _on_paused(self, paused: bool):
        self._set_play_button(paused)
        self._update_keep_awake()

    def _update_keep_awake(self):
        """播放中（或全螢幕）時不讓螢幕關閉 / 電腦睡眠；暫停、播完、縮到系統匣就恢復。"""
        if not hasattr(self, "video"):   # 建構中還沒準備好
            return
        on = bool(getattr(self, "_fs_extras", False))
        if not on and self.isVisible():
            on = self.video.is_playing()
        keepawake.set_active(on)

    def _set_play_button(self, paused: bool):
        """暫停中 = 藍底白色 ▶（提醒按下去會播放）；播放中 = 灰底 ❚❚。"""
        size = 44
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#ffffff"))
        if paused:
            path = QPainterPath()
            path.moveTo(size * 0.26, size * 0.16)
            path.lineTo(size * 0.26, size * 0.84)
            path.lineTo(size * 0.86, size * 0.5)
            path.closeSubpath()
            p.drawPath(path)
        else:
            p.drawRoundedRect(QRectF(size * 0.2, size * 0.16, size * 0.2, size * 0.68), 3, 3)
            p.drawRoundedRect(QRectF(size * 0.6, size * 0.16, size * 0.2, size * 0.68), 3, 3)
        p.end()
        self.btn_play.setIcon(QIcon(pm))
        self.btn_play.setStyleSheet(
            "QToolButton#btnPlay{background:#2d7ff9;border:1px solid #5b9bff;"
            "border-radius:8px;padding:0}"
            "QToolButton#btnPlay:hover{background:#4a91ff}"
            if paused else
            "QToolButton#btnPlay{background:#3a424f;border:1px solid #4a5364;"
            "border-radius:8px;padding:0}"
            "QToolButton#btnPlay:hover{background:#4a5364}")

    def _on_speed(self, s: float):
        self._updating_ui = True
        self.cmb_speed.setEditText(f"{s:g}×")
        self._updating_ui = False

    def _on_audio_delay(self, d: float):
        self._updating_ui = True
        self.spn_delay.setValue(round(d * 1000))
        self._updating_ui = False

    def _on_volume(self, v: float):
        self._updating_ui = True
        self.sld_vol.setValue(int(round(v)))
        self._updating_ui = False

    def _on_file_loaded(self, path: str):
        self.statusBar().showMessage(os.path.basename(path), 4000)
        subs, self._pending_subs = self._pending_subs, []
        for p in subs:
            self.add_subtitle_file(p)
        self._schedule_sub_ui()
        QTimer.singleShot(200, lambda: self._update_time_label(self.video.position))

    def _on_scrub(self, t: float):
        self._update_time_label(t)
        self.video.seek_absolute(t, exact=False)

    def _on_seek_request(self, t: float):
        self.video.seek_absolute(t, exact=True)

    # 速度 -------------------------------------------------------------
    def _speed_from_combo(self, idx: int):
        data = self.cmb_speed.itemData(idx)
        if data:
            self.video.set_speed(float(data))

    def _speed_from_text(self):
        if self._updating_ui:
            return
        txt = self.cmb_speed.currentText().strip().rstrip("×xX ").strip()
        try:
            self.video.set_speed(float(txt))
        except ValueError:
            self._on_speed(self.video.get_speed())

    def _nudge_speed(self, direction: int):
        cur = self.video.get_speed()
        step = self._speed_step
        k = cur / step
        # 對齊到間隔的格子上（例如 1.25 用 0.1 加速 → 1.3）
        if direction > 0:
            n = math.floor(k + 1e-6) + 1
        else:
            n = math.ceil(k - 1e-6) - 1
        nxt = round(min(MAX_SPEED, max(MIN_SPEED, n * step)), 2)
        self.video.set_speed(nxt)
        self.video.flash(tr("{s:g}× 速度", s=nxt), msec=800)

    # 聲音 -------------------------------------------------------------
    def _delay_changed(self, ms: float):
        if self._updating_ui:
            return
        self.video.set_audio_delay(ms / 1000.0)
        self.video.flash(tr("聲音延遲 {ms:+.0f} ms", ms=ms),
                         tr("正值 = 聲音延後") if ms else "", msec=900)

    def _nudge_volume(self, delta: int):
        vol = max(0, min(150, self.sld_vol.value() + delta))
        self.sld_vol.setValue(vol)
        self.video.flash(f"🔊 {vol}%", bar=vol / 150.0, msec=700)

    def _toggle_mute(self, on: bool):
        self.video.set_mute(on)
        self.btn_mute.setIcon(self._icon(
            QStyle.SP_MediaVolumeMuted if on else QStyle.SP_MediaVolume))

    # ==================================================================
    # 旗標
    # ==================================================================
    def add_marker(self, role: str = ROLE_AUTO):
        if not self.current_file:
            self.statusBar().showMessage(tr("請先開啟影片"), 3000)
            return
        t = self.video.position
        if self.markers.nearest(t, 0.02) is not None:
            self.video.flash(tr("這裡已經有旗標了"), msec=900)
            return
        mk = self.markers.add(t, "", role if isinstance(role, str) else ROLE_AUTO)
        self._placed_markers.append(mk)
        self._refresh_markers()
        label = {"in": tr("起點"), "out": tr("終點")}.get(role, tr("旗標"))
        self.video.flash(f"🚩 {label} {fmt_time(t)}", msec=1000)
        self._autosave()

    def undo_last_marker(self):
        """Ctrl+Z：移除最後放置的旗標（已經被刪掉的會跳過，可以連按）。"""
        while self._placed_markers:
            mk = self._placed_markers.pop()
            idx = next((i for i, m in enumerate(self.markers) if m is mk), None)
            if idx is None:
                continue
            self.markers.remove(idx)
            self._refresh_markers()
            self.video.flash(tr("↶ 已移除旗標 {t}", t=fmt_time(mk.t)), msec=1000)
            self._autosave()
            return
        self.video.flash(tr("沒有可以復原的旗標"), msec=900)

    def delete_selected_markers(self):
        rows = sorted({i.row() for i in self.tbl.selectedIndexes()}, reverse=True)
        if not rows:
            return
        for r in rows:
            self.markers.remove(r)
        self._refresh_markers()
        self._autosave()

    def clear_markers(self):
        if not len(self.markers):
            return
        if QMessageBox.question(self, tr("清空旗標"),
                                tr("確定要刪除全部 {n} 個旗標嗎？", n=len(self.markers))) \
                != QMessageBox.Yes:
            return
        self.markers.clear()
        self._refresh_markers()
        self._autosave()

    def toggle_selected_role(self):
        rows = sorted({i.row() for i in self.tbl.selectedIndexes()})
        order = [ROLE_AUTO, ROLE_IN, ROLE_OUT]
        for r in rows:
            m = self.markers[r]
            m.role = order[(order.index(m.role) + 1) % 3]
        self._refresh_markers()
        self._autosave()

    def goto_selected_marker(self):
        rows = sorted({i.row() for i in self.tbl.selectedIndexes()})
        if rows:
            self.video.seek_absolute(self.markers[rows[0]].t, exact=True)

    def goto_next_marker(self):
        t = self.markers.next_after(self.video.position)
        if t is not None:
            self.video.seek_absolute(t, exact=True)
            self.video.flash(f"🚩 {fmt_time(t)}", msec=800)

    def goto_prev_marker(self):
        t = self.markers.prev_before(self.video.position)
        if t is not None:
            self.video.seek_absolute(t, exact=True)
            self.video.flash(f"🚩 {fmt_time(t)}", msec=800)

    def _marker_double_clicked(self, item: QTableWidgetItem):
        if item.column() in (0, 1):
            self.video.seek_absolute(self.markers[item.row()].t, exact=True)

    def _marker_edited(self, item: QTableWidgetItem):
        if self._updating_ui:
            return
        r = item.row()
        if r >= len(self.markers):
            return
        if item.column() == 2:
            t = parse_time(item.text())
            if t is None:
                self._refresh_markers()
                return
            self.markers[r].t = max(0.0, t)
            self.markers.sort()
            self._refresh_markers()
        elif item.column() == 3:
            self.markers[r].label = item.text()
        self._autosave()

    def _select_marker_row(self, idx: int):
        if 0 <= idx < self.tbl.rowCount():
            self.tbl.selectRow(idx)

    def _refresh_markers(self):
        self._updating_ui = True
        roles = self.markers.roles()
        self.tbl.setRowCount(len(self.markers))
        for i, (m, role) in enumerate(zip(self.markers, roles)):
            forced = m.role in (ROLE_IN, ROLE_OUT)
            name = (tr("起點") if role == ROLE_IN else tr("終點")) + (tr("（固定）") if forced else "")
            cells = [str(i + 1), name, fmt_time(m.t), m.label]
            for c, text in enumerate(cells):
                it = QTableWidgetItem(text)
                if c in (0, 1):
                    it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                if c == 1:
                    it.setForeground(QColor("#5ad28c") if role == ROLE_IN
                                     else QColor("#f06e6e"))
                self.tbl.setItem(i, c, it)
        self._updating_ui = False
        self.timeline.update()

        segs = self.markers.segments(self.video.duration)
        if not segs:
            self.lbl_segments.setText(
                tr("尚無片段。\n插入第 1 個旗標 = 起點，第 2 個 = 終點，"
                "第 3 個又是起點…依此類推。"))
        else:
            total = sum(s.duration for s in segs)
            lines = ["<b>" + tr("將匯出 {n} 段，共 {sec:.3f} 秒", n=len(segs), sec=total) + "</b>"]
            for i, s in enumerate(segs[:12], 1):
                lines.append(f"{i}. {fmt_time(s.start)} → {fmt_time(s.end)}"
                             f"　({s.duration:.3f}s)")
            if len(segs) > 12:
                lines.append(tr("… 還有 {n} 段", n=len(segs) - 12))
            self.lbl_segments.setText("<br>".join(lines))

    # 旗標檔 -----------------------------------------------------------
    def _autosave(self):
        if not (self.current_file and self.chk_autosave.isChecked()):
            return
        try:
            self.markers.save(self.current_file, {
                "audio_delay": self.spn_delay.value() / 1000.0,
                "speed": self.video.get_speed(),
            })
        except Exception as exc:
            self.statusBar().showMessage(tr("旗標自動存檔失敗：{err}", err=exc), 5000)

    def save_markers_file(self):
        if not self.current_file:
            return
        default = str(MarkerList.project_path(self.current_file))
        path, _ = QFileDialog.getSaveFileName(self, tr("另存旗標檔"), default,
                                              "JSON (*.json)")
        if not path:
            return
        import json
        Path(path).write_text(json.dumps({
            "version": 1, "app": "PlayCut",
            "video": os.path.basename(self.current_file),
            "audio_delay": self.spn_delay.value() / 1000.0,
            "markers": [m.to_dict() for m in self.markers],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        self.statusBar().showMessage(tr("已儲存 {path}", path=path), 5000)

    def load_markers_file(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("載入旗標檔"), "",
                                              "JSON (*.json)")
        if path:
            self._load_marker_json(path)

    def _load_marker_json(self, path: str):
        try:
            data = self.markers.load_from(path)
        except Exception as exc:
            QMessageBox.warning(self, tr("載入失敗"), str(exc))
            return
        if "audio_delay" in data:
            self.spn_delay.setValue(round(float(data["audio_delay"]) * 1000))
        self._refresh_markers()
        self.statusBar().showMessage(tr("已載入 {n} 個旗標", n=len(self.markers)), 5000)

    def export_markers_csv(self):
        if not len(self.markers):
            return
        default = str(Path(self.current_file or "markers").with_suffix(".csv"))
        path, _ = QFileDialog.getSaveFileName(self, tr("匯出 CSV"), default,
                                              "CSV (*.csv)")
        if path:
            Path(path).write_text(self.markers.to_csv(), encoding="utf-8-sig")
            self.statusBar().showMessage(tr("已匯出 {path}", path=path), 5000)

    # ==================================================================
    # 匯出
    # ==================================================================
    def export_segments(self):
        if not self.current_file:
            QMessageBox.information(self, tr("尚未開啟影片"), tr("請先開啟一個影片檔。"))
            return
        if not Tools.available():
            self._warn_no_ffmpeg()
            return
        segs = self.markers.segments(self.video.duration)
        if not segs:
            QMessageBox.information(
                self, tr("沒有可匯出的片段"),
                tr("請至少插入兩個旗標：第 1 個是起點、第 2 個是終點。\n"
                "（在想要的位置按 M 就可以插旗標）"))
            return
        self.video.set_paused(True)
        dlg = ExportDialog(
            self, self.current_file, segs,
            audio_delay=self.spn_delay.value() / 1000.0,
            default_mode=self.settings.value("exportMode", EX.MODE_SMART, str),
            default_dir=self.settings.value("exportDir", "", str),
            subtitle=self._current_sub_source(),
            default_export_srt=self.settings.value("exportSrt", False, bool),
            default_burn=self.settings.value("exportBurnSub", False, bool),
            default_hw=self.settings.value("exportHwAccel", True, bool),
            player_speed=self.video.get_speed(),
            default_crop=self.settings.value("exportCrop", "", str),
            default_crop_pos=self.settings.value("exportCropPos", "center", str),
            default_crop_scale=self.settings.value("exportCropScale", True, bool),
            default_crf=self.settings.value("exportCrf", 22, int),
            default_preset=self.settings.value("exportPreset", "medium", str),
            default_vcodec=self.settings.value("exportVCodec", "", str),
            default_max_res=self.settings.value("exportMaxRes", 0, int),
            default_target_on=self.settings.value("exportTargetOn", False, bool),
            default_target_mb=self.settings.value("exportTargetMb", 25.0, float),
            default_audio_kbps=self.settings.value("exportAudioKbps", 0, int),
        )
        dlg.exec()
        self.settings.setValue("exportMode", dlg.mode.currentData())
        self.settings.setValue("exportDir", dlg.out_dir.text())
        self.settings.setValue("exportHwAccel", dlg.hw_accel.isChecked())
        self.settings.setValue("exportCrop", dlg.crop.currentData() or "")
        self.settings.setValue("exportCropPos", dlg.crop_pos.currentData() or "center")
        self.settings.setValue("exportCropScale", dlg.crop_scale.isChecked())
        self.settings.setValue("exportCrf", dlg.crf.value())
        self.settings.setValue("exportPreset", dlg.preset.currentText())
        self.settings.setValue("exportVCodec", dlg.vcodec.currentData() or "")
        self.settings.setValue("exportMaxRes", int(dlg.max_res.currentData() or 0))
        self.settings.setValue("exportTargetOn", dlg.target_on.isChecked())
        self.settings.setValue("exportTargetMb", dlg.target_mb.value())
        self.settings.setValue("exportAudioKbps", int(dlg.audio_kbps.currentData() or 0))
        if dlg.export_srt.isEnabled():
            self.settings.setValue("exportSrt", dlg.export_srt.isChecked())
            self.settings.setValue("exportBurnSub", dlg.burn_sub.isChecked())

    def _warn_no_ffmpeg(self):
        QMessageBox.warning(
            self, tr("找不到 ffmpeg"),
            tr("匯出功能需要 ffmpeg。\n\n")
            + (tr("請在終端機執行：brew install ffmpeg\n（或執行專案資料夾裡的 setup_mac.command）\n")
               if sys.platform == "darwin" else
               tr("請執行專案資料夾裡的 setup.bat，它會自動把 ffmpeg.exe 下載到 bin\\。\n")) +
            tr("（播放功能不受影響，仍可正常使用。）"))

    # ==================================================================
    # 截圖
    # ==================================================================
    def _shot_format(self) -> str:
        ext = self.settings.value("screenshotFormat", "png", str)
        return ext if ext in dict(SHOT_FORMATS) else "png"

    @staticmethod
    def _fallback_screenshot_dir() -> Path:
        """影片旁邊寫不進去（唯讀光碟、網路磁碟…）時改存到「圖片/PlayCut」。"""
        pics = QStandardPaths.writableLocation(QStandardPaths.PicturesLocation)
        return Path(pics or Path.home()) / "PlayCut"

    def _screenshot_dir(self) -> Path:
        """截圖存放位置：自訂資料夾 → 影片所在的資料夾 → 圖片/PlayCut。"""
        custom = self.settings.value("screenshotDir", "", str)
        if custom:
            return Path(custom)
        if self.current_file:
            return Path(self.current_file).parent
        return self._fallback_screenshot_dir()

    def _screenshot_path(self, folder: Path, with_subs: bool) -> Path:
        """檔名 = 影片名_時:分:秒.毫秒[_sub].png，同名時自動加 (2)、(3)…"""
        stem = Path(self.current_file).stem or "PlayCut"
        ms = int(round(max(0.0, self.video.position) * 1000))
        h, ms = divmod(ms, 3600_000)
        m, ms = divmod(ms, 60_000)
        s, ms = divmod(ms, 1000)
        base = f"{stem}_{h:02d}-{m:02d}-{s:02d}.{ms:03d}" + ("_sub" if with_subs else "")
        ext = self._shot_format()
        path = folder / f"{base}.{ext}"
        n = 2
        while path.exists():
            path = folder / f"{base} ({n}).{ext}"
            n += 1
        return path

    def _save_screenshot(self, folder: Path, with_subs: bool):
        """回傳 (路徑, 錯誤訊息)；成功時錯誤訊息是 None。"""
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return None, str(exc)
        path = self._screenshot_path(folder, with_subs)
        err = self.video.screenshot_to_file(str(path), with_subs)
        if err is None and not path.exists():
            err = tr("無法寫入檔案")
        return path, err

    def take_screenshot(self, with_subs: bool = True):
        """擷取目前畫面。with_subs=True 含字幕，False 只有影片本身。"""
        if not self.current_file:
            self.statusBar().showMessage(tr("請先開啟影片"), 3000)
            return
        folder = self._screenshot_dir()
        path, err = self._save_screenshot(folder, with_subs)
        if err is not None:
            fallback = self._fallback_screenshot_dir()
            if fallback != folder:
                path, err = self._save_screenshot(fallback, with_subs)
        if err is not None:
            self.video.flash(tr("截圖失敗"), msec=1500)
            self.statusBar().showMessage(tr("截圖失敗：{err}", err=err), 8000)
            return
        self._last_screenshot = path

        if self.act_shot_clip.isChecked():
            img = QImage(str(path))
            if not img.isNull():
                QApplication.clipboard().setImage(img)

        kind = tr("含字幕") if with_subs else tr("影片畫面")
        note = path.name
        if with_subs and not (self.video.is_subtitle_visible()
                              and self.video.current_subtitle()):
            note = tr("目前沒有顯示字幕，所以跟影片畫面一樣")
        self.video.flash(tr("📷 已截圖（{kind}）", kind=kind), note, msec=1400)
        self.statusBar().showMessage(tr("截圖已存到 {path}", path=str(path)), 8000)

    def choose_screenshot_dir(self):
        start = self.settings.value("screenshotDir", "", str) or str(self._screenshot_dir())
        d = QFileDialog.getExistingDirectory(self, tr("選擇截圖資料夾"), start)
        if d:
            self.settings.setValue("screenshotDir", str(Path(d)))
            self.statusBar().showMessage(tr("截圖會存到 {path}", path=str(Path(d))), 5000)
        self._sync_screenshot_ui()

    def _shot_use_video_dir(self, on: bool):
        if on:
            self.settings.setValue("screenshotDir", "")
            self.statusBar().showMessage(tr("截圖會存到影片所在的資料夾"), 4000)
            self._sync_screenshot_ui()
        else:
            self.choose_screenshot_dir()      # 取消勾選 = 改用自訂資料夾

    def open_screenshot_dir(self):
        d = self._screenshot_dir()
        if not d.is_dir():
            d = self._fallback_screenshot_dir()
            d.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(d)))

    def _sync_screenshot_ui(self):
        custom = self.settings.value("screenshotDir", "", str)
        self.act_shot_beside.setChecked(not custom)
        self.act_shot_choose.setText(
            tr("截圖資料夾：{name}…", name=Path(custom).name or custom) if custom
            else tr("選擇截圖資料夾…"))
        fmt = self._shot_format()
        for a in self._shot_fmt_menu.actions():
            a.setChecked(a.data() == fmt)

    # ==================================================================
    # 其他
    # ==================================================================
    def _set_paused_badge(self, on: bool):
        self.video.osd.badge_enabled = bool(on)
        self.settings.setValue("pausedBadge", bool(on))
        self.video.update()

    def _set_hdr_mode(self, mode: str):
        from .mpvwidget import HDR_DEFAULT, HDR_MODES
        if mode not in HDR_MODES:
            mode = HDR_DEFAULT
        self.settings.setValue("hdrToneMapping", mode)
        for a in self._hdr_menu.actions():
            if a.data() in HDR_MODES:
                a.setChecked(a.data() == mode)
        self.video.set_hdr_tonemap(mode, self.act_hdr_peak.isChecked(),
                                   self.act_hdr_boost.isChecked())

    def _set_hdr_peak(self, on: bool):
        self.settings.setValue("hdrPeakDetect", bool(on))
        self._set_hdr_mode(self.settings.value("hdrToneMapping", "hable", str))

    def _set_hdr_boost(self, on: bool):
        self.settings.setValue("hdrBoost", bool(on))
        self._set_hdr_mode(self.settings.value("hdrToneMapping", "hable", str))

    def _on_hdr_changed(self, kind: str):
        self.video.apply_hdr_boost()
        if kind:
            mode = self.settings.value("hdrToneMapping", "hable", str)
            self.statusBar().showMessage(
                tr("HDR 影片（{kind}）→ 已轉換為 SDR 顯示（{mode}）", kind=kind, mode=mode),
                6000)

    def _set_speed_step(self, step: float):
        self._speed_step = float(step)
        self.settings.setValue("speedStep", float(step))
        for a in self._speed_step_menu.actions():
            a.setChecked(abs(float(a.data()) - step) < 1e-6)
        self.statusBar().showMessage(tr("加速 / 降速每次 ± {s:g}×", s=step), 3000)

    def _set_swipe_span(self, sec: int, menu: QMenu):
        self.video.swipe_span = float(sec)
        self.settings.setValue("swipeSpan", sec)
        for a in menu.actions():
            a.setChecked(a.data() == sec)
        self.statusBar().showMessage(tr("整個螢幕寬的滑動 = {n} 秒", n=sec), 3000)

    def isFullScreen(self) -> bool:
        # Windows 上的全螢幕是自己做的（見 winmax），Qt 本身不知道
        if winmax.CUSTOM_FULLSCREEN:
            return getattr(self, "_borderless_state", None) is not None
        return super().isFullScreen()

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.exit_fullscreen()
        else:
            self._pre_fs_dock = self.marker_dock.isVisible()
            self.marker_dock.hide()
            self.bottom_bar.hide()        # 全螢幕時隱藏底下的進度條與控制列
            self.menuBar().hide()
            self.statusBar().hide()
            state = winmax.enter_borderless(self) if winmax.CUSTOM_FULLSCREEN else None
            if state is not None:
                self._borderless_state = state
            else:
                self._pre_fs_placement = winmax.prepare_fullscreen(self)
                if winmax.CUSTOM_FULLSCREEN:
                    # 自製全螢幕失敗：退回 Qt 的全螢幕，isFullScreen 也要跟著走 Qt 的
                    winmax.CUSTOM_FULLSCREEN = False
                self.showFullScreen()
        self._sync_fullscreen_extras()

    def exit_fullscreen(self):
        if not self.isFullScreen():
            return
        state = getattr(self, "_borderless_state", None)
        if state is not None:
            self._borderless_state = None
            winmax.exit_borderless(self, state)
        else:
            self.showMaximized()   # 離開全螢幕後回到「最大化」，而不是原本的視窗大小
        self.menuBar().show()
        self.statusBar().show()
        self.bottom_bar.show()
        if getattr(self, "_pre_fs_dock", True):
            self.marker_dock.show()
        placement, self._pre_fs_placement = getattr(self, "_pre_fs_placement", None), None
        if placement is not None:
            QTimer.singleShot(0, lambda: winmax.restore_after_fullscreen(self, placement))
        self._sync_fullscreen_extras()

    def show_help(self):
        # 鍵盤部分依「目前」的快捷鍵產生，自訂過也會正確
        rows, last_cat = [], None
        for a, e in self._actions.values():
            k = a.shortcut().toString(QKeySequence.NativeText)
            if not k:
                continue
            if e.category != last_cat:
                rows.append(f"<tr><td colspan=2><i>{e.category}</i></td></tr>")
                last_cat = e.category
            rows.append(f"<tr><td style='padding-right:18px'><b>{k}</b></td>"
                        f"<td>{e.text}</td></tr>")
        keys = ("<table cellspacing=0 cellpadding=1>" + "".join(rows) + "</table><br>"
                + tr("要改按鍵：檢視 → 自訂快捷鍵…") + "<br>")
        QMessageBox.information(self, tr("快速鍵與手勢"),
                                tr(HELP_GESTURES) + "<br><b>" + tr("鍵盤") + "</b><br>" + keys
                                + tr(HELP_MARKERS) + tr(HELP_SUBS))

    def show_about(self):
        QMessageBox.about(self, tr("關於 PlayCut"), tr(ABOUT_TEXT))

    def _restore_settings(self):
        geo = self.settings.value("geometry")
        if geo:
            self.restoreGeometry(geo)
        state = self.settings.value("windowState")
        if state:
            self.restoreState(state)
        span = self.settings.value("swipeSpan", 120, int)
        self.video.swipe_span = float(span)
        for a in self._swipe_menu.actions():
            a.setChecked(a.data() == span)
        self.act_paused_badge.setChecked(
            self.settings.value("pausedBadge", False, bool))
        self._set_paused_badge(self.act_paused_badge.isChecked())
        step = self.settings.value("speedStep", 0.1, float)
        if not any(abs(step - s) < 1e-6 for s in SPEED_STEPS):
            step = 0.1
        self._set_speed_step(step)
        self.act_hdr_peak.blockSignals(True)
        self.act_hdr_peak.setChecked(self.settings.value("hdrPeakDetect", True, bool))
        self.act_hdr_peak.blockSignals(False)
        self.act_hdr_boost.blockSignals(True)
        self.act_hdr_boost.setChecked(self.settings.value("hdrBoost", True, bool))
        self.act_hdr_boost.blockSignals(False)
        self._set_hdr_mode(self.settings.value("hdrToneMapping", "hable", str))
        vol = self.settings.value("volume", 100, int)
        self.sld_vol.setValue(vol)
        self.video.set_volume(vol)
        self.video.set_sub_scale(self.settings.value("subScale", 1.0, float))
        self.video.set_sub_pos(self.settings.value("subPos", 100, int))
        self.act_shot_clip.setChecked(self.settings.value("screenshotClipboard", False, bool))
        self._sync_screenshot_ui()

    def _save_state(self):
        # 先離開全螢幕，不然存下來的版面會是「控制列 / 旗標面板都隱藏」的狀態
        self.exit_fullscreen()
        self._autosave()
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("windowState", self.saveState())
        self.settings.setValue("volume", self.sld_vol.value())
        self.settings.sync()

    def quit_app(self):
        """真的結束程式（不縮到系統匣）。"""
        tc = getattr(self, "tray_controller", None)
        if tc is not None:
            tc.quit()
        else:
            self.close()
            QApplication.quit()

    def _unload_video(self) -> bool:
        """縮到系統匣時：停止播放、清掉目前的影片，下次叫出來是乾淨的新視窗。

        回傳 True 代表影片檔已經確定被放掉（可以在檔案總管刪除）。
        """
        path = self.current_file
        self._unloading = True
        try:
            released = self.video.release_file()
            if released and path:
                released = _wait_file_unlocked(path)
            if released and self.video.filename:
                # 等待期間 mpv 又被叫去開了別的檔 → 視為沒放乾淨
                released = False
        finally:
            self._unloading = False
        if not released:
            _debug_log(f"release failed: {path!r} mpv_path={self.video.filename!r}")
        self.current_file = ""
        self._media_info = None
        self._pending_subs = []
        self.markers.clear()
        self._refresh_markers()
        self.timeline.set_duration(0)
        self.timeline.set_position(0)
        try:
            self.video.set_speed(1.0)
            self.spn_delay.blockSignals(True)
            self.spn_delay.setValue(0)
            self.spn_delay.blockSignals(False)
            self.video.set_audio_delay(0.0)
            self.video.set_sub_delay(0.0)  # 靜默歸零，不顯示提示
        except Exception:
            pass
        self.setWindowTitle("PlayCut")
        self.statusBar().showMessage(tr("拖一個影片檔進來，或按 Ctrl+O 開啟"))
        return released

    def closeEvent(self, ev):
        if getattr(self, "_unloading", False):
            ev.ignore()          # 上一次關閉還在處理中，重複按 X 不要再進來
            return
        tc = getattr(self, "tray_controller", None)
        if tc is not None and not tc.quitting:
            if self.settings.value("closeToTray", True, bool):
                self._save_state()
                if self._unload_video():
                    ev.ignore()
                    self.hide()
                    tc.window_hidden()
                else:
                    # 影片檔沒能順利放掉 → 這次直接完全結束，確保檔案可以刪除
                    ev.ignore()
                    tc.quit()
            else:
                ev.ignore()
                tc.quit()
            return
        self._save_state()
        _arm_exit_watchdog()
        try:
            self.video.shutdown()
        except Exception:
            pass
        super().closeEvent(ev)


def _wait_file_unlocked(path: str, timeout: float = 2.0) -> bool:
    """Windows：確認檔案現在「可以被刪除」。

    用 DELETE 權限 + 完全共用（讀 / 寫 / 刪除）試開一次：只有當某個程式開著這個檔
    而且「不允許別人刪除」時才會失敗（ERROR_SHARING_VIOLATION），這正好就是檔案總管
    刪不掉的條件。不讀取檔案內容，所以也不會觸發防毒軟體掃描、反過來把檔案鎖住。

    其他平台刪除開著的檔案不會失敗，直接回傳 True。
    """
    if sys.platform != "win32" or not os.path.exists(path):
        return True
    import ctypes
    import time
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD,
                                wintypes.HANDLE]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    DELETE = 0x00010000
    SHARE_ALL = 0x1 | 0x2 | 0x4            # FILE_SHARE_READ | WRITE | DELETE
    OPEN_EXISTING, ERROR_SHARING_VIOLATION = 3, 32
    INVALID = ctypes.c_void_p(-1).value
    deadline = time.monotonic() + timeout
    while True:
        h = k32.CreateFileW(path, DELETE, SHARE_ALL, None, OPEN_EXISTING, 0, None)
        if h and h != INVALID:
            k32.CloseHandle(h)
            return True
        if ctypes.get_last_error() != ERROR_SHARING_VIOLATION:
            return True        # 其他錯誤（權限等）跟「被佔用」無關，不擋
        if time.monotonic() >= deadline:
            return False
        QApplication.processEvents()
        time.sleep(0.05)


# 只有真正從 __main__ 啟動的程式才開啟（測試裡關視窗不能把整個 pytest 砍掉）
EXIT_WATCHDOG_ENABLED = False


def _arm_exit_watchdog(seconds: float = 6.0) -> None:
    """真的要結束程式時的保險：萬一 mpv 收尾卡住，幾秒後強制結束行程，
    避免 PlayCut 在背景殘留、把影片檔一直鎖著。正常結束的話這個執行緒會跟著消失。"""
    if not EXIT_WATCHDOG_ENABLED:
        return
    import threading

    def _kill():
        _debug_log("exit watchdog fired: forcing process exit")
        os._exit(0)

    t = threading.Timer(seconds, _kill)
    t.daemon = True
    t.start()


def _debug_log(msg: str) -> None:
    """疑難排解用：寫到暫存資料夾的 PlayCut-debug.log。"""
    try:
        import tempfile
        import time
        with open(os.path.join(tempfile.gettempdir(), "PlayCut-debug.log"),
                  "a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except Exception:
        pass


HELP_GESTURES = N_("""<b>觸控手勢（觸控螢幕 / 滑鼠皆可）</b><br>
• 左右滑 —— 拉進度條（滑動中即時預覽，放開才真的跳過去）<br>
• 上下滑 —— 音量<br>
• 觸控單指點（點哪裡都一樣）/ 滑鼠單擊 —— 播放 / 暫停<br>
• 觸控兩指點 —— 切換全螢幕<br>
• 滑鼠雙擊左 1/3 —— 倒退 10 秒；右 1/3 —— 快轉 10 秒；中間 —— 全螢幕<br>
• 滑鼠中鍵 —— 切換全螢幕<br>
• 長按 —— 兩倍速播放，放開恢復<br>
• 觸控板兩指左右滑 / 滾輪 —— 拉進度、上下 —— 音量<br>
""")

HELP_MARKERS = N_("""<br><b>旗標怎麼用</b><br>
第 1 個旗標是起點、第 2 個是終點、第 3 個又是起點…<br>
例如在 01:00 和 02:00 各插一個，就會匯出 01:00–02:00 這一段。<br>
在旗標面板可以把某個旗標固定成起點或終點。
""")

HELP_SUBS = N_("""<br><b>字幕</b><br>
• 跟影片同名的字幕（abc.mp4 → abc.srt / abc.zh-TW.srt）會自動載入<br>
• 其他字幕檔：直接拖進視窗，或 字幕 → 載入字幕檔…（srt / ass / vtt / sup…）<br>
• 影片跟字幕可以一起拖進來<br>
• 匯出時可以另存對齊片段的 .srt，或把字幕燒進畫面；字幕延遲也會一起套用
""")

ABOUT_TEXT = N_("""<b>PlayCut</b><br>
一個給 Windows / macOS 用的影片播放 / 標記 / 剪輯工具。<br><br>
• 不會跳出更新通知<br>
• 播放核心 libmpv，剪輯核心 ffmpeg<br>
• 智慧剪輯模式讓起點<b>完全精準</b>，沒有 LosslessCut 的關鍵影格偏移問題<br>
• 聲音延遲校正可以直接烘焙進輸出檔
""")


def apply_dark_theme(app: QApplication):
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(30, 34, 42))
    pal.setColor(QPalette.WindowText, QColor(230, 236, 245))
    pal.setColor(QPalette.Base, QColor(35, 40, 48))
    pal.setColor(QPalette.AlternateBase, QColor(38, 44, 53))
    pal.setColor(QPalette.Text, QColor(230, 236, 245))
    pal.setColor(QPalette.Button, QColor(47, 53, 64))
    pal.setColor(QPalette.ButtonText, QColor(230, 236, 245))
    pal.setColor(QPalette.Highlight, QColor(63, 127, 208))
    pal.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    pal.setColor(QPalette.ToolTipBase, QColor(38, 43, 52))
    pal.setColor(QPalette.ToolTipText, QColor(230, 236, 245))
    app.setPalette(pal)
    app.setStyleSheet(DARK_QSS)
