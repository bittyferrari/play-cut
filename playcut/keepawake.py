"""播放中（或全螢幕）時，避免螢幕關閉 / 電腦進入睡眠。

Windows：SetThreadExecutionState（要在同一條執行緒（GUI 執行緒）開關）。
macOS  ：背景跑 `caffeinate -d -i -w <pid>`，程式結束時它也會自己結束。
其他平台：不做事。
"""
from __future__ import annotations

import os
import subprocess
import sys

_active = False
_proc = None

if sys.platform == "win32":
    import ctypes

    _ES_CONTINUOUS = 0x80000000
    _ES_SYSTEM_REQUIRED = 0x00000001
    _ES_DISPLAY_REQUIRED = 0x00000002
    _kernel32 = ctypes.windll.kernel32
    _kernel32.SetThreadExecutionState.argtypes = [ctypes.c_uint32]
    _kernel32.SetThreadExecutionState.restype = ctypes.c_uint32


def set_active(on: bool) -> None:
    global _active, _proc
    on = bool(on)
    if on == _active:
        return
    _active = on
    try:
        if sys.platform == "win32":
            flags = _ES_CONTINUOUS
            if on:
                flags |= _ES_DISPLAY_REQUIRED | _ES_SYSTEM_REQUIRED
            _kernel32.SetThreadExecutionState(flags)
        elif sys.platform == "darwin":
            if on:
                if _proc is None or _proc.poll() is not None:
                    _proc = subprocess.Popen(
                        ["caffeinate", "-d", "-i", "-w", str(os.getpid())],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif _proc is not None:
                _proc.terminate()
                _proc = None
    except Exception:
        pass   # 防休眠只是加分，失敗不影響播放
