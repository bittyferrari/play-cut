"""播放畫面 + 觸控手勢 + 螢幕疊加提示（OSD）。

手勢（觸控螢幕與滑鼠皆可）
--------------------------
左右滑      拉進度（滑動中即時預覽，放開才真正跳過去）
上下滑      音量（整個畫面都可以）
觸控單指點  播放 / 暫停（點哪裡都一樣，不做雙擊判定）
觸控兩指點  切換全螢幕
滑鼠單擊    播放 / 暫停
滑鼠雙擊左 1/3  倒退 10 秒；右 1/3  快轉 10 秒；中間  全螢幕
滑鼠中鍵    切換全螢幕
長按        兩倍速播放（放開恢復）
"""
from __future__ import annotations

import time
from typing import Optional

from PySide6.QtCore import (QEvent, QObject, QPoint, QPointF, QRect, QRectF, Qt,
                            QTimer, Signal)
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QPainter, QPainterPath,
                           QPen)
from PySide6.QtWidgets import QWidget

from .ffio import fmt_time
from .mpvwidget import MpvWidget
from .i18n import tr

DRAG_THRESHOLD = 10          # px，超過才判定為手勢
DOUBLE_TAP_MS = 300
TWO_FINGER_TAP_MS = 500      # 兩指點：手指全部離開前的最長時間
LONG_PRESS_MS = 550


class OsdOverlay(QObject):
    """半透明提示層。

    刻意「不是」一個子視窗：在某些平台上，蓋在 QOpenGLWidget 上的子視窗
    會讓底下的影片畫面整個變黑。這裡改成由 VideoView 的 paintGL 直接畫。
    """

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self._host = parent
        self._text = ""
        self._sub = ""
        self._bar: Optional[float] = None     # 0..1，None 代表不畫
        self._visible = False
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.clear)
        self._pinned = False
        # 播放 / 暫停：切換時畫面中央閃一下大圖示；暫停中左上角常駐標示
        self._state_icon: Optional[str] = None     # "play" / "pause" / None
        self._state_timer = QTimer(self)
        self._state_timer.setSingleShot(True)
        self._state_timer.timeout.connect(self._clear_state_icon)
        self.paused_badge = False
        self.badge_enabled = False     # 左上角「已暫停」標籤要不要顯示

    def flash_state(self, paused: bool, msec: int = 650):
        self._state_icon = "pause" if paused else "play"
        self.paused_badge = paused
        self._state_timer.start(msec)
        self._host.update()

    def set_paused_badge(self, paused: bool):
        self.paused_badge = paused
        self._host.update()

    def _clear_state_icon(self):
        self._state_icon = None
        self._host.update()

    @staticmethod
    def _draw_glyph(p: QPainter, kind: str, cx: float, cy: float, r: float,
                    color: QColor):
        """以 (cx, cy) 為中心、半徑 r 的範圍內畫 ▶ 或 ❚❚。"""
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        if kind == "play":
            tri = QPainterPath()
            tri.moveTo(cx - r * 0.45, cy - r * 0.6)
            tri.lineTo(cx - r * 0.45, cy + r * 0.6)
            tri.lineTo(cx + r * 0.62, cy)
            tri.closeSubpath()
            p.drawPath(tri)
        else:
            bw, bh = r * 0.32, r * 1.15
            p.drawRoundedRect(QRectF(cx - r * 0.45, cy - bh / 2, bw, bh), r * 0.07, r * 0.07)
            p.drawRoundedRect(QRectF(cx + r * 0.13, cy - bh / 2, bw, bh), r * 0.07, r * 0.07)

    def _paint_state(self, p: QPainter, width: int, height: int):
        if self.paused_badge and self.badge_enabled:
            # 左上角「已暫停」標籤
            font = QFont(self._host.font())
            font.setPointSizeF(max(10.0, min(16.0, width / 70.0)))
            font.setBold(True)
            fm = QFontMetrics(font)
            text = tr("已暫停")
            ih = fm.height()
            pad = int(ih * 0.45)
            w = pad + ih + int(pad * 0.6) + fm.horizontalAdvance(text) + pad
            h = ih + pad
            rect = QRectF(14, 14, w, h)
            path = QPainterPath()
            path.addRoundedRect(rect, h / 2, h / 2)
            p.fillPath(path, QColor(230, 150, 30, 225))
            self._draw_glyph(p, "pause", rect.x() + pad + ih / 2,
                             rect.center().y(), ih * 0.5, QColor(255, 255, 255))
            p.setFont(font)
            p.setPen(QPen(QColor(255, 255, 255)))
            p.drawText(QRectF(rect.x() + pad + ih + pad * 0.6, rect.y(),
                              fm.horizontalAdvance(text) + 2, h),
                       Qt.AlignVCenter | Qt.AlignLeft, text)
        if self._state_icon:
            r = max(38.0, min(70.0, min(width, height) / 7.0))
            cx, cy = width / 2, height / 2
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, 150))
            p.drawEllipse(QPointF(cx, cy), r, r)
            off = r * 0.08 if self._state_icon == "play" else 0
            self._draw_glyph(p, self._state_icon, cx + off, cy, r * 0.9,
                             QColor(255, 255, 255, 240))

    # 讓呼叫端可以像 widget 一樣用
    def isVisible(self) -> bool:
        return self._visible

    def size(self):
        return self._host.size()

    def clear(self):
        self._text = ""
        self._sub = ""
        self._bar = None
        self._visible = False
        self._host.update()

    def show_message(self, text: str, sub: str = "", bar: Optional[float] = None,
                     msec: int = 1100, pinned: bool = False):
        self._text = text
        self._sub = sub
        self._bar = bar
        self._pinned = pinned
        self._visible = True
        self._hide_timer.stop()
        if not pinned:
            self._hide_timer.start(msec)
        self._host.update()

    def render(self, device):
        """給測試用：把目前的 OSD 畫到任意 paint device 上。"""
        p = QPainter(device)
        self.paint(p, self._host.width(), self._host.height())
        p.end()

    def paint(self, p: QPainter, width: int, height: int):
        if (self.paused_badge and self.badge_enabled) or self._state_icon:
            p.save()
            p.setRenderHint(QPainter.Antialiasing, True)
            p.setRenderHint(QPainter.TextAntialiasing, True)
            self._paint_state(p, width, height)
            p.restore()
        if not self._visible or (not self._text and self._bar is None):
            return
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)

        font = QFont(self._host.font())
        font.setPointSizeF(max(14.0, min(30.0, width / 34.0)))
        font.setBold(True)
        p.setFont(font)
        fm = QFontMetrics(font)

        sub_font = QFont(font)
        sub_font.setPointSizeF(font.pointSizeF() * 0.62)
        sub_font.setBold(False)
        sub_fm = QFontMetrics(sub_font)

        tw = fm.horizontalAdvance(self._text)
        th = fm.height()
        sw = sub_fm.horizontalAdvance(self._sub) if self._sub else 0
        sh = sub_fm.height() if self._sub else 0
        barh = 8 if self._bar is not None else 0
        pad = int(th * 0.55)

        w = max(tw, sw, 220 if self._bar is not None else 0) + pad * 2
        h = th + (sh + 6 if self._sub else 0) + (barh + 12 if barh else 0) + pad * 2
        x = (width - w) // 2
        y = int(height * 0.5 - h / 2)

        path = QPainterPath()
        path.addRoundedRect(QRect(x, y, w, h), 14, 14)
        p.fillPath(path, QColor(0, 0, 0, 175))

        p.setPen(QPen(QColor(255, 255, 255, 240)))
        p.drawText(QRect(x, y + pad, w, th), Qt.AlignHCenter | Qt.AlignVCenter,
                   self._text)
        cy = y + pad + th
        if self._sub:
            p.setFont(sub_font)
            p.setPen(QPen(QColor(210, 218, 228, 225)))
            p.drawText(QRect(x, cy + 4, w, sh), Qt.AlignHCenter | Qt.AlignVCenter,
                       self._sub)
            cy += sh + 6
        if self._bar is not None:
            bw = w - pad * 2
            bx = x + pad
            by = cy + 8
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 60))
            p.drawRoundedRect(QRect(bx, by, bw, barh), 4, 4)
            p.setBrush(QColor(90, 175, 255, 245))
            p.drawRoundedRect(QRect(bx, by, max(4, int(bw * self._bar)), barh), 4, 4)
        p.restore()


class VideoView(MpvWidget):
    """加上手勢與 OSD 的播放畫面。"""

    tapped = Signal()
    doubleTapCenter = Signal()
    seekPreview = Signal(float)
    seekCommitted = Signal(float)
    requestFullscreenToggle = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_AcceptTouchEvents, True)
        self.setMouseTracking(True)
        self.osd = OsdOverlay(self)

        # 一次全寬度滑動所代表的秒數（可在設定調整）
        self.swipe_span = 120.0
        self.gesture_enabled = True

        self._active = False
        self._mode: Optional[str] = None      # seek / volume
        self._is_touch = False                # 這次手勢是不是來自觸控
        self._multi = False                   # 觸控中出現過第二根手指
        self._multi_moved = False
        self._multi_max = 0
        self._multi_ts = 0.0
        self._p0 = QPointF()
        self._t0 = 0.0
        self._vol0 = 100.0
        self._target = 0.0
        self._last_tap = 0.0
        self._tap_pos = QPointF()
        self._press_ts = 0.0
        self._long_press_active = False
        self._speed_before_long = 1.0
        self._long_timer = QTimer(self)
        self._long_timer.setSingleShot(True)
        self._long_timer.timeout.connect(self._start_long_press)

        self._last_paused: Optional[bool] = None
        self.pausedChanged.connect(self._on_paused_osd)

    def _on_paused_osd(self, paused: bool):
        # 第一次（剛載入）只設定標籤，不閃中央圖示
        if self._last_paused is None or self._last_paused == paused:
            self.osd.set_paused_badge(paused)
        else:
            self.osd.flash_state(paused)
        self._last_paused = paused

    # ------------------------------------------------------------------
    def paint_overlay(self, painter):
        self.osd.paint(painter, self.width(), self.height())

    def flash(self, text: str, sub: str = "", bar: Optional[float] = None,
              msec: int = 1000):
        self.osd.show_message(text, sub, bar, msec)

    # ------------------------------------------------------------------
    # 事件入口
    # ------------------------------------------------------------------
    def event(self, ev):
        t = ev.type()
        if t == QEvent.TouchBegin:
            pts = ev.points()
            self._multi = False
            self._multi_moved = False
            self._multi_max = len(pts)
            self._multi_ts = time.monotonic()
            if len(pts) == 1:
                self._begin(pts[0].position(), touch=True)
            else:
                self._enter_multi()
                self._track_multi(pts)
            ev.accept()
            return True
        if t == QEvent.TouchUpdate:
            pts = ev.points()
            if len(pts) >= 2 and not self._multi:
                self._enter_multi()
            if self._multi:
                self._track_multi(pts)
                ev.accept()
                return True
            if self._active and pts:
                self._move(pts[0].position())
                ev.accept()
                return True
            return super().event(ev)
        if t in (QEvent.TouchEnd, QEvent.TouchCancel):
            pts = ev.points()
            if self._multi:
                self._track_multi(pts)
                quick = (time.monotonic() - self._multi_ts) * 1000 < TWO_FINGER_TAP_MS
                if t == QEvent.TouchEnd and self._multi_max == 2 \
                        and not self._multi_moved and quick:
                    # 兩指點一下 = 全螢幕
                    self.requestFullscreenToggle.emit()
                    self.doubleTapCenter.emit()
                self._multi = False
                ev.accept()
                return True
            if self._active:
                pos = pts[0].position() if pts else self._p0
                self._end(pos, cancelled=(t == QEvent.TouchCancel))
                ev.accept()
                return True
            return super().event(ev)
        return super().event(ev)

    def _enter_multi(self):
        """第二根手指放上來：取消單指手勢，改成追蹤兩指點。"""
        self._multi = True
        if self._active:
            self._long_timer.stop()
            if self._long_press_active:
                self._stop_long_press()
            if self._mode is not None:
                # 已經在滑了，不算點擊
                self._multi_moved = True
                if self._mode == "seek":
                    self.seek_absolute(self._target, exact=True)
                    self.seekCommitted.emit(self._target)
            self._active = False
            self._mode = None

    def _track_multi(self, pts):
        self._multi_max = max(self._multi_max, len(pts))
        for p in pts:
            if (p.position() - p.pressPosition()).manhattanLength() > DRAG_THRESHOLD * 2:
                self._multi_moved = True

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            # 系統從觸控合成的滑鼠事件也當作觸控（單擊不做雙擊判定）
            self._begin(ev.position(),
                        touch=ev.source() != Qt.MouseEventNotSynthesized)
            ev.accept()
            return
        if ev.button() == Qt.MiddleButton:
            # 滑鼠中鍵 = 切換全螢幕
            self.requestFullscreenToggle.emit()
            ev.accept()
            return
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if self._active:
            self._move(ev.position())
            ev.accept()
            return
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        if self._active and ev.button() == Qt.LeftButton:
            self._end(ev.position())
            ev.accept()
            return
        super().mouseReleaseEvent(ev)

    def mouseDoubleClickEvent(self, ev):
        # 雙擊由 _begin/_end 的計時邏輯處理，這裡吃掉避免重複
        ev.accept()

    def wheelEvent(self, ev):
        """觸控板兩指滑動 / 滑鼠滾輪。"""
        if not self.gesture_enabled:
            return super().wheelEvent(ev)
        px = ev.pixelDelta()
        ang = ev.angleDelta()
        dx = px.x() if not px.isNull() else ang.x()
        dy = px.y() if not px.isNull() else ang.y()
        if not px.isNull() and abs(dy) >= abs(dx):
            # macOS 觸控板一次滑動會送出幾十個小事件（外加慣性捲動），
            # 累積到一定距離才調一次音量，不然音量會瞬間衝到底。
            if ev.phase() == Qt.ScrollMomentum:
                ev.accept()
                return
            self._wheel_acc_y = getattr(self, "_wheel_acc_y", 0) + dy
            if abs(self._wheel_acc_y) < 40:
                ev.accept()
                return
            dy, self._wheel_acc_y = self._wheel_acc_y, 0
        if abs(dx) > abs(dy) and dx:
            # 水平 = 拉進度
            span = self.swipe_span
            step = (dx / max(1, self.width())) * span
            self.seek_relative(-step if px.isNull() else step, exact=False)
            tgt = max(0.0, min(self.duration, self.position + step))
            self.flash("⏩ " + fmt_time(tgt, ms=False),
                       tr("{s:+.1f} 秒", s=step),
                       (tgt / self.duration) if self.duration else None, 700)
            ev.accept()
            return
        if dy:
            vol = max(0.0, min(150.0, self.get_volume() + (5 if dy > 0 else -5)))
            self.set_volume(vol)
            self.flash(f"🔊 {vol:.0f}%", bar=vol / 150.0, msec=700)
            ev.accept()
            return
        super().wheelEvent(ev)

    # ------------------------------------------------------------------
    # 手勢狀態機
    # ------------------------------------------------------------------
    def _begin(self, pos: QPointF, touch: bool = False):
        if not self.gesture_enabled:
            return
        self._active = True
        self._is_touch = touch
        self._mode = None
        self._p0 = QPointF(pos)
        self._t0 = self.position
        self._target = self._t0
        self._vol0 = self.get_volume()
        self._press_ts = time.monotonic()
        self._long_press_active = False
        self._long_timer.start(LONG_PRESS_MS)

    def _move(self, pos: QPointF):
        if not self._active:
            return
        dx = pos.x() - self._p0.x()
        dy = pos.y() - self._p0.y()
        if self._mode is None:
            if max(abs(dx), abs(dy)) < DRAG_THRESHOLD:
                return
            self._long_timer.stop()
            if self._long_press_active:
                self._stop_long_press()
            if abs(dx) >= abs(dy):
                self._mode = "seek"
            else:
                self._mode = "volume"

        if self._mode == "seek":
            span = self.swipe_span
            delta = (dx / max(1, self.width())) * span
            dur = self.duration or 0.0
            self._target = max(0.0, min(dur if dur else self._t0 + delta,
                                        self._t0 + delta))
            arrow = "⏩" if delta >= 0 else "⏪"
            self.flash(f"{arrow} {fmt_time(self._target, ms=False)}",
                       tr("{s:+.1f} 秒", s=delta) + "　/　" + fmt_time(dur, ms=False),
                       (self._target / dur) if dur else None, 4000)
            self.seekPreview.emit(self._target)
            # 拖曳時用 keyframe seek，順暢不卡
            self.seek_absolute(self._target, exact=False)
        elif self._mode == "volume":
            vol = max(0.0, min(150.0, self._vol0 - dy / max(1, self.height()) * 200.0))
            self.set_volume(vol)
            self.flash(f"🔊 {vol:.0f}%", bar=vol / 150.0, msec=4000)

    def _end(self, pos: QPointF, cancelled: bool = False):
        self._long_timer.stop()
        was_long = self._long_press_active
        if was_long:
            self._stop_long_press()
        mode, self._mode = self._mode, None
        self._active = False
        if cancelled:
            self.osd.clear()
            return

        if mode == "seek":
            self.seek_absolute(self._target, exact=True)
            self.seekCommitted.emit(self._target)
            self.osd.show_message(f"▶ {fmt_time(self._target, ms=False)}",
                                  "", None, 600)
            return
        if mode == "volume":
            return
        if was_long:
            return

        if self._is_touch:
            # 觸控：單指點哪裡都是播放 / 暫停，不做雙擊判定
            self._last_tap = 0.0
            self._single_tap()
            return

        # 單擊 / 雙擊
        now = time.monotonic()
        if (now - self._last_tap) * 1000 < DOUBLE_TAP_MS and \
                (pos - self._tap_pos).manhattanLength() < 40:
            self._last_tap = 0.0
            # 第一下已經立即切換了播放/暫停，雙擊時先復原再做雙擊動作
            self.toggle_pause()
            self._double_tap(pos)
        else:
            self._last_tap = now
            self._tap_pos = QPointF(pos)
            # 單擊立即切換，不再等待雙擊判定（避免延遲）
            self._single_tap()

    def _single_tap(self):
        self.toggle_pause()
        self.flash(tr("⏸ 暫停") if self.is_paused() else tr("▶ 播放"), msec=650)
        self.tapped.emit()

    def _double_tap(self, pos: QPointF):
        x = pos.x()
        w = self.width()
        if x < w / 3:
            self.seek_relative(-10.0)
            self.flash(tr("⏪ 10 秒"), msec=700)
        elif x > w * 2 / 3:
            self.seek_relative(10.0)
            self.flash(tr("⏩ 10 秒"), msec=700)
        else:
            self.requestFullscreenToggle.emit()
            self.doubleTapCenter.emit()

    def _start_long_press(self):
        if not self._active or self._mode is not None:
            return
        self._long_press_active = True
        self._speed_before_long = self.get_speed()
        self.set_speed(min(4.0, self._speed_before_long * 2.0))
        self.osd.show_message(f"⏩ {self.get_speed():.2f}×", tr("放開恢復"),
                              None, 3000, pinned=True)

    def _stop_long_press(self):
        self._long_press_active = False
        self.set_speed(self._speed_before_long)
        self.osd.clear()
