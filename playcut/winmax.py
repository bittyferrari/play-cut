"""Windows：從全螢幕直接回到「最大化」，中間不閃一下小視窗。

Qt 在 Windows 離開全螢幕時，會先把視窗 SetWindowPos 回「一般（未最大化）」的
大小，再最大化，所以會看到一瞬間的小視窗。
做法：進全螢幕前，先把視窗的「一般大小」暫時設成跟螢幕工作區一樣大，
這樣 Qt 還原的那一步看起來就跟最大化一模一樣；離開全螢幕後再把原本的
一般大小放回去（之後按「還原」按鈕仍會回到使用者原本的視窗大小）。
其他平台什麼都不做。
"""
from __future__ import annotations

import os
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
    _user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                     ctypes.c_int, ctypes.c_int, wintypes.UINT]
    _user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]

    _SWP_NOZORDER = 0x0004
    _SWP_NOACTIVATE = 0x0010
    _SWP_NOOWNERZORDER = 0x0200

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



# ----------------------------------------------------------------------
# 自己做的「無邊框全螢幕」（Windows）
#
# 用 Qt 的 showFullScreen() 時，OpenGL 視窗剛好蓋滿整個螢幕，Windows 會把它
# 升級成「獨佔全螢幕」（跳過 DWM 直接翻頁），之後偶爾在兩種模式間切換，就會
# 黑一下（約 0.5 秒）。只要視窗比螢幕大 1 像素就不會被升級，但 Qt 一看到
# 視窗大小跟螢幕不一樣，就會把狀態改回「一般視窗」，全螢幕切換會亂掉。
# 所以 Windows 上不用 Qt 的全螢幕：自己拿掉標題列 / 邊框、把視窗撐到
# 「螢幕 + 1 像素」，離開時再把樣式與位置放回去。是不是全螢幕由呼叫端自己記。
# 設環境變數 PLAYCUT_EXCLUSIVE_FS=1 可改回用 Qt 原本的 showFullScreen()。
# ----------------------------------------------------------------------
CUSTOM_FULLSCREEN = _ENABLED and not os.environ.get("PLAYCUT_EXCLUSIVE_FS")

if _ENABLED:
    _GWL_STYLE = -16
    _WS_POPUP = 0x80000000
    _WS_CAPTION = 0x00C00000
    _WS_THICKFRAME = 0x00040000
    _SW_SHOWNORMAL = 1
    _SW_SHOWMAXIMIZED = 3
    _SWP_FRAMECHANGED = 0x0020
    _SWP_NOMOVE = 0x0002
    _SWP_NOSIZE = 0x0001
    _HWND_TOP = wintypes.HWND(0)
    if ctypes.sizeof(ctypes.c_void_p) == 8:
        _GetStyle = _user32.GetWindowLongPtrW
        _SetStyle = _user32.SetWindowLongPtrW
        _GetStyle.restype = ctypes.c_ssize_t
        _GetStyle.argtypes = [wintypes.HWND, ctypes.c_int]
        _SetStyle.restype = ctypes.c_ssize_t
        _SetStyle.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    else:
        _GetStyle = _user32.GetWindowLongW
        _SetStyle = _user32.SetWindowLongW
        _GetStyle.restype = ctypes.c_long
        _GetStyle.argtypes = [wintypes.HWND, ctypes.c_int]
        _SetStyle.restype = ctypes.c_long
        _SetStyle.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]


def enter_borderless(widget):
    """進入無邊框全螢幕。成功回傳要留給 exit_borderless 的狀態，失敗回傳 None。"""
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
        style = int(_GetStyle(hwnd, _GWL_STYLE))
        full, work = mi.rcMonitor, mi.rcWork
        l, t, r, b = full.left, full.top, full.right, full.bottom + 1   # 多 1 像素

        _SetStyle(hwnd, _GWL_STYLE, (style & ~(_WS_CAPTION | _WS_THICKFRAME)) | _WS_POPUP)
        # 用 placement 直接從「最大化」換成「一般 + 螢幕大小」，中間不會閃小視窗
        wp = _get_placement(hwnd)
        dx, dy = work.left - full.left, work.top - full.top   # 工作區座標
        wp.showCmd = _SW_SHOWNORMAL
        wp.rcNormalPosition = wintypes.RECT(l - dx, t - dy, r - dx, b - dy)
        _user32.SetWindowPlacement(hwnd, ctypes.byref(wp))
        _user32.SetWindowPos(hwnd, _HWND_TOP, l, t, r - l, b - t,
                             _SWP_FRAMECHANGED | _SWP_NOOWNERZORDER)
        return (style, orig)
    except Exception:
        return None


def exit_borderless(widget, state):
    """離開無邊框全螢幕，回到「最大化」（還原按鈕仍會回到原本的一般大小）。"""
    if not _ENABLED or state is None:
        return
    style, orig = state
    try:
        hwnd = _hwnd(widget)
        _SetStyle(hwnd, _GWL_STYLE, style)
        orig.showCmd = _SW_SHOWMAXIMIZED
        _user32.SetWindowPlacement(hwnd, ctypes.byref(orig))
        _user32.SetWindowPos(hwnd, None, 0, 0, 0, 0,
                             _SWP_FRAMECHANGED | _SWP_NOMOVE | _SWP_NOSIZE
                             | _SWP_NOZORDER | _SWP_NOACTIVATE | _SWP_NOOWNERZORDER)
    except Exception:
        pass
