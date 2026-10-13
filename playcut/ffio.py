"""ffmpeg / ffprobe 的探測與共用工具。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .i18n import tr

# Windows 下不要彈出黑色的 console 視窗
if sys.platform == "win32":
    _CREATE_NO_WINDOW = 0x08000000
else:
    _CREATE_NO_WINDOW = 0


def _startupinfo():
    if sys.platform == "win32":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        return si
    return None


def run(cmd: list[str], timeout: Optional[float] = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=_CREATE_NO_WINDOW,
        startupinfo=_startupinfo(),
        timeout=timeout,
    )


def popen(cmd: list[str], **kw) -> subprocess.Popen:
    return subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        encoding="utf-8",
        errors="replace",
        creationflags=_CREATE_NO_WINDOW,
        startupinfo=_startupinfo(),
        **kw,
    )


# --------------------------------------------------------------------------
# 工具路徑
# --------------------------------------------------------------------------

def app_root() -> Path:
    """回傳資源根目錄（打包成 exe 時是 PyInstaller 的解壓目錄）。"""
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", None)
        if base:
            return Path(base)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def search_roots() -> list[Path]:
    roots = [app_root()]
    if getattr(sys, "frozen", False):
        roots.append(Path(sys.executable).resolve().parent)
    return roots


def _find_tool(name: str) -> str:
    exe = name + (".exe" if sys.platform == "win32" else "")
    for root in search_roots():
        for cand in (root / "bin" / exe, root / exe):
            if cand.exists():
                return str(cand)
    env = os.environ.get("PLAYCUT_" + name.upper())
    if env and Path(env).is_file():
        return env
    from shutil import which
    found = which(name)
    if found:
        return found
    if sys.platform == "darwin":
        # 從 Finder 啟動的 App 的 PATH 只有 /usr/bin:/bin，找不到 Homebrew
        for d in ("/opt/homebrew/bin", "/usr/local/bin", "/opt/local/bin"):
            cand = Path(d) / name
            if cand.exists():
                return str(cand)
    return name


class Tools:
    _ffmpeg: Optional[str] = None
    _ffprobe: Optional[str] = None

    @classmethod
    def ffmpeg(cls) -> str:
        if cls._ffmpeg is None:
            cls._ffmpeg = _find_tool("ffmpeg")
        return cls._ffmpeg

    @classmethod
    def ffprobe(cls) -> str:
        if cls._ffprobe is None:
            cls._ffprobe = _find_tool("ffprobe")
        return cls._ffprobe

    @classmethod
    def available(cls) -> bool:
        try:
            return run([cls.ffmpeg(), "-version"], timeout=15).returncode == 0
        except Exception:
            return False


# --------------------------------------------------------------------------
# 媒體資訊
# --------------------------------------------------------------------------

@dataclass
class MediaInfo:
    path: str
    duration: float = 0.0
    has_video: bool = False
    has_audio: bool = False
    v_codec: str = ""
    v_width: int = 0
    v_height: int = 0
    v_pix_fmt: str = "yuv420p"
    v_fps: float = 0.0
    v_sar: str = ""
    v_profile: str = ""
    a_codec: str = ""
    a_sample_rate: int = 48000
    a_channels: int = 2
    a_bitrate: int = 0
    a_layout: str = ""
    format_name: str = ""
    raw: dict = field(default_factory=dict)

    @property
    def frame_duration(self) -> float:
        return 1.0 / self.v_fps if self.v_fps > 0 else 0.0


def _frac(s: str) -> float:
    try:
        if "/" in s:
            a, b = s.split("/")
            b = float(b)
            return float(a) / b if b else 0.0
        return float(s)
    except Exception:
        return 0.0


def probe(path: str) -> MediaInfo:
    cmd = [
        Tools.ffprobe(), "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", path,
    ]
    cp = run(cmd, timeout=60)
    if cp.returncode != 0:
        raise RuntimeError(cp.stderr.decode("utf-8", "replace").strip() or tr("ffprobe 失敗"))
    data = json.loads(cp.stdout.decode("utf-8", "replace"))
    info = MediaInfo(path=path, raw=data)
    fmt = data.get("format", {})
    info.format_name = fmt.get("format_name", "")
    try:
        info.duration = float(fmt.get("duration", 0.0))
    except (TypeError, ValueError):
        info.duration = 0.0

    for st in data.get("streams", []):
        ctype = st.get("codec_type")
        if ctype == "video" and not info.has_video:
            if st.get("disposition", {}).get("attached_pic"):
                continue  # 封面圖，不是真的影片流
            info.has_video = True
            info.v_codec = st.get("codec_name", "")
            info.v_profile = st.get("profile", "") or ""
            info.v_width = int(st.get("width") or 0)
            info.v_height = int(st.get("height") or 0)
            info.v_pix_fmt = st.get("pix_fmt") or "yuv420p"
            fps = _frac(st.get("avg_frame_rate") or "0") or _frac(st.get("r_frame_rate") or "0")
            info.v_fps = fps
            info.v_sar = st.get("sample_aspect_ratio") or ""
            if not info.duration:
                try:
                    info.duration = float(st.get("duration") or 0.0)
                except (TypeError, ValueError):
                    pass
        elif ctype == "audio" and not info.has_audio:
            info.has_audio = True
            info.a_codec = st.get("codec_name", "")
            info.a_sample_rate = int(st.get("sample_rate") or 48000)
            info.a_channels = int(st.get("channels") or 2)
            info.a_layout = st.get("channel_layout") or ""
            try:
                info.a_bitrate = int(st.get("bit_rate") or 0)
            except (TypeError, ValueError):
                info.a_bitrate = 0
    return info


def list_keyframes(path: str, t0: float, t1: float) -> list[float]:
    """列出 [t0, t1] 區間內視訊流的關鍵影格時間（秒）。

    只讀取 packet header，不解碼，所以即使是長片也很快。
    """
    t0 = max(0.0, t0)
    if t1 <= t0:
        t1 = t0 + 1.0
    cmd = [
        Tools.ffprobe(), "-v", "error",
        "-select_streams", "v:0",
        "-read_intervals", f"{t0:.6f}%{t1:.6f}",
        "-show_entries", "packet=pts_time,dts_time,flags",
        "-of", "csv=p=0",
        path,
    ]
    cp = run(cmd, timeout=180)
    out = cp.stdout.decode("utf-8", "replace")
    kfs: list[float] = []
    for line in out.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 2:
            continue
        flags = parts[-1]
        if "K" not in flags:
            continue
        ts = None
        for p in parts[:-1]:
            if p and p != "N/A":
                try:
                    ts = float(p)
                    break
                except ValueError:
                    continue
        if ts is not None:
            kfs.append(ts)
    kfs.sort()
    return kfs


def next_keyframe_after(path: str, t: float, duration: float, eps: float = 1e-3) -> Optional[float]:
    """找出嚴格大於 t 的第一個關鍵影格；找不到回傳 None。"""
    window = 12.0
    start = max(0.0, t - 1.0)
    while start < duration:
        end = min(duration, start + window)
        for k in list_keyframes(path, start, end):
            if k > t + eps:
                return k
        if end >= duration:
            return None
        start = end
        window = min(window * 2, 120.0)
    return None


def keyframe_at_or_before(path: str, t: float, eps: float = 1e-3) -> Optional[float]:
    back = 12.0
    while back <= 600.0:
        lo = max(0.0, t - back)
        kfs = [k for k in list_keyframes(path, lo, t + 0.05) if k <= t + eps]
        if kfs:
            return kfs[-1]
        if lo <= 0.0:
            return None
        back *= 2
    return None


def fmt_time(seconds: float, ms: bool = True) -> str:
    if seconds is None:
        return "--:--:--"
    neg = seconds < 0
    seconds = abs(float(seconds))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    if ms:
        txt = f"{h:02d}:{m:02d}:{s:06.3f}"
    else:
        txt = f"{h:02d}:{m:02d}:{int(s):02d}"
    return ("-" if neg else "") + txt


def parse_time(text: str) -> Optional[float]:
    text = (text or "").strip()
    if not text:
        return None
    sign = 1.0
    if text.startswith("-"):
        sign, text = -1.0, text[1:]
    parts = text.split(":")
    try:
        vals = [float(p) for p in parts]
    except ValueError:
        return None
    total = 0.0
    for v in vals:
        total = total * 60 + v
    return sign * total
