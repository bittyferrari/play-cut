"""影片片段匯出引擎。

三種模式
--------
smart     智慧剪輯：起點所在的那一個 GOP 重新編碼，其餘串流複製後接起來。
          起點「完全精準」，速度接近無損剪輯。（預設）
reencode  全部重新編碼：100% 精準、相容性最好，但最慢、畫質會有損失。
lossless  純串流複製：最快，但起點會被拉到前一個關鍵影格（= LosslessCut 的偏移問題）。

壓縮（讓檔案變小）
------------------
可改用 H.264 / H.265 編碼、限制解析度（短邊上限，720 = 720p），
或指定「目標檔案大小」：依長度算出影片位元率，用 CPU 兩階段編碼（2-pass）逼近目標大小。
有任何一項會真的改變輸出時，一律整段重新編碼。

播放速度 / 短影音裁切
--------------------
speed != 1 或設定了 crop 時會強制「全部重新編碼」：
畫面用 setpts=PTS/speed、聲音用 atempo（音高不變）；
裁切依目標比例從畫面中取最大的區域（可置中 / 靠左上 / 靠右下），再縮放到指定解析度，
等同於 ffmpeg -vf "crop=ih*4/5:ih,scale=1080:1350"，但直式、橫式來源都適用。

聲音延遲
--------
播放器裡的 audio_delay D（秒，mpv 語意：正值 = 聲音延後）會被「烘焙」進輸出檔：
輸出的畫面取 [S, E]，聲音取 [S-D, E-D]，所以看起來跟你在播放器裡校正後聽到的一模一樣。
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import subprocess
import tempfile
import threading
import uuid
from dataclasses import dataclass, field, replace as dc_replace
from pathlib import Path
from typing import Callable, Optional

from .ffio import (
    MediaInfo,
    Tools,
    fmt_time,
    list_keyframes,
    next_keyframe_after,
    popen,
    probe,
    run,
)
from . import subtitles as SUB
from .i18n import N_, tr

EPS = 1e-3

MODE_SMART = "smart"
MODE_REENCODE = "reencode"
MODE_LOSSLESS = "lossless"

MODE_LABELS = {
    MODE_SMART: N_("智慧剪輯（起點精準 · 快）"),
    MODE_REENCODE: N_("全部重新編碼（最精準 · 慢）"),
    MODE_LOSSLESS: N_("純無損複製（最快 · 起點會偏移）"),
}

# 來源視訊編碼 -> 重新編碼時要用的編碼器（必須產生同樣格式才能跟複製的部分接起來）
VIDEO_ENCODER = {
    "h264": "libx264",
    "hevc": "libx265",
    "h265": "libx265",
    "mpeg4": "mpeg4",
    "mpeg2video": "mpeg2video",
    "vp8": "libvpx",
    "vp9": "libvpx-vp9",
    "av1": "libsvtav1",
    "prores": "prores_ks",
}

AUDIO_ENCODER = {
    "aac": "aac",
    "mp3": "libmp3lame",
    "ac3": "ac3",
    "eac3": "eac3",
    "opus": "libopus",
    "vorbis": "libvorbis",
    "flac": "flac",
    "pcm_s16le": "pcm_s16le",
}


# 顯卡編碼器：依來源格式，照順序嘗試（NVIDIA → Intel → AMD → Apple）
HW_ENCODERS = {
    "h264": ["h264_nvenc", "h264_qsv", "h264_amf", "h264_videotoolbox"],
    "hevc": ["hevc_nvenc", "hevc_qsv", "hevc_amf", "hevc_videotoolbox"],
    "h265": ["hevc_nvenc", "hevc_qsv", "hevc_amf", "hevc_videotoolbox"],
    "av1": ["av1_nvenc", "av1_qsv", "av1_amf"],
}

HW_LABELS = {
    "nvenc": "NVIDIA NVENC",
    "qsv": "Intel Quick Sync",
    "amf": "AMD AMF",
    "videotoolbox": "Apple VideoToolbox",
}


# 短影音裁切預設：key -> (比例寬, 比例高, 輸出寬, 輸出高, 顯示名稱)
CROP_PRESETS = {
    "1:1": (1, 1, 1080, 1080, N_("1:1 正方形（1080×1080）")),
    "4:5": (4, 5, 1080, 1350, N_("4:5 直式（1080×1350）")),
    "9:16": (9, 16, 1080, 1920, N_("9:16 直式全螢幕（1080×1920）")),
    "16:9": (16, 9, 1920, 1080, N_("16:9 橫式（1920×1080）")),
}

CROP_POSITIONS = {
    "center": (0.5, N_("置中")),
    "start": (0.0, N_("靠左 / 靠上")),
    "end": (1.0, N_("靠右 / 靠下")),
}


# 壓縮：輸出影片編碼（"" = 跟來源相同）
OUT_CODECS = {
    "": N_("跟來源相同"),
    "h264": N_("H.264（相容性最好）"),
    "hevc": N_("H.265 / HEVC（檔案更小、較慢）"),
}

# 壓縮：解析度上限（短邊像素，0 = 不限制）
RES_LIMITS = [0, 2160, 1440, 1080, 720, 480]

# 聲音位元率「自動」時，雙聲道最多用這麼多（kbps）
AUDIO_AUTO_MAX_KBPS = 160

# 依目標大小算位元率時，預留給容器的空間
_SIZE_MARGIN = 0.96


class ExportError(RuntimeError):
    pass


class Cancelled(RuntimeError):
    pass


@dataclass
class Segment:
    start: float
    end: float
    name: str = ""

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass
class ExportOptions:
    mode: str = MODE_SMART
    audio_delay: float = 0.0          # 秒，正值 = 聲音延後（與 mpv audio-delay 同義）
    apply_audio_delay: bool = True
    out_dir: str = ""
    container: str = ""               # "" = 跟來源一樣
    crf: int = 22                     # 重新編碼畫質（越小越好；22 一般人看不出差別，16 接近無損但檔案大很多）
    preset: str = "medium"
    hw_accel: bool = True             # 整段重新編碼時優先用顯卡（失敗自動退回 CPU）
    audio_bitrate: int = 0            # kbps，0 = 自動（跟來源，雙聲道最多 160k）
    merge: bool = False               # 把所有片段接成一個檔
    overwrite: bool = True
    subtitle: Optional[SUB.SubSource] = None   # 目前播放器選的字幕（None = 沒有）
    burn_subtitles: bool = False      # 把字幕燒進畫面（會整段重新編碼）
    export_srt: bool = False          # 每個輸出檔旁邊另存對應的 .srt
    burn_file: str = ""               # 內部用：準備好的燒錄字幕檔
    sub_shift: float = 0.0            # 內部用：內嵌字幕要扣掉的容器起始時間
    speed: float = 1.0                # 播放速度（2.0 = 兩倍速），!= 1 時整段重新編碼
    crop: str = ""                    # "" = 不裁切；否則為 CROP_PRESETS 的 key
    crop_pos: str = "center"          # CROP_POSITIONS 的 key
    crop_scale: bool = True           # 裁切後縮放到預設解析度（例如 1080×1350）
    v_codec: str = ""                 # 壓縮：輸出影片編碼，"" = 跟來源相同；"h264" / "hevc"
    max_short_side: int = 0           # 壓縮：短邊上限（720 = 720p），0 = 不縮
    target_mb: float = 0.0            # 壓縮：每個輸出檔的目標大小（MB），0 = 用 CRF
    video_kbps: int = 0               # 內部用：依目標大小算出的影片位元率


ProgressCb = Callable[[float, str], None]   # (0..1, 訊息)


def eff_speed(opts: ExportOptions) -> float:
    try:
        sp = float(opts.speed or 1.0)
    except (TypeError, ValueError):
        sp = 1.0
    sp = max(0.1, min(10.0, sp))
    return 1.0 if abs(sp - 1.0) < 1e-6 else sp


def norm_codec(codec: str) -> str:
    return "hevc" if codec in ("hevc", "h265") else (codec or "")


def compress_active(opts: ExportOptions, info: Optional[MediaInfo] = None) -> bool:
    """壓縮設定是否真的會改變輸出（不知道來源資訊時，有設定就當作會）。"""
    if opts.target_mb and opts.target_mb > 0:
        return True
    if opts.v_codec and (info is None or norm_codec(info.v_codec) != opts.v_codec):
        return True
    if opts.max_short_side and opts.max_short_side > 0:
        if info is None:
            return True
        short = min(info.v_width, info.v_height)
        if short <= 0 or short > opts.max_short_side:
            return True
    return False


def needs_reencode(opts: ExportOptions, info: Optional[MediaInfo] = None) -> bool:
    """速度、裁切、燒錄字幕、壓縮都要改動每一格畫面，只能整段重新編碼。"""
    return bool(opts.burn_file or opts.crop in CROP_PRESETS
                or eff_speed(opts) != 1.0 or compress_active(opts, info))


def limit_filters(opts: ExportOptions) -> list[str]:
    """解析度上限：短邊縮到 max_short_side（只縮不放大，另一邊等比例、取偶數）。"""
    n = int(opts.max_short_side or 0)
    if n <= 0:
        return []
    w = f"if(gte(iw\\,ih)\\,-2\\,min(iw\\,{n}))"
    h = f"if(gte(iw\\,ih)\\,min(ih\\,{n})\\,-2)"
    return [f"scale=w={w}:h={h}:flags=lanczos"]


def target_video_kbps(target_mb: float, out_dur: float, audio_kbps: int) -> int:
    """目標檔案大小（MB，1 MB = 1024×1024 bytes）→ 影片位元率 kbps。"""
    if target_mb <= 0 or out_dur <= 0:
        return 0
    total_kbps = target_mb * 1024 * 1024 * 8 / 1000 * _SIZE_MARGIN / out_dur
    return max(50, int(total_kbps - max(0, audio_kbps)))


def encode_info(info: MediaInfo, opts: ExportOptions) -> MediaInfo:
    """整段重新編碼時實際要用的「目標格式」：改編碼器與像素格式，其餘照來源。"""
    if not opts.v_codec or not info.has_video:
        return info
    pf = (info.v_pix_fmt or "yuv420p").lower()
    ten_bit = "10" in pf
    if opts.v_codec == "h264":
        pf = "yuv420p"                       # 10-bit / 4:2:2 的 H.264 很多裝置播不了
    else:
        pf = "yuv420p10le" if ten_bit else "yuv420p"
    return dc_replace(info, v_codec=opts.v_codec, v_pix_fmt=pf)


def atempo_chain(speed: float) -> list[str]:
    """atempo 單一濾鏡只保證 0.5~2.0，超出範圍就串接多個。"""
    parts: list[str] = []
    s = speed
    while s > 2.0 + 1e-9:
        parts.append("atempo=2.0")
        s /= 2.0
    while s < 0.5 - 1e-9:
        parts.append("atempo=0.5")
        s /= 0.5
    if abs(s - 1.0) > 1e-6:
        parts.append(f"atempo={s:.6f}")
    return parts


def crop_filters(opts: ExportOptions) -> list[str]:
    """短影音裁切：取目標比例內最大的區域，再（選擇性）縮放到預設解析度。"""
    preset = CROP_PRESETS.get(opts.crop)
    if not preset:
        return []
    a, b, W, H, _ = preset
    p = CROP_POSITIONS.get(opts.crop_pos, CROP_POSITIONS["center"])[0]
    w = f"trunc(min(iw\\,ih*{a}/{b})/2)*2"
    h = f"trunc(min(ih\\,iw*{b}/{a})/2)*2"
    out = [f"crop={w}:{h}:(iw-ow)*{p:g}:(ih-oh)*{p:g}"]
    if opts.crop_scale:
        out.append(f"scale={W}:{H}:flags=lanczos")
    return out


def output_tag(opts: ExportOptions) -> str:
    """輸出檔名後綴，例如 _2x_4x5。"""
    tag = ""
    sp = eff_speed(opts)
    if sp != 1.0:
        tag += f"_{sp:g}x"
    if opts.crop in CROP_PRESETS:
        tag += "_" + opts.crop.replace(":", "x")
    return tag


# --------------------------------------------------------------------------
# 小工具
# --------------------------------------------------------------------------

def _safe_name(text: str) -> str:
    text = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", text).strip(" .")
    return text or "segment"


def audio_kbps(info: MediaInfo, opts: ExportOptions) -> int:
    if opts.audio_bitrate:
        return int(opts.audio_bitrate)
    if info.a_bitrate:
        k = max(96, min(512, round(info.a_bitrate / 1000)))
    else:
        k = 192
    if info.a_channels <= 2:
        k = min(k, AUDIO_AUTO_MAX_KBPS)
    return k


def _audio_bitrate(info: MediaInfo, opts: ExportOptions) -> str:
    return f"{audio_kbps(info, opts)}k"


def _video_encoder(info: MediaInfo) -> str:
    enc = VIDEO_ENCODER.get(info.v_codec)
    if not enc:
        return "libx264"
    if enc == "libsvtav1" and not _encoder_exists("libsvtav1"):
        return "libaom-av1" if _encoder_exists("libaom-av1") else "libx264"
    if not _encoder_exists(enc):
        return "libx264"
    return enc


def _audio_encoder(info: MediaInfo, opts: Optional[ExportOptions] = None) -> str:
    enc = AUDIO_ENCODER.get(info.a_codec, "aac")
    if opts is not None and opts.target_mb > 0 and enc in ("flac", "pcm_s16le"):
        enc = "aac"                    # 指定大小時無損音訊會吃掉太多空間
    return enc if _encoder_exists(enc) else "aac"


_ENC_CACHE: dict[str, bool] = {}


def _encoder_exists(name: str) -> bool:
    if name in _ENC_CACHE:
        return _ENC_CACHE[name]
    try:
        cp = run([Tools.ffmpeg(), "-hide_banner", "-encoders"], timeout=30)
        text = cp.stdout.decode("utf-8", "replace")
        _ENC_CACHE.clear()
        for line in text.splitlines():
            m = re.match(r"^\s*[A-Z.]{6}\s+(\S+)", line)
            if m:
                _ENC_CACHE[m.group(1)] = True
    except Exception:
        return True
    return _ENC_CACHE.get(name, False)


# ---- 顯卡編碼 ----------------------------------------------------------------

_NV_PRESET = {"ultrafast": "p1", "veryfast": "p2", "faster": "p3", "fast": "p4",
              "medium": "p5", "slow": "p6", "slower": "p7"}
_QSV_PRESET = {"ultrafast": "veryfast", "veryfast": "veryfast", "faster": "faster",
               "fast": "fast", "medium": "medium", "slow": "slow", "slower": "slower"}
_AMF_QUALITY = {"ultrafast": "speed", "veryfast": "speed", "faster": "speed",
                "fast": "balanced", "medium": "balanced", "slow": "quality",
                "slower": "quality"}

_HW_OK: dict[tuple[str, str], bool] = {}
_HW_LOCK = threading.Lock()


def hw_family(encoder: str) -> str:
    """h264_nvenc -> nvenc；CPU 編碼器回傳空字串。"""
    for fam in HW_LABELS:
        if encoder.endswith("_" + fam):
            return fam
    return ""


def hw_label(encoder: str) -> str:
    fam = hw_family(encoder)
    return HW_LABELS.get(fam, "CPU")


def _hw_pix_fmt(encoder: str, src_pix_fmt: str) -> Optional[str]:
    """顯卡編碼器要用的像素格式；None = 這種來源格式顯卡處理不了（改用 CPU）。"""
    pf = (src_pix_fmt or "yuv420p").lower()
    ten_bit = pf in ("yuv420p10le", "yuv420p10be", "p010le", "p010be")
    eight_bit = pf in ("yuv420p", "yuvj420p", "nv12")
    if not (ten_bit or eight_bit):
        return None                   # 4:2:2 / 4:4:4 / 12-bit… 交給 CPU
    fam = hw_family(encoder)
    if ten_bit:
        if encoder.startswith("h264_"):
            return None               # 大部分顯卡不支援 10-bit H.264
        return "p010le"
    return "nv12" if fam == "qsv" else "yuv420p"


def _hw_works(encoder: str, pix_fmt: str) -> bool:
    """實際用這個編碼器編幾格測試畫面，確定驅動與顯卡都能用。結果會快取。"""
    key = (encoder, pix_fmt)
    with _HW_LOCK:
        if key in _HW_OK:
            return _HW_OK[key]
        ok = False
        if _encoder_exists(encoder):
            cmd = [Tools.ffmpeg(), "-hide_banner", "-nostdin", "-loglevel", "error",
                   "-f", "lavfi", "-i", "color=c=black:s=320x240:r=30:d=0.2",
                   "-frames:v", "3", "-c:v", encoder, "-pix_fmt", pix_fmt,
                   "-f", "null", "-"]
            try:
                ok = run(cmd, timeout=20).returncode == 0
            except Exception:
                ok = False
        _HW_OK[key] = ok
        return ok


def pick_hw_encoder(info: MediaInfo) -> Optional[str]:
    """找一個這台電腦能用、而且跟來源同格式的顯卡編碼器；找不到回傳 None。"""
    for enc in HW_ENCODERS.get(info.v_codec, []):
        if enc.endswith("_videotoolbox") and sys.platform != "darwin":
            continue
        if not enc.endswith("_videotoolbox") and sys.platform == "darwin":
            continue
        pf = _hw_pix_fmt(enc, info.v_pix_fmt)
        if pf and _hw_works(enc, pf):
            return enc
    return None


def _hw_quality_args(encoder: str, info: MediaInfo, crf: int, preset: str) -> list[str]:
    fam = hw_family(encoder)
    args = ["-c:v", encoder]
    if fam == "nvenc":
        args += ["-preset", _NV_PRESET.get(preset, "p5"), "-tune", "hq",
                 "-rc", "vbr", "-cq", str(max(1, crf)), "-b:v", "0",
                 "-spatial-aq", "1"]
    elif fam == "qsv":
        args += ["-preset", _QSV_PRESET.get(preset, "medium"),
                 "-global_quality", str(max(1, crf))]
    elif fam == "amf":
        args += ["-quality", _AMF_QUALITY.get(preset, "balanced"), "-rc", "cqp",
                 "-qp_i", str(crf), "-qp_p", str(crf)]
        if encoder == "h264_amf":
            args += ["-qp_b", str(crf)]
    elif fam == "videotoolbox":
        # q:v 1..100，越大越好；CRF 16 約對應 68
        args += ["-q:v", str(max(1, min(100, 100 - crf * 2)))]
    pf = _hw_pix_fmt(encoder, info.v_pix_fmt)
    if pf:
        args += ["-pix_fmt", pf]
    return args


def _video_quality_args(encoder: str, info: MediaInfo, crf: int, preset: str,
                        kbps: int = 0, vpass: Optional[tuple[int, str]] = None) -> list[str]:
    if hw_family(encoder):
        return _hw_quality_args(encoder, info, crf, preset)
    args = ["-c:v", encoder]
    if kbps > 0 and encoder in ("libx264", "libx265"):
        # 指定位元率（目標檔案大小）；vpass = (第幾階段, 記錄檔名稱，相對於工作目錄)
        args += ["-b:v", f"{kbps}k", "-preset", preset]
        if encoder == "libx265":
            x265 = "log-level=error"
            if vpass:
                x265 += f":pass={vpass[0]}:stats={vpass[1]}.log"
            args += ["-x265-params", x265]
        elif vpass:
            args += ["-pass", str(vpass[0]), "-passlogfile", vpass[1]]
    elif kbps > 0 and encoder != "prores_ks":
        args += ["-b:v", f"{kbps}k"]
    elif encoder in ("libx264", "libx265"):
        args += ["-crf", str(crf), "-preset", preset]
        if encoder == "libx265":
            args += ["-x265-params", "log-level=error"]
    elif encoder in ("libvpx-vp9", "libvpx"):
        args += ["-crf", str(crf + 12), "-b:v", "0"]
    elif encoder in ("libsvtav1", "libaom-av1"):
        args += ["-crf", str(crf + 10)]
    elif encoder == "prores_ks":
        args += ["-profile:v", "3"]
    else:
        args += ["-q:v", "2"]
    if info.v_pix_fmt:
        args += ["-pix_fmt", info.v_pix_fmt]
    return args


def _container_for(info: MediaInfo, opts: ExportOptions, src: Path) -> str:
    if opts.container:
        return opts.container.lstrip(".")
    ext = src.suffix.lstrip(".").lower()
    if ext == "webm" and opts.v_codec in ("h264", "hevc"):
        return "mkv"                   # webm 只能放 VP8 / VP9 / AV1
    return ext or "mkv"


# --------------------------------------------------------------------------
# ffmpeg 指令組裝
# --------------------------------------------------------------------------

def _inputs_with_delay(src: str, v_start: float, delay: float, has_audio: bool,
                       accurate: bool) -> tuple[list[str], list[str], float]:
    """組出輸入參數。

    回傳 (輸入參數, map 參數, 需要在前面補的靜音秒數)

    畫面取 v_start 起，聲音取 (v_start - delay) 起。
    若 v_start - delay < 0，回傳需要補的靜音長度，交給呼叫端用 adelay 處理。
    """
    args: list[str] = []
    maps: list[str] = []
    pad = 0.0

    seek_flag = ["-ss", f"{max(0.0, v_start):.6f}"]
    args += seek_flag + ["-i", src]
    maps += ["-map", "0:v:0"]

    if not has_audio:
        return args, maps, 0.0

    a_start = v_start - delay
    if abs(delay) < 1e-6:
        # 沒有延遲：直接用同一個輸入的音訊，省掉一次解碼
        maps += ["-map", "0:a:0"]
        return args, maps, 0.0

    if a_start < 0:
        pad = -a_start
        a_start = 0.0
    args += ["-ss", f"{a_start:.6f}", "-i", src]
    maps += ["-map", "1:a:0"]
    return args, maps, pad


def _build_part_cmd(src: str, info: MediaInfo, start: float, duration: float,
                    out_path: str, opts: ExportOptions, *,
                    copy_video: bool, delay: float,
                    encoder: Optional[str] = None,
                    vpass: Optional[tuple[int, str]] = None) -> list[str]:
    """vpass = (1 或 2, 記錄檔名稱)：兩階段編碼。第 1 階段只分析畫面，不輸出檔案也不處理聲音。"""
    ff = Tools.ffmpeg()
    cmd = [ff, "-hide_banner", "-nostdin", "-loglevel", "error", "-y"]
    first_pass = bool(vpass and vpass[0] == 1)
    has_audio = info.has_audio and not first_pass

    in_args, maps, pad = _inputs_with_delay(src, start, delay, has_audio, accurate=not copy_video)
    cmd += in_args
    cmd += maps

    speed = 1.0 if copy_video else eff_speed(opts)
    if copy_video:
        cmd += ["-c:v", "copy"]
    else:
        enc = encoder or _video_encoder(info)
        cmd += _video_quality_args(enc, info, opts.crf, opts.preset,
                                   kbps=opts.video_kbps, vpass=vpass)
        if ((enc == "libx265" or enc.startswith("hevc_"))
                and Path(out_path).suffix.lower() in (".mp4", ".mov", ".m4v")):
            cmd += ["-tag:v", "hvc1"]          # 讓 Apple 裝置 / QuickTime 也能播 HEVC
        vf: list[str] = []
        cropping = bool(crop_filters(opts)) and info.has_video
        if cropping:
            # 先裁切再燒字幕：字幕會依裁切後的畫面排版，不會被切掉
            vf += crop_filters(opts)
        if info.has_video:
            # 解析度上限放在燒字幕之前，字幕才會依縮小後的畫面排版
            vf += limit_filters(opts)
        if opts.burn_file:
            sub_delay = opts.subtitle.delay if opts.subtitle else 0.0
            vf.append(SUB.burn_filter(Path(opts.burn_file), start,
                                      sub_delay - opts.sub_shift))
        if cropping:
            vf.append("setsar=1")
        elif info.v_sar and info.v_sar not in ("0:1", "N/A"):
            vf.append(f"setsar={info.v_sar.replace(':', '/')}")
        if speed != 1.0:
            vf.append(f"setpts=PTS/{speed:.6f}")
        if vf:
            cmd += ["-vf", ",".join(vf)]

    if has_audio:
        cmd += ["-c:a", _audio_encoder(info, opts), "-b:a", _audio_bitrate(info, opts)]
        cmd += ["-ar", str(info.a_sample_rate), "-ac", str(info.a_channels)]
        af: list[str] = []
        if pad > 0:
            af.append(f"adelay={int(round(pad * 1000))}:all=1")
        if speed != 1.0:
            af += atempo_chain(speed)
        if af:
            cmd += ["-af", ",".join(af)]
    else:
        cmd += ["-an"]

    # 輸出長度 = 原片段長度 / 速度
    cmd += ["-t", f"{duration / speed:.6f}"]
    cmd += ["-map_metadata", "-1", "-map_chapters", "-1"]
    cmd += ["-avoid_negative_ts", "make_zero", "-video_track_timescale", "90000"]
    if first_pass:
        cmd += ["-f", "null", "-"]
    else:
        cmd += [out_path]
    return cmd


def _build_lossless_cmd(src: str, info: MediaInfo, start: float, duration: float,
                        out_path: str, opts: ExportOptions, delay: float) -> list[str]:
    ff = Tools.ffmpeg()
    cmd = [ff, "-hide_banner", "-nostdin", "-loglevel", "error", "-y"]
    in_args, maps, pad = _inputs_with_delay(src, start, delay, info.has_audio, accurate=False)
    cmd += in_args + maps
    if pad > 0 and info.has_audio:
        # 需要補靜音就沒辦法純複製音訊
        cmd += ["-c:v", "copy", "-c:a", _audio_encoder(info),
                "-b:a", _audio_bitrate(info, opts),
                "-af", f"adelay={int(round(pad * 1000))}:all=1"]
    else:
        cmd += ["-c", "copy"]
    cmd += ["-t", f"{duration:.6f}", "-avoid_negative_ts", "make_zero", out_path]
    return cmd


def _build_reencode_cmd(src: str, info: MediaInfo, start: float, duration: float,
                        out_path: str, opts: ExportOptions, delay: float,
                        encoder: Optional[str] = None,
                        vpass: Optional[tuple[int, str]] = None) -> list[str]:
    return _build_part_cmd(src, info, start, duration, out_path, opts,
                           copy_video=False, delay=delay, encoder=encoder, vpass=vpass)


def _run_full_reencode(src: str, info: MediaInfo, start: float, dur: float,
                       out_path: str, opts: ExportOptions, delay: float,
                       runner: "Runner", prog, lo: float, hi: float,
                       allow_hw: bool) -> None:
    """整段重新編碼；允許時先用顯卡，失敗就自動改用 CPU 重來。

    指定目標檔案大小時改用 CPU 兩階段編碼（顯卡沒辦法準確控制大小）。
    """
    out_dur = dur / eff_speed(opts)          # ffmpeg 進度回報的是輸出時間
    enc = _video_encoder(info) if info.has_video else ""
    if opts.video_kbps > 0 and enc in ("libx264", "libx265"):
        _run_two_pass(src, info, start, dur, out_path, opts, delay, runner,
                      prog, lo, hi, enc, out_dur)
        return
    if opts.video_kbps > 0:
        allow_hw = False
    hw = pick_hw_encoder(info) if (allow_hw and opts.hw_accel and info.has_video) else None
    if hw:
        msg = tr("重新編碼中（顯卡 {name}）…", name=hw_label(hw))
        prog(lo, msg)
        cmd = _build_reencode_cmd(src, info, start, dur, out_path, opts, delay, encoder=hw)
        try:
            runner.exec(cmd, out_dur, lambda f: prog(lo + f * (hi - lo), msg))
            return
        except ExportError:
            prog(lo, tr("顯卡編碼失敗，改用 CPU 重新編碼…"))
    msg = tr("重新編碼中（CPU）…") if info.has_video else tr("重新編碼中…")
    prog(lo, msg)
    cmd = _build_reencode_cmd(src, info, start, dur, out_path, opts, delay)
    runner.exec(cmd, out_dur, lambda f: prog(lo + f * (hi - lo), msg))


def _run_two_pass(src: str, info: MediaInfo, start: float, dur: float,
                  out_path: str, opts: ExportOptions, delay: float,
                  runner: "Runner", prog, lo: float, hi: float,
                  encoder: str, out_dur: float) -> None:
    # x265 的 stats 路徑放在 x265-params 裡，Windows 的 "C:" 會被當成參數分隔字元，
    # 所以在暫存資料夾裡執行 ffmpeg、記錄檔用相對路徑；輸入輸出改成絕對路徑。
    tmpdir = Path(tempfile.mkdtemp(prefix="playcut_2pass_"))
    src_abs = os.path.abspath(src)
    out_abs = os.path.abspath(out_path)
    mid = lo + (hi - lo) * 0.45
    try:
        msg1 = tr("兩階段編碼：第 1 階段（分析畫面）…")
        prog(lo, msg1)
        cmd1 = _build_reencode_cmd(src_abs, info, start, dur, out_abs, opts, delay,
                                   encoder=encoder, vpass=(1, "ffpass"))
        runner.exec(cmd1, out_dur, lambda f: prog(lo + f * (mid - lo), msg1), cwd=str(tmpdir))
        msg2 = tr("兩階段編碼：第 2 階段（輸出，約 {k} kbps）…", k=opts.video_kbps)
        prog(mid, msg2)
        cmd2 = _build_reencode_cmd(src_abs, info, start, dur, out_abs, opts, delay,
                                   encoder=encoder, vpass=(2, "ffpass"))
        runner.exec(cmd2, out_dur, lambda f: prog(mid + f * (hi - mid), msg2), cwd=str(tmpdir))
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# --------------------------------------------------------------------------
# 執行 + 進度
# --------------------------------------------------------------------------

_TIME_RE = re.compile(r"time=(\d+):(\d+):(\d+\.?\d*)")


class Runner:
    def __init__(self, cancel_event: Optional[threading.Event] = None):
        self.cancel = cancel_event or threading.Event()
        self._proc: Optional[subprocess.Popen] = None

    def abort(self):
        self.cancel.set()
        p = self._proc
        if p and p.poll() is None:
            try:
                p.kill()
            except Exception:
                pass

    def exec(self, cmd: list[str], total: float = 0.0,
             on_progress: Optional[Callable[[float], None]] = None,
             cwd: Optional[str] = None) -> None:
        if self.cancel.is_set():
            raise Cancelled()
        cmd = list(cmd)
        if "-loglevel" in cmd:
            i = cmd.index("-loglevel")
            cmd[i + 1] = "error"
        cmd = cmd[:1] + ["-stats"] + cmd[1:]
        self._proc = popen(cmd, cwd=cwd) if cwd else popen(cmd)
        tail: list[str] = []
        assert self._proc.stdout is not None
        buf = ""
        while True:
            ch = self._proc.stdout.read(1)
            if not ch:
                break
            if ch in "\r\n":
                if buf.strip():
                    tail.append(buf.strip())
                    del tail[:-40]
                    m = _TIME_RE.search(buf)
                    if m and total > 0 and on_progress:
                        h, mnt, s = m.groups()
                        cur = int(h) * 3600 + int(mnt) * 60 + float(s)
                        on_progress(max(0.0, min(1.0, cur / total)))
                buf = ""
            else:
                buf += ch
            if self.cancel.is_set():
                try:
                    self._proc.kill()
                except Exception:
                    pass
                raise Cancelled()
        rc = self._proc.wait()
        self._proc = None
        if self.cancel.is_set():
            raise Cancelled()
        if rc != 0:
            raise ExportError(tr("ffmpeg 失敗：\n") + "\n".join(tail[-12:]))


# --------------------------------------------------------------------------
# 主要匯出流程
# --------------------------------------------------------------------------

def plan_smart_cut(src: str, info: MediaInfo, start: float, end: float) -> tuple[float, str]:
    """決定智慧剪輯的切點。

    回傳 (join_time, 說明)。join_time == start 代表整段都可以直接複製，
    join_time >= end 代表整段都要重新編碼。
    """
    kfs = list_keyframes(src, max(0.0, start - 0.05), start + 0.05)
    if any(abs(k - start) <= EPS for k in kfs):
        return start, tr("起點剛好落在關鍵影格，整段串流複製")
    nxt = next_keyframe_after(src, start, info.duration or end + 1.0)
    if nxt is None or nxt >= end - EPS:
        return end, tr("起點到終點之間沒有關鍵影格，整段重新編碼")
    return nxt, tr("重新編碼 {a:.3f}s–{b:.3f}s（{d:.3f}s），其餘串流複製",
                   a=start, b=nxt, d=nxt - start)


def export_segment(src: str, info: MediaInfo, seg: Segment, out_path: str,
                   opts: ExportOptions, runner: Runner,
                   on_progress: Optional[ProgressCb] = None) -> str:
    delay = opts.audio_delay if opts.apply_audio_delay else 0.0
    start, end = float(seg.start), float(seg.end)
    if end <= start:
        raise ExportError(tr("片段長度必須大於 0"))
    dur = end - start

    def prog(frac: float, msg: str = ""):
        if on_progress:
            on_progress(max(0.0, min(1.0, frac)), msg)

    mode = opts.mode
    if needs_reencode(opts, info):
        # 燒錄字幕 / 改速度 / 裁切 / 壓縮：每一格都得重新編碼
        mode = MODE_REENCODE
    if opts.target_mb > 0 and opts.video_kbps <= 0 and info.has_video:
        kb = target_video_kbps(opts.target_mb, dur / eff_speed(opts),
                               audio_kbps(info, opts) if info.has_audio else 0)
        opts = ExportOptions(**{**opts.__dict__, "video_kbps": kb})
    if mode == MODE_LOSSLESS:
        prog(0.02, tr("串流複製中…"))
        cmd = _build_lossless_cmd(src, info, start, dur, out_path, opts, delay)
        runner.exec(cmd, dur, lambda f: prog(0.02 + f * 0.96, tr("串流複製中…")))
        prog(1.0, tr("完成"))
        return out_path

    if mode == MODE_REENCODE or not info.has_video:
        # 整個輸出檔都由同一個編碼器產生，可以放心用顯卡
        _run_full_reencode(src, encode_info(info, opts), start, dur, out_path, opts, delay, runner,
                           prog, 0.02, 0.98, allow_hw=True)
        prog(1.0, tr("完成"))
        return out_path

    # ---- 智慧剪輯 ----
    prog(0.01, tr("掃描關鍵影格…"))
    try:
        join, note = plan_smart_cut(src, info, start, end)
    except Exception as exc:  # 掃描失敗就退回全重編碼
        join, note = end, tr("關鍵影格掃描失敗（{err}），改為整段重新編碼", err=exc)

    if join <= start + EPS:
        # 起點正好是關鍵影格 -> 直接複製
        prog(0.05, note)
        cmd = _build_lossless_cmd(src, info, start, dur, out_path, opts, delay)
        runner.exec(cmd, dur, lambda f: prog(0.05 + f * 0.93, tr("串流複製中…")))
        prog(1.0, tr("完成"))
        return out_path

    if join >= end - EPS:
        # 智慧剪輯一律用 CPU：合併匯出時這段會跟串流複製的片段接在一起，
        # 編碼參數必須跟來源一致才不會在接縫出問題
        prog(0.05, note)
        cmd = _build_reencode_cmd(src, info, start, dur, out_path, opts, delay)
        runner.exec(cmd, dur, lambda f: prog(0.05 + f * 0.93, tr("重新編碼中…")))
        prog(1.0, tr("完成"))
        return out_path

    head_dur = join - start
    tail_dur = end - join
    tmpdir = Path(tempfile.mkdtemp(prefix="playcut_"))
    try:
        head = tmpdir / "head.mkv"
        tail = tmpdir / "tail.mkv"

        prog(0.05, tr("重新編碼開頭 {sec:.3f} 秒…", sec=head_dur))
        cmd_head = _build_part_cmd(src, info, start, head_dur, str(head), opts,
                                   copy_video=False, delay=delay)
        runner.exec(cmd_head, head_dur, lambda f: prog(0.05 + f * 0.25, tr("重新編碼開頭…")))

        prog(0.32, tr("串流複製其餘部分…"))
        cmd_tail = _build_part_cmd(src, info, join, tail_dur, str(tail), opts,
                                   copy_video=True, delay=delay)
        runner.exec(cmd_tail, tail_dur, lambda f: prog(0.32 + f * 0.58, tr("串流複製中…")))

        prog(0.92, tr("接合片段…"))
        try:
            _concat([head, tail], out_path, runner, durations=[head_dur, tail_dur])
        except (ExportError, Cancelled) as exc:
            if isinstance(exc, Cancelled):
                raise
            # 接合失敗（少見，通常是編碼參數對不起來）-> 安全退回全重編碼
            prog(0.35, tr("接合失敗，改用全部重新編碼…"))
            cmd = _build_reencode_cmd(src, info, start, dur, out_path, opts, delay)
            runner.exec(cmd, dur, lambda f: prog(0.35 + f * 0.63, tr("重新編碼中…")))
        prog(1.0, tr("完成"))
        return out_path
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _concat(parts: list[Path], out_path: str, runner: Runner,
            durations: Optional[list[float]] = None, hevc_tag: bool = False) -> None:
    """用 concat demuxer 接合片段。

    重點：一定要寫出 `duration` 指令。片段檔自己回報的長度會因為 B-frame 造成的
    時間戳偏移而比實際內容長幾十毫秒，concat 會照那個長度去排下一段，
    接縫就會出現跳動。指定精確長度可以完全消除這個問題。
    """
    listfile = parts[0].parent / "concat.txt"
    with open(listfile, "w", encoding="utf-8") as fh:
        for i, p in enumerate(parts):
            escaped = str(p).replace("\\", "/").replace("'", r"'\''")
            fh.write(f"file '{escaped}'\n")
            if durations and i < len(durations) and durations[i] > 0:
                fh.write(f"duration {durations[i]:.6f}\n")
    cmd = [
        Tools.ffmpeg(), "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
        "-f", "concat", "-safe", "0", "-i", str(listfile),
        "-c", "copy", "-avoid_negative_ts", "make_zero",
        "-fflags", "+genpts",
    ]
    if hevc_tag and Path(out_path).suffix.lower() in (".mp4", ".mov", ".m4v"):
        cmd += ["-tag:v", "hvc1"]
    if durations:
        # 串流複製的尾段會多帶幾格（packet 邊界），在這裡切齊總長度
        cmd += ["-t", f"{sum(d for d in durations if d > 0):.6f}"]
    cmd += [out_path]
    runner.exec(cmd)


def export_all(src: str, segments: list[Segment], opts: ExportOptions,
               runner: Optional[Runner] = None,
               on_progress: Optional[ProgressCb] = None) -> list[str]:
    """匯出多個片段。opts.merge 為 True 時會接成單一檔案。"""
    runner = runner or Runner()
    info = probe(src)
    srcp = Path(src)
    out_dir = Path(opts.out_dir) if opts.out_dir else srcp.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    ext = _container_for(info, opts, srcp)

    segments = [s for s in segments if s.duration > 0]
    if not segments:
        raise ExportError(tr("沒有可匯出的片段"))

    results: list[str] = []
    n = len(segments)

    # ---- 字幕準備 ----
    sub_tmp: Optional[Path] = None
    cues: list[SUB.Cue] = []
    sub_delay = opts.subtitle.delay if opts.subtitle else 0.0
    if opts.subtitle and not opts.subtitle.external_path:
        # 內嵌字幕的時間戳是容器原始時間；播放器（mpv）的時間軸會扣掉容器起始時間
        try:
            shift = float(info.raw.get("format", {}).get("start_time") or 0.0)
        except (TypeError, ValueError):
            shift = 0.0
        opts = ExportOptions(**{**opts.__dict__, "sub_shift": shift})
        sub_delay -= shift
    if opts.subtitle and (opts.burn_subtitles or opts.export_srt):
        sub_tmp = Path(tempfile.mkdtemp(prefix="playcut_sub_"))
        try:
            if on_progress:
                on_progress(0.0, tr("準備字幕…"))
            if opts.burn_subtitles:
                bf = SUB.prepare_burn_file(opts.subtitle, src, sub_tmp)
                opts = ExportOptions(**{**opts.__dict__, "burn_file": str(bf)})
            if opts.export_srt:
                cues = SUB.load_cues(opts.subtitle, src, sub_tmp)
        except SUB.SubtitleError as exc:
            SUB.remove_tree(sub_tmp)
            raise ExportError(str(exc)) from exc
        except Exception:
            SUB.remove_tree(sub_tmp)
            raise

    speed = eff_speed(opts)

    def write_srt(out: Path, parts: list[tuple[float, float]]):
        if not opts.export_srt:
            return
        merged: list[SUB.Cue] = []
        offset = 0.0
        for a, b in parts:
            for c in SUB.cut_cues(cues, a, b, sub_delay, 0.0):
                merged.append(SUB.Cue(c.start / speed + offset,
                                      c.end / speed + offset, c.text))
            offset += (b - a) / speed
        out.with_suffix(".srt").write_text(SUB.format_srt(merged), encoding="utf-8-sig")

    try:
        return _export_all_inner(src, srcp, info, segments, opts, runner,
                                 on_progress, out_dir, ext, n, results, write_srt)
    finally:
        SUB.remove_tree(sub_tmp)


def _export_all_inner(src, srcp, info, segments, opts, runner, on_progress,
                      out_dir, ext, n, results, write_srt) -> list[str]:
    if opts.merge and n > 1:
        tmpdir = Path(tempfile.mkdtemp(prefix="playcut_merge_"))
        try:
            parts = []
            merged_opts = {**opts.__dict__, "merge": False}
            if opts.target_mb > 0 and info.has_video:
                # 目標大小指的是合併後的整個檔案：所有片段用同一個位元率
                total = sum(s.duration for s in segments) / eff_speed(opts)
                merged_opts["video_kbps"] = target_video_kbps(
                    opts.target_mb, total, audio_kbps(info, opts) if info.has_audio else 0)
            for i, seg in enumerate(segments):
                part = tmpdir / f"part{i:03d}.mkv"
                sub = ExportOptions(**merged_opts)
                export_segment(src, info, seg, str(part), sub, runner,
                               lambda f, m, i=i: on_progress and
                               on_progress((i + f) / (n + 1), f"[{i+1}/{n}] {m}"))
                parts.append(part)
            out = _unique(out_dir / f"{_safe_name(srcp.stem)}_merged{output_tag(opts)}.{ext}",
                          opts.overwrite)
            if on_progress:
                on_progress(n / (n + 1), tr("接合所有片段…"))
            _concat(parts, str(out), runner,
                    durations=[s.duration / eff_speed(opts) for s in segments],
                    hevc_tag=opts.v_codec == "hevc")
            write_srt(out, [(s.start, s.end) for s in segments])
            results.append(str(out))
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
        if on_progress:
            on_progress(1.0, tr("完成"))
        return results

    for i, seg in enumerate(segments):
        label = _safe_name(seg.name) if seg.name else f"{_fmt_tag(seg.start)}-{_fmt_tag(seg.end)}"
        out = _unique(out_dir / f"{_safe_name(srcp.stem)}_{label}{output_tag(opts)}.{ext}",
                      opts.overwrite)
        export_segment(src, info, seg, str(out), opts, runner,
                       lambda f, m, i=i: on_progress and
                       on_progress((i + f) / n, f"[{i+1}/{n}] {m}"))
        write_srt(out, [(seg.start, seg.end)])
        results.append(str(out))
    if on_progress:
        on_progress(1.0, tr("完成"))
    return results


def _fmt_tag(t: float) -> str:
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h:02d}{m:02d}{s:06.3f}".replace(".", "")


def _unique(path: Path, overwrite: bool) -> Path:
    if overwrite or not path.exists():
        return path
    stem, suffix, parent = path.stem, path.suffix, path.parent
    i = 2
    while True:
        cand = parent / f"{stem} ({i}){suffix}"
        if not cand.exists():
            return cand
        i += 1
