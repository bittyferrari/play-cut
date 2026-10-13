"""Windows：從全螢幕直接回到「最大化」，中間不閃一下小視窗。

Qt 在 Windows 離開全螢幕時，會先把視窗 SetWindowPos 回「一般（未最大化）」的
大小，再最大化，所以會看到一瞬間的小視窗。
做法：進全螢幕前，先把視窗的「一般大小」暫時設成跟螢幕工作區一樣大，
這樣 Qt 還原的那一步看起來就跟最大化一模一樣；離開全螢幕後再把原本的
一般大小放回去（之後按「還原」按鈕仍會回到使用者原本的視窗大小）。
其他平台什麼都不做。
"""
from __future__ import annotations

import sys

_ENABLED = sys.platform == "win32"

if _ENABLED:
    import ctypes
    from ctypes import wintypes

    class _WINDOWPLACEMENT(ctypes.Structure):
        _fields_ = [("length", wintypes.UINT),
                    ("flags", wintypes.UINT),
                    ("showCmd", wintypes.UINT),
                    ("ptMinPosition", wintypes.POINT),
                    ("ptMaxPosition", wintypes.POINT),
                    ("rcNormalPosition", wintypes.RECT)]

    class _MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD),
                    ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT),
                    ("dwFlags", wintypes.DWORD)]

    _user32 = ctypes.windll.user32
    _user32.GetWindowPlacement.argtypes = [wintypes.HWND, ctypes.POINTER(_WINDOWPLACEMENT)]
    _user32.SetWindowPlacement.argtypes = [wintypes.HWND, ctypes.POINTER(_WINDOWPLACEMENT)]
    _user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    _user32.MonitorFromWindow.restype = wintypes.HMONITOR
    _user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(_MONITORINFO)]
    _user32.IsZoomed.argtypes = [wintypes.HWND]

    _MONITOR_DEFAULTTONEAREST = 2


def _hwnd(widget):
    return wintypes.HWND(int(widget.winId()))


def _get_placement(hwnd):
    wp = _WINDOWPLACEMENT()
    wp.length = ctypes.sizeof(_WINDOWPLACEMENT)
    if not _user32.GetWindowPlacement(hwnd, ctypes.byref(wp)):
        return None
    return wp


def prepare_fullscreen(widget):
    """進全螢幕「之前」呼叫。回傳原本的 placement（離開時交給 restore_after_fullscreen）。"""
    if not _ENABLED:
        return None
    try:
        hwnd = _hwnd(widget)
        orig = _get_placement(hwnd)
        if orig is None:
            return None
        mi = _MONITORINFO()
        mi.cbSize = ctypes.sizeof(_MONITORINFO)
        mon = _user32.MonitorFromWindow(hwnd, _MONITOR_DEFAULTTONEAREST)
        if not mon or not _user32.GetMonitorInfoW(mon, ctypes.byref(mi)):
            return None
        work, full = mi.rcWork, mi.rcMonitor
        # rcNormalPosition 用的是「工作區座標」：相對於工作區左上角
        dx, dy = work.left - full.left, work.top - full.top
        wp = _get_placement(hwnd)
        wp.rcNormalPosition = wintypes.RECT(work.left - dx, work.top - dy,
                                            work.right - dx, work.bottom - dy)
        if widget.isMaximized():
            _user32.SetWindowPlacement(hwnd, ctypes.byref(wp))
        else:
            # 本來不是最大化：先把視窗撐滿工作區，之後回來時同樣不會閃
            widget.setGeometry(widget.screen().availableGeometry())
        return orig
    except Exception:
        return None


def restore_after_fullscreen(widget, orig):
    """離開全螢幕、已經最大化之後呼叫：把原本的「一般大小」放回去。"""
    if not _ENABLED or orig is None:
        return
    try:
        hwnd = _hwnd(widget)
        if not _user32.IsZoomed(hwnd):
            return   # 萬一沒有真的最大化，就別動它，免得視窗縮小
        cur = _get_placement(hwnd)
        if cur is None:
            return
        cur.rcNormalPosition = orig.rcNormalPosition
        _user32.SetWindowPlacement(hwnd, ctypes.byref(cur))
    except Exception:
        pass
