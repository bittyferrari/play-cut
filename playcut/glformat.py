"""OpenGL surface 設定。獨立成小模組，啟動時不必先載入 libmpv 就能設定。"""
from __future__ import annotations

import sys

from PySide6.QtGui import QSurfaceFormat


def configure_surface_format():
    """在建立 QApplication 之前呼叫。"""
    fmt = QSurfaceFormat()
    fmt.setDepthBufferSize(0)
    fmt.setStencilBufferSize(0)
    fmt.setSwapBehavior(QSurfaceFormat.DoubleBuffer)
    fmt.setRenderableType(QSurfaceFormat.OpenGL)
    if sys.platform == "darwin":
        # macOS 預設只給 OpenGL 2.1 legacy context；要 3.2 以上必須明確指定 Core Profile。
        fmt.setVersion(3, 2)
        fmt.setProfile(QSurfaceFormat.CoreProfile)
    QSurfaceFormat.setDefaultFormat(fmt)
