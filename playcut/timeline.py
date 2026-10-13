"""帶旗標的進度條。支援滑鼠拖曳與觸控。"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEvent, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QFontMetrics, QLinearGradient,
                           QPainter, QPainterPath, QPen, QPolygonF)
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from .ffio import fmt_time
from .markers import MarkerList, ROLE_IN

BG = QColor(38, 42, 50)
TRACK = QColor(58, 64, 76)
PLAYED = QColor(88, 166, 255)
SEG = QColor(70, 190, 130, 110)
IN_C = QColor(80, 210, 140)
OUT_C = QColor(240, 110, 110)
CURSOR = QColor(255, 255, 255)


class Timeline(QWidget):
    seekRequested = Signal(float)       # 放開後的最終位置
    scrubbing = Signal(float)           # 拖曳中
    markerClicked = Signal(int)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumHeight(52)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setAttribute(Qt.WA_AcceptTouchEvents, True)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)

        self.duration = 0.0
        self.position = 0.0
        self.markers: Optional[MarkerList] = None
        self._dragging = False
        self._hover_x: Optional[float] = None

    # ------------------------------------------------------------------
    def set_markers(self, markers: MarkerList):
        self.markers = markers
        self.update()

    def set_duration(self, d: float):
        self.duration = max(0.0, float(d or 0.0))
        self.update()

    def set_position(self, t: float):
        if self._dragging:
            return
        self.position = max(0.0, float(t or 0.0))
        self.update()

    # ------------------------------------------------------------------
    def _bar_rect(self) -> QRect:
        return QRect(10, self.height() // 2 - 5, max(1, self.width() - 20), 10)

    def _t_from_x(self, x: float) -> float:
        r = self._bar_rect()
        if r.width() <= 0 or self.duration <= 0:
            return 0.0
        frac = (x - r.left()) / r.width()
        return max(0.0, min(self.duration, frac * self.duration))

    def _x_from_t(self, t: float) -> float:
        r = self._bar_rect()
        if self.duration <= 0:
            return r.left()
        return r.left() + r.width() * max(0.0, min(1.0, t / self.duration))

    # ------------------------------------------------------------------
    def event(self, ev):
        t = ev.type()
        if t == QEvent.TouchBegin:
            pts = ev.points()
            if pts:
                self._dragging = True
                self._scrub(pts[0].position().x())
                ev.accept()
                return True
        elif t == QEvent.TouchUpdate:
            pts = ev.points()
            if self._dragging and pts:
                self._scrub(pts[0].position().x())
                ev.accept()
                return True
        elif t in (QEvent.TouchEnd, QEvent.TouchCancel):
            if self._dragging:
                pts = ev.points()
                x = pts[0].position().x() if pts else self._x_from_t(self.position)
                self._dragging = False
                self.position = self._t_from_x(x)
                self.seekRequested.emit(self.position)
                self.update()
                ev.accept()
                return True
        return super().event(ev)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            idx = self._marker_at(ev.position().x())
            if idx is not None and ev.modifiers() & Qt.ControlModifier:
                self.markerClicked.emit(idx)
                return
            self._dragging = True
            self._scrub(ev.position().x())

    def mouseMoveEvent(self, ev):
        self._hover_x = ev.position().x()
        if self._dragging:
            self._scrub(ev.position().x())
        else:
            self.update()
            if self.duration:
                QToolTip.showText(ev.globalPosition().toPoint(),
                                  fmt_time(self._t_from_x(ev.position().x())), self)

    def mouseReleaseEvent(self, ev):
        if self._dragging and ev.button() == Qt.LeftButton:
            self._dragging = False
            self.position = self._t_from_x(ev.position().x())
            self.seekRequested.emit(self.position)
            self.update()

    def leaveEvent(self, ev):
        self._hover_x = None
        self.update()

    def _scrub(self, x: float):
        self.position = self._t_from_x(x)
        self.scrubbing.emit(self.position)
        self.update()

    def _marker_at(self, x: float, tol: float = 7.0) -> Optional[int]:
        if not self.markers:
            return None
        for i, m in enumerate(self.markers):
            if abs(self._x_from_t(m.t) - x) <= tol:
                return i
        return None

    # ------------------------------------------------------------------
    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.fillRect(self.rect(), BG)
        r = self._bar_rect()

        p.setPen(Qt.NoPen)
        p.setBrush(TRACK)
        p.drawRoundedRect(r, 5, 5)

        # 片段底色
        if self.markers and self.duration > 0:
            p.setBrush(SEG)
            for seg in self.markers.segments(self.duration):
                x1 = self._x_from_t(seg.start)
                x2 = self._x_from_t(seg.end)
                p.drawRect(QRectF(x1, r.top() - 3, max(2.0, x2 - x1), r.height() + 6))

        # 已播放
        if self.duration > 0:
            pw = self._x_from_t(self.position) - r.left()
            if pw > 0:
                grad = QLinearGradient(r.left(), 0, r.right(), 0)
                grad.setColorAt(0.0, QColor(70, 140, 235))
                grad.setColorAt(1.0, PLAYED)
                p.setBrush(QBrush(grad))
                p.drawRoundedRect(QRectF(r.left(), r.top(), pw, r.height()), 5, 5)

        # 旗標
        if self.markers and self.duration > 0:
            roles = self.markers.roles()
            for i, (m, role) in enumerate(zip(self.markers, roles)):
                x = self._x_from_t(m.t)
                col = IN_C if role == ROLE_IN else OUT_C
                p.setPen(QPen(col, 2))
                p.drawLine(QPointF(x, r.top() - 10), QPointF(x, r.bottom() + 10))
                p.setPen(Qt.NoPen)
                p.setBrush(col)
                tri = QPolygonF([
                    QPointF(x, r.top() - 10),
                    QPointF(x + (9 if role == ROLE_IN else -9), r.top() - 16),
                    QPointF(x, r.top() - 22),
                ])
                p.drawPolygon(tri)

        # 滑鼠位置
        if self._hover_x is not None and not self._dragging:
            p.setPen(QPen(QColor(255, 255, 255, 80), 1))
            p.drawLine(QPointF(self._hover_x, r.top() - 8),
                       QPointF(self._hover_x, r.bottom() + 8))

        # 播放頭
        if self.duration > 0:
            x = self._x_from_t(self.position)
            p.setPen(Qt.NoPen)
            p.setBrush(CURSOR)
            p.drawEllipse(QPointF(x, r.center().y() + 0.5), 8, 8)
            p.setBrush(QColor(40, 110, 220))
            p.drawEllipse(QPointF(x, r.center().y() + 0.5), 4, 4)
        p.end()
