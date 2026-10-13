"""匯出設定對話框與背景執行緒。"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFileDialog, QFormLayout,
                               QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QProgressBar, QPushButton,
                               QSpinBox, QVBoxLayout, QWidget)

from . import exporter as EX
from . import subtitles as SUB
from .ffio import fmt_time
from .i18n import N_, tr


class ExportWorker(QObject):
    progress = Signal(float, str)
    finished = Signal(list)
    failed = Signal(str)

    def __init__(self, src: str, segments: list[EX.Segment], opts: EX.ExportOptions):
        super().__init__()
        self.src = src
        self.segments = segments
        self.opts = opts
        self.runner = EX.Runner()

    def run(self):
        try:
            out = EX.export_all(self.src, self.segments, self.opts, self.runner,
                                lambda f, m: self.progress.emit(f, m))
            self.finished.emit(out)
        except EX.Cancelled:
            self.failed.emit(tr("已取消"))
        except Exception as exc:
            self.failed.emit(str(exc))

    def cancel(self):
        self.runner.abort()


class ExportDialog(QDialog):
    def __init__(self, parent, src: str, segments: list[EX.Segment],
                 audio_delay: float, default_mode: str = EX.MODE_SMART,
                 default_dir: str = "", subtitle: Optional[SUB.SubSource] = None,
                 default_export_srt: bool = False, default_burn: bool = False,
                 default_hw: bool = True, player_speed: float = 1.0,
                 default_crop: str = "", default_crop_pos: str = "center",
                 default_crop_scale: bool = True, default_crf: int = 22,
                 default_preset: str = "medium", default_vcodec: str = "",
                 default_max_res: int = 0, default_target_on: bool = False,
                 default_target_mb: float = 25.0, default_audio_kbps: int = 0):
        super().__init__(parent)
        self.setWindowTitle(tr("匯出片段"))
        self.setMinimumWidth(1000)
        self.src = src
        self.segments = segments
        self.audio_delay = audio_delay
        self.subtitle = subtitle
        self._thread: Optional[QThread] = None
        self._worker: Optional[ExportWorker] = None
        self.results: list[str] = []
        try:
            self.info: Optional[EX.MediaInfo] = EX.probe(src)
        except Exception:
            self.info = None

        outer = QVBoxLayout(self)
        cols = QHBoxLayout()
        cols.setSpacing(14)
        outer.addLayout(cols, 1)
        left = QVBoxLayout()
        right = QVBoxLayout()
        cols.addLayout(left, 1)
        cols.addLayout(right, 1)
        # 左欄：剪輯方式、聲音、速度與裁切；右欄：來源摘要、字幕、輸出
        root = left

        info = QLabel(self._summary())
        info.setWordWrap(True)
        info.setStyleSheet("color:#cfd6e2;")
        info.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        right.addWidget(info)

        box = QGroupBox(tr("剪輯方式"))
        form = QFormLayout(box)
        self.mode = QComboBox()
        for m in (EX.MODE_SMART, EX.MODE_REENCODE, EX.MODE_LOSSLESS):
            self.mode.addItem(tr(EX.MODE_LABELS[m]), m)
        idx = self.mode.findData(default_mode)
        self.mode.setCurrentIndex(max(0, idx))
        self.mode.currentIndexChanged.connect(self._mode_changed)
        form.addRow(tr("模式"), self.mode)

        self.mode_hint = QLabel("")
        self.mode_hint.setWordWrap(True)
        self.mode_hint.setStyleSheet("color:#9fb0c8; font-size:12px;")
        form.addRow("", self.mode_hint)

        self.crf = QSpinBox()
        self.crf.setRange(0, 40)
        self.crf.setValue(max(0, min(40, int(default_crf))))
        self.crf.setToolTip(tr("重新編碼的畫質，數字越小畫質越好、檔案越大。\n"
                               "22 一般人看不出差別；16 接近無損但檔案約大一倍；每 +6 檔案約小一半。"))
        form.addRow(tr("重編碼畫質 CRF"), self.crf)

        self.preset = QComboBox()
        self.preset.addItems(["ultrafast", "veryfast", "faster", "fast",
                              "medium", "slow", "slower"])
        self.preset.setCurrentText(default_preset if self.preset.findText(default_preset) >= 0
                                   else "medium")
        self.preset.setToolTip(tr("越慢壓縮效率越好：同樣畫質下 slow 的檔案會比 medium 小一些"))
        form.addRow(tr("編碼速度"), self.preset)

        self.hw_accel = QCheckBox(tr("使用顯卡加速（NVIDIA / Intel / AMD，失敗會自動改用 CPU）"))
        self.hw_accel.setChecked(default_hw)
        self.hw_accel.setToolTip(
            tr("「全部重新編碼」和「燒錄字幕」時用顯卡編碼，速度快很多。\n"
            "智慧剪輯開頭那一小段仍用 CPU，確保跟直接複製的部分接得起來。\n"
            "用顯卡時 CRF 會當成對應的品質值（NVENC 的 CQ 等），檔案可能稍大。"))
        form.addRow("", self.hw_accel)
        root.addWidget(box)

        abox = QGroupBox(tr("聲音"))
        aform = QFormLayout(abox)
        self.apply_delay = QCheckBox(
            tr("把目前的聲音延遲 {ms:+.0f} ms 套用到輸出檔", ms=audio_delay*1000))
        self.apply_delay.setChecked(abs(audio_delay) > 1e-6)
        self.apply_delay.setEnabled(abs(audio_delay) > 1e-6)
        aform.addRow(self.apply_delay)
        note = QLabel(tr("套用延遲時聲音會重新編碼（畫面仍維持原樣），"
                      "輸出檔就會跟你在播放器裡聽到的完全一致。"))
        note.setWordWrap(True)
        note.setStyleSheet("color:#9fb0c8; font-size:12px;")
        aform.addRow(note)
        root.addWidget(abox)

        vbox = QGroupBox(tr("速度與短影音裁切"))
        vform = QFormLayout(vbox)
        srow = QHBoxLayout()
        srow.setContentsMargins(0, 0, 0, 0)
        self.apply_speed = QCheckBox(tr("套用播放速度"))
        self.speed = QDoubleSpinBox()
        self.speed.setRange(0.1, 10.0)
        self.speed.setDecimals(2)
        self.speed.setSingleStep(0.05)
        self.speed.setSuffix(" ×")
        self.speed.setMinimumWidth(100)
        self.speed.setKeyboardTracking(False)   # 打完字再更新，避免打 "1" 就被當成 1×
        self.speed.setValue(player_speed if player_speed > 0 else 1.0)
        self.speed.setToolTip(tr("輸出影片的速度：2 = 兩倍速（長度減半），0.5 = 慢動作。\n"
                              "聲音用 atempo 變速，音高不變。"))
        self.apply_speed.setChecked(abs(player_speed - 1.0) > 1e-6)
        self.apply_speed.setToolTip(tr("預設帶入目前播放器的速度 {s:g}×，可以直接改數字", s=player_speed))
        srow.addWidget(self.apply_speed)
        srow.addWidget(self.speed)
        srow.addStretch(1)
        sw = QWidget()
        sw.setLayout(srow)
        vform.addRow(tr("速度"), sw)

        self.crop = QComboBox()
        self.crop.addItem(tr("不裁切"), "")
        for key, (_, _, _, _, label) in EX.CROP_PRESETS.items():
            self.crop.addItem(tr(label), key)
        self.crop.setCurrentIndex(max(0, self.crop.findData(default_crop)))
        vform.addRow(tr("裁切比例"), self.crop)

        self.crop_pos = QComboBox()
        for key, (_, label) in EX.CROP_POSITIONS.items():
            self.crop_pos.addItem(tr(label), key)
        self.crop_pos.setCurrentIndex(max(0, self.crop_pos.findData(default_crop_pos)))
        self.crop_pos.setToolTip(tr("橫式影片裁成直式時，取畫面的哪一邊"))
        vform.addRow(tr("裁切位置"), self.crop_pos)

        self.crop_scale = QCheckBox(tr("縮放到上面標示的解析度（不勾 = 保留裁切後的原始解析度）"))
        self.crop_scale.setChecked(default_crop_scale)
        vform.addRow(self.crop_scale)

        vnote = QLabel(tr("套用速度或裁切時，會改用「全部重新編碼」。"
                       "輸出檔名會自動加上 _2x、_4x5 之類的後綴。"))
        vnote.setWordWrap(True)
        vnote.setStyleSheet("color:#9fb0c8; font-size:12px;")
        vform.addRow(vnote)
        root.addWidget(vbox)
        left.addStretch(1)
        root = right

        self.apply_speed.toggled.connect(self._mode_changed)
        self.speed.valueChanged.connect(self._speed_edited)
        self.crop.currentIndexChanged.connect(self._mode_changed)

        sbox = QGroupBox(tr("字幕"))
        sform = QFormLayout(sbox)
        sub = subtitle
        if sub is None:
            cur = QLabel(tr("目前沒有開啟字幕（字幕 → 載入字幕檔…，或切換到內嵌字幕軌）"))
        else:
            d = (tr("，字幕延遲 {ms:+.0f} ms 會一起套用", ms=sub.delay*1000)
                 if abs(sub.delay) > 1e-6 else "")
            cur = QLabel(tr("目前字幕：{name}", name=sub.label) + d)
        cur.setWordWrap(True)
        cur.setStyleSheet("color:#cfd6e2;")
        sform.addRow(cur)
        self.export_srt = QCheckBox(tr("每個輸出檔旁邊另存對應的 .srt 字幕（時間自動對齊片段）"))
        self.burn_sub = QCheckBox(tr("把字幕燒進畫面（硬字幕，一律整段重新編碼）"))
        text_ok = sub is not None and sub.is_text
        self.export_srt.setEnabled(text_ok)
        self.burn_sub.setEnabled(text_ok)
        self.export_srt.setChecked(text_ok and default_export_srt)
        self.burn_sub.setChecked(text_ok and default_burn)
        if sub is not None and not text_ok:
            self.export_srt.setToolTip(tr("圖像字幕（PGS / VobSub）無法轉成 .srt"))
            self.burn_sub.setToolTip(tr("圖像字幕（PGS / VobSub）目前不支援燒錄"))
        self.burn_sub.toggled.connect(self._mode_changed)
        sform.addRow(self.export_srt)
        sform.addRow(self.burn_sub)
        root.addWidget(sbox)

        cbox = QGroupBox(tr("壓縮（讓檔案變小）"))
        cform = QFormLayout(cbox)
        self.vcodec = QComboBox()
        for key, label in EX.OUT_CODECS.items():
            self.vcodec.addItem(tr(label), key)
        self.vcodec.setCurrentIndex(max(0, self.vcodec.findData(default_vcodec)))
        self.vcodec.setToolTip(tr("H.265 同樣畫質下檔案約小 30～50%，但編碼較慢，"
                                  "部分舊裝置或網站可能無法播放"))
        cform.addRow(tr("影片編碼"), self.vcodec)

        self.max_res = QComboBox()
        for n in EX.RES_LIMITS:
            self.max_res.addItem(tr("原始解析度") if n == 0 else f"{n}p", n)
        self.max_res.setCurrentIndex(max(0, self.max_res.findData(int(default_max_res))))
        self.max_res.setToolTip(tr("以短邊計算（直式影片也適用），只會縮小、不會放大"))
        cform.addRow(tr("解析度上限"), self.max_res)

        self.audio_kbps = QComboBox()
        self.audio_kbps.addItem(tr("自動（雙聲道最多 160 kbps）"), 0)
        for k in (96, 128, 160, 192, 256, 320):
            self.audio_kbps.addItem(f"{k} kbps", k)
        self.audio_kbps.setCurrentIndex(max(0, self.audio_kbps.findData(int(default_audio_kbps))))
        cform.addRow(tr("聲音位元率"), self.audio_kbps)

        trow = QHBoxLayout()
        trow.setContentsMargins(0, 0, 0, 0)
        self.target_on = QCheckBox(tr("指定檔案大小"))
        self.target_mb = QDoubleSpinBox()
        self.target_mb.setRange(1.0, 100000.0)
        self.target_mb.setDecimals(1)
        self.target_mb.setSingleStep(5.0)
        self.target_mb.setSuffix(" MB")
        self.target_mb.setMinimumWidth(110)
        self.target_mb.setKeyboardTracking(False)
        self.target_mb.setValue(default_target_mb if default_target_mb > 0 else 25.0)
        self.target_on.setChecked(default_target_on)
        self.target_on.setToolTip(tr("依片段長度自動算出位元率，用 CPU 兩階段編碼，"
                                     "輸出大小會很接近設定值（會略小一點）。\n"
                                     "不分段時是每個輸出檔的大小；合併時是整個檔案的大小。"))
        trow.addWidget(self.target_on)
        trow.addWidget(self.target_mb)
        trow.addStretch(1)
        tw = QWidget()
        tw.setLayout(trow)
        cform.addRow(tr("目標大小"), tw)

        self.compress_hint = QLabel("")
        self.compress_hint.setWordWrap(True)
        self.compress_hint.setStyleSheet("color:#9fb0c8; font-size:12px;")
        cform.addRow(self.compress_hint)
        root.addWidget(cbox)

        self.vcodec.currentIndexChanged.connect(self._mode_changed)
        self.max_res.currentIndexChanged.connect(self._mode_changed)
        self.audio_kbps.currentIndexChanged.connect(self._mode_changed)
        self.target_on.toggled.connect(self._mode_changed)
        self.target_mb.valueChanged.connect(self._target_edited)

        obox = QGroupBox(tr("輸出"))
        oform = QFormLayout(obox)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        self.out_dir = QLineEdit(default_dir or str(Path(src).parent))
        btn = QPushButton(tr("瀏覽…"))
        btn.clicked.connect(self._pick_dir)
        row.addWidget(self.out_dir, 1)
        row.addWidget(btn)
        w = QWidget()
        w.setLayout(row)
        oform.addRow(tr("資料夾"), w)

        self.container = QComboBox()
        self.container.addItem(tr("跟來源相同"), "")
        for c in ("mp4", "mkv", "mov", "ts", "webm"):
            self.container.addItem("." + c, c)
        oform.addRow(tr("容器格式"), self.container)

        self.merge = QCheckBox(tr("把所有片段接成一個檔案"))
        self.merge.setEnabled(len(segments) > 1)
        self.merge.toggled.connect(self._mode_changed)
        oform.addRow(self.merge)
        root.addWidget(obox)
        right.addStretch(1)
        root = outer

        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(True)
        self.bar.setFormat("%p%")
        root.addWidget(self.bar)
        self.status = QLabel("")
        self.status.setStyleSheet("color:#9fb0c8;")
        root.addWidget(self.status)

        self.buttons = QDialogButtonBox()
        self.start_btn = self.buttons.addButton(tr("開始匯出"),
                                                QDialogButtonBox.AcceptRole)
        self.cancel_btn = self.buttons.addButton(tr("關閉"),
                                                 QDialogButtonBox.RejectRole)
        self.start_btn.clicked.connect(self._start)
        self.cancel_btn.clicked.connect(self._close_or_cancel)
        root.addWidget(self.buttons)

        self._mode_changed()

    # ------------------------------------------------------------------
    def _summary(self) -> str:
        lines = ["<b>" + tr("來源：") + "</b>" + os.path.basename(self.src),
                 "<b>" + tr("片段：") + "</b>" + tr("共 {n} 段", n=len(self.segments))]
        for i, s in enumerate(self.segments[:8], 1):
            lines.append(f"　{i}. {fmt_time(s.start)} → {fmt_time(s.end)}　"
                         + tr("({sec:.3f} 秒)", sec=s.duration))
        if len(self.segments) > 8:
            lines.append("　" + tr("… 還有 {n} 段", n=len(self.segments) - 8))
        return "<br>".join(lines)

    HINTS = {
        EX.MODE_SMART: N_("起點所在的那一小段重新編碼，其餘直接複製。"
                       "起點完全精準、不會像 LosslessCut 那樣往前偏移，速度也接近無損剪輯。"),
        EX.MODE_REENCODE: N_("整段重新編碼。最精準、相容性最好，但最慢，而且畫質會依 CRF 略有損失。"),
        EX.MODE_LOSSLESS: N_("完全不重新編碼，最快也完全無損 —— 但起點會被拉到前一個關鍵影格"
                          "（也就是 LosslessCut 的偏移問題），最多可能早好幾秒。"),
    }

    def _target_edited(self, *_):
        # 改了大小就自動勾「指定檔案大小」
        if not self.target_on.isChecked():
            self.target_on.setChecked(True)
        else:
            self._mode_changed()

    def _compress_opts(self) -> EX.ExportOptions:
        return EX.ExportOptions(
            v_codec=self.vcodec.currentData() or "",
            max_short_side=int(self.max_res.currentData() or 0),
            target_mb=self.target_mb.value() if self.target_on.isChecked() else 0.0,
            audio_bitrate=int(self.audio_kbps.currentData() or 0),
            speed=self._speed_value(),
        )

    def _compress_text(self) -> str:
        """壓縮區塊下方的說明：來源資訊 + 指定大小時預估的影片位元率。"""
        lines: list[str] = []
        info = self.info
        if info and info.has_video and info.v_width and info.v_height:
            src = f"{info.v_width}×{info.v_height}"
            if info.v_codec:
                src += f" · {info.v_codec.upper()}"
            try:
                size = os.path.getsize(self.src)
                if info.duration > 0:
                    src += f" · {size * 8 / 1000 / info.duration / 1000:.1f} Mbps"
            except OSError:
                pass
            lines.append(tr("來源：{desc}", desc=src))
        if not self.target_on.isChecked():
            return "\n".join(lines)
        o = self._compress_opts()
        a_k = EX.audio_kbps(info, o) if (info and info.has_audio) else 0
        sp = EX.eff_speed(o)
        merge = getattr(self, "merge", None)
        if merge is not None and merge.isChecked() and len(self.segments) > 1:
            durs = [sum(s.duration for s in self.segments) / sp]
        else:
            durs = [s.duration / sp for s in self.segments]
        ks = [EX.target_video_kbps(o.target_mb, d, a_k) for d in durs if d > 0]
        if ks:
            lo, hi = min(ks), max(ks)
            rng = f"{lo}" if lo == hi else f"{lo}–{hi}"
            lines.append(tr("預估影片位元率約 {k} kbps（用 CPU 兩階段編碼）", k=rng))
            if lo < 500:
                lines.append("⚠ " + tr("位元率很低，畫質可能會很差：可以調大目標大小、"
                                      "降低解析度，或把片段剪短"))
        return "\n".join(lines)

    def _speed_value(self) -> float:
        return self.speed.value() if self.apply_speed.isChecked() else 1.0

    def _speed_edited(self, *_):
        # 輸入框永遠可以點、可以打字；改了數字就自動勾「套用播放速度」
        if not self.apply_speed.isChecked() and abs(self.speed.value() - 1.0) > 1e-6:
            self.apply_speed.setChecked(True)   # toggled 會觸發 _mode_changed
        else:
            self._mode_changed()

    def _mode_changed(self, *_):
        m = self.mode.currentData()
        hint = tr(self.HINTS.get(m, "")) if m in self.HINTS else ""
        burn = hasattr(self, "burn_sub") and self.burn_sub.isChecked()
        reasons = []
        if burn:
            reasons.append(tr("燒錄字幕"))
        if hasattr(self, "speed"):
            if abs(self._speed_value() - 1.0) > 1e-6:
                reasons.append(tr("{s:g}× 速度", s=self._speed_value()))
            has_crop = bool(self.crop.currentData())
            self.crop_pos.setEnabled(has_crop)
            self.crop_scale.setEnabled(has_crop)
            if has_crop:
                reasons.append(tr("{ratio} 裁切", ratio=self.crop.currentData()))
        if hasattr(self, "compress_hint"):
            if EX.compress_active(self._compress_opts(), self.info):
                reasons.append(tr("壓縮"))
            self.compress_hint.setText(self._compress_text())
        force = bool(reasons)
        if force and m != EX.MODE_REENCODE:
            hint += "\n⚠ " + tr("已設定{what}：這次會改用「全部重新編碼」。",
                               what=tr("、").join(reasons))
        self.mode_hint.setText(hint)
        re_enc = m != EX.MODE_LOSSLESS or force
        self.crf.setEnabled(re_enc)
        self.preset.setEnabled(re_enc)
        # 只有整段重新編碼時才會用到顯卡
        # 指定檔案大小時一律用 CPU 兩階段編碼
        target = hasattr(self, "target_on") and self.target_on.isChecked()
        self.hw_accel.setEnabled((m == EX.MODE_REENCODE or force) and not target)
        self.crf.setEnabled(re_enc and not target)

    def _pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, tr("選擇輸出資料夾"),
                                             self.out_dir.text())
        if d:
            self.out_dir.setText(d)

    # ------------------------------------------------------------------
    def _options(self) -> EX.ExportOptions:
        return EX.ExportOptions(
            mode=self.mode.currentData(),
            audio_delay=self.audio_delay,
            apply_audio_delay=self.apply_delay.isChecked(),
            out_dir=self.out_dir.text().strip(),
            container=self.container.currentData(),
            crf=self.crf.value(),
            preset=self.preset.currentText(),
            hw_accel=self.hw_accel.isChecked(),
            merge=self.merge.isChecked(),
            subtitle=self.subtitle,
            burn_subtitles=self.burn_sub.isChecked(),
            export_srt=self.export_srt.isChecked(),
            speed=self._speed_value(),
            crop=self.crop.currentData() or "",
            crop_pos=self.crop_pos.currentData() or "center",
            crop_scale=self.crop_scale.isChecked(),
            v_codec=self.vcodec.currentData() or "",
            max_short_side=int(self.max_res.currentData() or 0),
            target_mb=self.target_mb.value() if self.target_on.isChecked() else 0.0,
            audio_bitrate=int(self.audio_kbps.currentData() or 0),
        )

    def _start(self):
        if self._thread:
            return
        opts = self._options()
        try:
            Path(opts.out_dir).mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            QMessageBox.warning(self, tr("輸出資料夾有問題"), str(exc))
            return
        self.start_btn.setEnabled(False)
        self.cancel_btn.setText(tr("取消"))
        self.status.setText(tr("準備中…"))

        self._worker = ExportWorker(self.src, self.segments, opts)
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_done)
        self._worker.failed.connect(self._on_fail)
        self._thread.start()

    def _on_progress(self, frac: float, msg: str):
        self.bar.setValue(int(frac * 1000))
        self.status.setText(msg)

    def _cleanup(self):
        if self._thread:
            self._thread.quit()
            self._thread.wait(3000)
            self._thread = None
        self._worker = None
        self.start_btn.setEnabled(True)
        self.cancel_btn.setText(tr("關閉"))

    def _on_done(self, files: list):
        self.results = files
        self._cleanup()
        self.bar.setValue(1000)
        self.status.setText(tr("完成，共 {n} 個檔案", n=len(files)))
        names = "\n".join(os.path.basename(f) for f in files[:10])
        QMessageBox.information(self, tr("匯出完成"),
                                tr("已輸出到：") + f"\n{self.out_dir.text()}\n\n{names}")
        self.accept()

    def _on_fail(self, msg: str):
        self._cleanup()
        self.status.setText(tr("失敗"))
        if msg != tr("已取消"):
            QMessageBox.critical(self, tr("匯出失敗"), msg)
        else:
            self.status.setText(tr("已取消"))

    def _close_or_cancel(self):
        if self._worker:
            self._worker.cancel()
            self.status.setText(tr("取消中…"))
            return
        self.reject()

    def closeEvent(self, ev):
        if self._worker:
            self._worker.cancel()
            self._cleanup()
        super().closeEvent(ev)
