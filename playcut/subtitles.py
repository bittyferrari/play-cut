"""字幕：檔案判斷、編碼偵測、SRT / VTT 解析與輸出、匯出時的字幕準備。

播放本身交給 mpv（它原生支援 srt / ass / ssa / vtt / sub / sup / idx…），
這裡處理的是「匯出片段」需要的部分：
  • 把目前字幕依片段切開、重新對時，另存成 .srt
  • 準備一份 UTF-8 的字幕檔給 ffmpeg 的 subtitles 濾鏡燒錄進畫面
"""
from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from .ffio import Tools, run
from .i18n import N_, tr

# mpv 能直接載入的外掛字幕副檔名
SUB_EXTS = (".srt", ".ass", ".ssa", ".vtt", ".webvtt", ".sub", ".idx",
            ".sup", ".smi", ".sami", ".lrc", ".mks")

SUB_FILTER = N_("字幕檔 (*.srt *.ass *.ssa *.vtt *.sub *.idx *.sup *.smi *.lrc *.mks)"
                 ";;所有檔案 (*.*)")

# 圖像型字幕：無法轉成文字，也不能用 subtitles 濾鏡燒錄
BITMAP_CODECS = {"hdmv_pgs_subtitle", "pgssub", "dvd_subtitle", "dvdsub",
                 "dvb_subtitle", "dvbsub", "xsub", "vobsub"}


def is_subtitle(path: str) -> bool:
    return str(path).lower().endswith(SUB_EXTS)


# --------------------------------------------------------------------------
# 目前字幕的描述（由播放器提供給匯出）
# --------------------------------------------------------------------------

@dataclass
class SubSource:
    """匯出時要用的字幕。

    external_path 有值 = 外掛字幕檔；否則用影片裡第 ff_index 條串流（絕對索引）。
    delay 與 mpv 的 sub-delay 同義：正值 = 字幕晚出現。
    """
    title: str = ""
    codec: str = ""
    external_path: str = ""
    ff_index: int = -1
    delay: float = 0.0

    @property
    def is_bitmap(self) -> bool:
        c = (self.codec or "").lower()
        if c in BITMAP_CODECS:
            return True
        return self.external_path.lower().endswith((".sup", ".idx", ".sub")) \
            and c not in ("subrip", "microdvd", "srt")

    @property
    def is_text(self) -> bool:
        return not self.is_bitmap

    @property
    def label(self) -> str:
        if self.external_path:
            return os.path.basename(self.external_path) + tr("（外掛）")
        return self.title or tr("內嵌字幕 #{n}", n=self.ff_index)


# --------------------------------------------------------------------------
# 編碼偵測
# --------------------------------------------------------------------------

# 台灣使用者優先猜 Big5（cp950），再試簡中 / 日文
_FALLBACK_ENCODINGS = ("cp950", "gb18030", "shift_jis", "cp1252")


def decode_bytes(data: bytes) -> str:
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8", "replace")
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", "replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    for enc in _FALLBACK_ENCODINGS:
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def read_text(path: str) -> str:
    with open(path, "rb") as fh:
        return decode_bytes(fh.read())


# --------------------------------------------------------------------------
# SRT / VTT
# --------------------------------------------------------------------------

@dataclass
class Cue:
    start: float
    end: float
    text: str


_TS = r"(?:(\d+):)?(\d{1,2}):(\d{1,2})(?:[.,](\d{1,3}))?"
_CUE_RE = re.compile(rf"^\s*{_TS}\s*-->\s*{_TS}")


def _ts(h, m, s, ms) -> float:
    frac = (ms or "0").ljust(3, "0")[:3]
    return int(h or 0) * 3600 + int(m) * 60 + int(s) + int(frac) / 1000.0


def parse_srt(text: str) -> list[Cue]:
    """同時吃 SRT 與 WebVTT（只取時間與文字，樣式標記保留原樣）。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("﻿")
    cues: list[Cue] = []
    lines = text.split("\n")
    i = 0
    n = len(lines)
    while i < n:
        m = _CUE_RE.match(lines[i])
        if not m:
            i += 1
            continue
        g = m.groups()
        start, end = _ts(*g[0:4]), _ts(*g[4:8])
        i += 1
        body: list[str] = []
        while i < n and lines[i].strip() != "":
            if _CUE_RE.match(lines[i]):
                break
            body.append(lines[i].rstrip())
            i += 1
        # SRT 的下一個序號行如果被吃進內文，拿掉
        if body and body[-1].strip().isdigit() and i < n and _CUE_RE.match(lines[i]):
            body.pop()
        if end > start:
            cues.append(Cue(start, end, "\n".join(body)))
    cues.sort(key=lambda c: (c.start, c.end))
    return cues


def _fmt_srt_time(t: float) -> str:
    t = max(0.0, t)
    total_ms = int(round(t * 1000))
    h, rem = divmod(total_ms, 3600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def format_srt(cues: Iterable[Cue]) -> str:
    out = []
    for i, c in enumerate(cues, 1):
        out.append(f"{i}\n{_fmt_srt_time(c.start)} --> {_fmt_srt_time(c.end)}\n{c.text}\n")
    return "\n".join(out)


def cut_cues(cues: list[Cue], start: float, end: float, delay: float = 0.0,
             offset: float = 0.0) -> list[Cue]:
    """取出片段 [start, end] 內的字幕，並重新對時。

    delay  = 播放器的字幕延遲（正值 = 字幕晚出現），會烘焙進輸出
    offset = 這個片段在輸出檔裡的起始時間（合併多段時用）
    """
    out: list[Cue] = []
    for c in cues:
        s, e = c.start + delay, c.end + delay
        if e <= start or s >= end:
            continue
        s, e = max(s, start), min(e, end)
        if e - s < 0.01:
            continue
        out.append(Cue(s - start + offset, e - start + offset, c.text))
    return out


# --------------------------------------------------------------------------
# 匯出前的準備：取得文字字幕 / 燒錄用檔案
# --------------------------------------------------------------------------

class SubtitleError(RuntimeError):
    pass


def _ffmpeg_convert(inputs: list[str], out_path: str) -> None:
    cmd = [Tools.ffmpeg(), "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
           *inputs, out_path]
    cp = run(cmd, timeout=300)
    if cp.returncode != 0 or not os.path.exists(out_path):
        msg = cp.stderr.decode("utf-8", "replace").strip()
        raise SubtitleError(tr("字幕轉換失敗：\n") + msg[-800:])


def _utf8_copy(src: str, dst: Path) -> Path:
    dst.write_text(read_text(src), encoding="utf-8")
    return dst


def load_cues(sub: SubSource, video: str, tmpdir: Path) -> list[Cue]:
    """把目前字幕變成 Cue 清單（圖像字幕會丟 SubtitleError）。"""
    if sub.is_bitmap:
        raise SubtitleError(tr("這是圖像字幕（PGS / VobSub），無法轉成 .srt。"))
    if sub.external_path:
        ext = Path(sub.external_path).suffix.lower()
        if ext in (".srt", ".vtt", ".webvtt"):
            return parse_srt(read_text(sub.external_path))
        tmp_in = _utf8_copy(sub.external_path, tmpdir / f"in_src{ext or '.txt'}")
        out = tmpdir / "converted.srt"
        _ffmpeg_convert(["-i", str(tmp_in), "-map", "0:s:0", "-c:s", "srt"], str(out))
        return parse_srt(read_text(str(out)))
    if sub.ff_index < 0:
        raise SubtitleError(tr("沒有可用的字幕軌。"))
    out = tmpdir / "embedded.srt"
    _ffmpeg_convert(["-i", video, "-map", f"0:{sub.ff_index}", "-c:s", "srt"], str(out))
    return parse_srt(read_text(str(out)))


def prepare_burn_file(sub: SubSource, video: str, tmpdir: Path) -> Path:
    """準備一份 UTF-8、路徑單純的字幕檔給 subtitles 濾鏡用。"""
    if sub.is_bitmap:
        raise SubtitleError(tr("圖像字幕（PGS / VobSub）目前不支援燒錄，請改用文字字幕。"))
    if sub.external_path:
        ext = Path(sub.external_path).suffix.lower()
        if ext in (".ass", ".ssa", ".srt"):
            return _utf8_copy(sub.external_path, tmpdir / f"burn{ext}")
        tmp_in = _utf8_copy(sub.external_path, tmpdir / f"burn_src{ext or '.txt'}")
        out = tmpdir / "burn.ass"
        _ffmpeg_convert(["-i", str(tmp_in), "-map", "0:s:0", "-c:s", "ass"], str(out))
        return out
    if sub.ff_index < 0:
        raise SubtitleError(tr("沒有可用的字幕軌。"))
    out = tmpdir / "burn.ass"
    codec = (sub.codec or "").lower()
    # 內嵌 ASS 直接複製（保留樣式），其他文字字幕轉成 ASS
    cs = "copy" if codec in ("ass", "ssa") else "ass"
    _ffmpeg_convert(["-i", video, "-map", f"0:{sub.ff_index}", "-c:s", cs], str(out))
    return out


def filter_escape_path(path: str) -> str:
    """把檔案路徑跳脫成可以放進 ffmpeg 濾鏡參數的樣子（Windows 的 C: 也沒問題）。"""
    p = str(path).replace("\\", "/")
    # 第一層：濾鏡選項值（: ' \ 要跳脫）
    p = re.sub(r"([\\:'])", r"\\\1", p)
    # 第二層：濾鏡圖（\ ' [ ] , ; 要跳脫）
    p = re.sub(r"([\\'\[\],;])", r"\\\1", p)
    return p


def burn_filter(sub_file: Path, seg_start: float, delay: float) -> str:
    """產生燒錄字幕用的 -vf 片段。

    輸入用 -ss 快速定位後，畫面時間戳會從 0 開始；字幕檔用的是原片時間，
    所以先把時間戳平移回原片時間（並扣掉字幕延遲）、疊字幕，再平移回來。
    """
    off = seg_start - delay
    return (f"setpts=PTS{off:+.6f}/TB,"
            f"subtitles=filename={filter_escape_path(str(sub_file))},"
            f"setpts=PTS{-off:+.6f}/TB")


def remove_tree(path: Optional[Path]):
    if path:
        shutil.rmtree(path, ignore_errors=True)
