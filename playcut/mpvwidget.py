"""把 libmpv 嵌進 Qt。

主要走 libmpv 的 render API + QOpenGLWidget：畫面是由 Qt 自己畫出來的，
所以觸控 / 滑鼠事件與疊加層（OSD）都能正常運作。
如果 render API 起不來，會自動退回傳統的 `--wid` 內嵌模式。
"""
from __future__ import annotations

import ctypes
import ctypes.util
import locale
import os
import sys
import time
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QOpenGLContext, QPainter, QSurfaceFormat
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QApplication, QWidget

from .ffio import app_root, search_roots
from .i18n import tr


# --------------------------------------------------------------------------
# 載入 libmpv
#   Windows：優先找專案 bin/ 內的 DLL
#   macOS  ：bin/、.app 內部、Homebrew（/opt/homebrew、/usr/local）、MacPorts
# --------------------------------------------------------------------------

# macOS 上常見的 libmpv 位置（Finder 啟動的 App 不會繼承 shell 的環境變數）
_MAC_LIB_DIRS = [Path("/opt/homebrew/lib"), Path("/usr/local/lib"), Path("/opt/local/lib")]


def _find_libmpv_darwin() -> Optional[str]:
    env = os.environ.get("PLAYCUT_LIBMPV")
    if env and Path(env).is_file():
        return env
    dirs: list[Path] = []
    for root in search_roots():
        dirs.extend([root / "bin", root, root.parent / "Frameworks"])
    dirs.extend(_MAC_LIB_DIRS)
    for d in dirs:
        if not d.is_dir():
            continue
        for name in ("libmpv.dylib", "libmpv.2.dylib"):
            if (d / name).is_file():
                return str(d / name)
        for cand in sorted(d.glob("libmpv.*.dylib"), reverse=True):
            return str(cand)
    return None


def _prepare_libmpv() -> None:
    if sys.platform == "darwin":
        _prepare_libmpv_darwin()
        return
    if sys.platform != "win32":
        return
    dirs = []
    for root in search_roots():
        dirs.extend([root / "bin", root])
    for d in dirs:
        if not d.is_dir():
            continue
        os.environ["PATH"] = str(d) + os.pathsep + os.environ.get("PATH", "")
        try:
            os.add_dll_directory(str(d))
        except (AttributeError, OSError):
            pass


def _prepare_libmpv_darwin() -> None:
    """python-mpv 在 macOS 只用 ctypes.util.find_library('mpv') 找函式庫，
    它不會搜尋 /opt/homebrew/lib，也找不到打包進 .app 的 libmpv.2.dylib。
    所以 import 期間暫時把 find_library('mpv') 導向我們找到的檔案。"""
    path = _find_libmpv_darwin()
    if not path:
        return
    orig = ctypes.util.find_library

    def _patched(name):
        if name == "mpv":
            return path
        return orig(name)

    ctypes.util.find_library = _patched
    _prepare_libmpv_darwin.restore = orig  # type: ignore[attr-defined]


_prepare_libmpv()

try:
    import mpv  # noqa: E402
    MPV_IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover
    mpv = None
    MPV_IMPORT_ERROR = exc
finally:
    _restore = getattr(_prepare_libmpv_darwin, "restore", None)
    if _restore is not None:
        ctypes.util.find_library = _restore


def _libmpv_missing_hint() -> str:
    if sys.platform == "darwin":
        return (tr("找不到 libmpv。請先執行 setup_mac.command，"
                "或在終端機輸入：brew install mpv"))
    if sys.platform == "win32":
        return tr("找不到 libmpv。請先執行 setup.bat（會自動下載 libmpv-2.dll）。")
    return tr("找不到 libmpv。請用套件管理員安裝 libmpv（例如 libmpv2 / mpv-libs）。")


def _get_proc_address(_ctx, name):
    glctx = QOpenGLContext.currentContext()
    if glctx is None:
        return 0
    if isinstance(name, bytes):
        key = name
    else:
        key = str(name).encode("utf-8")
    try:
        addr = glctx.getProcAddress(key)
    except TypeError:
        addr = glctx.getProcAddress(key.decode("utf-8"))
    return int(addr) if addr else 0


# HDR → SDR 色調映射曲線（libmpv render API 走的是 vo_gpu，只支援這幾種）
HDR_MODES = ("hable", "mobius", "reinhard", "bt.2390", "clip")
HDR_DEFAULT = "hable"


class MpvWidget(QOpenGLWidget):
    """會發出 Qt signal 的 mpv 播放畫面。"""

    positionChanged = Signal(float)
    durationChanged = Signal(float)
    pausedChanged = Signal(bool)
    speedChanged = Signal(float)
    audioDelayChanged = Signal(float)
    volumeChanged = Signal(float)
    fileLoaded = Signal(str)
    endReached = Signal()
    mpvMessage = Signal(str)
    subtitleTracksChanged = Signal()      # 字幕軌清單或目前選取的字幕變了
    subDelayChanged = Signal(float)
    hdrChanged = Signal(str)              # "PQ" / "HLG"，SDR 影片則是 ""
    _needUpdate = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        if mpv is None:
            raise RuntimeError(
                _libmpv_missing_hint() + "\n"
                + tr("原始錯誤：{err}", err=MPV_IMPORT_ERROR)
            )
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(320, 180)

        self._ctx = None
        self._proc_addr_fn = None
        self._destroyed = False
        self._duration = 0.0
        self._position = 0.0
        self._fps = 0.0
        self._hdr = ""
        self._hdr_boost = True

        # QApplication 在 macOS / Linux 會把 locale 改成系統語系，
        # 但 libmpv 要求 LC_NUMERIC 必須是 "C"，否則 mpv_create 直接失敗。
        try:
            locale.setlocale(locale.LC_NUMERIC, "C")
        except locale.Error:
            pass

        extra = {
            "hwdec": os.environ.get("PLAYCUT_HWDEC") or "auto-safe",
            # HDR → SDR：mpv 預設的 bt.2390 會把整體亮度拉得比較高，在一般 SDR 螢幕上
            # 常看起來過曝。改用 Hable（電影感曲線，暗部與亮部都會壓）+ 動態峰值偵測，
            # 觀感接近 PotPlayer。可在「檢視 → HDR 影片色調映射」切換。
            "tone_mapping": HDR_DEFAULT,
            "hdr_compute_peak": "yes",
            # HDR 影片截圖：預設會存成 16-bit PQ / BT.2020 的 HDR PNG，一般看圖軟體
            # 打開會灰濛濛的。改成跟畫面一樣轉好的 8-bit SDR 圖。
            "screenshot_tag_colorspace": "no",
            "screenshot_high_bit_depth": "no",
        }
        if os.environ.get("PLAYCUT_AO"):          # 測試 / 無音效裝置時可指定 null
            extra["ao"] = os.environ["PLAYCUT_AO"]
        if os.environ.get("PLAYCUT_MPV_LOG"):     # 疑難排解用
            extra["log_handler"] = lambda lv, pre, txt: print(
                f"[mpv {lv}] {pre}: {txt.rstrip()}", file=sys.stderr)
            extra["loglevel"] = os.environ["PLAYCUT_MPV_LOG"]
        if os.environ.get("PLAYCUT_MPV_OPTS"):    # 例如 "gpu_api=opengl,scale=bilinear"
            for item in os.environ["PLAYCUT_MPV_OPTS"].split(","):
                if "=" in item:
                    k, v = item.split("=", 1)
                    extra[k.strip().replace("-", "_")] = v.strip()

        self.mpv = mpv.MPV(
            vo="libmpv",
            keep_open="yes",
            osc=False,
            osd_level=0,
            input_default_bindings=False,
            input_vo_keyboard=False,
            input_cursor=False,
            ytdl=False,
            terminal=False,
            audio_display="no",
            # 字幕：自動載入檔名相近的外掛字幕（abc.mp4 → abc.srt / abc.zh-TW.srt）
            sub_auto="fuzzy",
            sub_codepage="auto",
            slang="zh-TW,zh-Hant,zht,cht,tc,chi,zho,zh,en,eng",
            **extra,
        )

        self._needUpdate.connect(self._request_update, Qt.QueuedConnection)

        # 保險用的重畫計時器：萬一某次 mpv 的更新通知漏掉，畫面也不會卡住
        self._repaint_timer = QTimer(self)
        self._repaint_timer.setInterval(200)
        self._repaint_timer.timeout.connect(self._request_update)
        self._repaint_timer.start()

        self._wire_properties()

    # ------------------------------------------------------------------
    # 屬性監聽
    # ------------------------------------------------------------------
    def _wire_properties(self):
        m = self.mpv

        @m.property_observer("time-pos")
        def _tp(_name, value):
            if value is not None:
                self._position = float(value)
                self.positionChanged.emit(self._position)

        @m.property_observer("duration")
        def _dur(_name, value):
            if value:
                self._duration = float(value)
                self.durationChanged.emit(self._duration)

        @m.property_observer("pause")
        def _pause(_name, value):
            self.pausedChanged.emit(bool(value))

        @m.property_observer("speed")
        def _spd(_name, value):
            if value:
                self.speedChanged.emit(float(value))

        @m.property_observer("audio-delay")
        def _ad(_name, value):
            if value is not None:
                self.audioDelayChanged.emit(float(value))

        @m.property_observer("volume")
        def _vol(_name, value):
            if value is not None:
                self.volumeChanged.emit(float(value))

        @m.property_observer("container-fps")
        def _fpsobs(_name, value):
            if value:
                self._fps = float(value)

        @m.property_observer("eof-reached")
        def _eof(_name, value):
            if value:
                self.endReached.emit()

        @m.property_observer("track-list")
        def _tracks(_name, _value):
            self.subtitleTracksChanged.emit()

        @m.property_observer("sid")
        def _sid(_name, _value):
            self.subtitleTracksChanged.emit()

        @m.property_observer("sub-visibility")
        def _subvis(_name, _value):
            self.subtitleTracksChanged.emit()

        @m.property_observer("video-params")
        def _vparams(_name, value):
            gamma = str((value or {}).get("gamma") or "").lower()
            kind = {"pq": "PQ", "hlg": "HLG"}.get(gamma, "")
            if value and kind != self._hdr:
                self._hdr = kind
                self.hdrChanged.emit(kind)

        @m.property_observer("sub-delay")
        def _sd(_name, value):
            if value is not None:
                self.subDelayChanged.emit(float(value))

        @m.event_callback("file-loaded")
        def _loaded(_event):
            try:
                path = self.mpv.path or ""
            except Exception:
                path = ""
            self.fileLoaded.emit(path)

    # ------------------------------------------------------------------
    # OpenGL
    # ------------------------------------------------------------------
    def initializeGL(self):
        if self._ctx is not None:
            return
        # 不同版本的 python-mpv 名字不一樣，兩種都試
        fn_type = getattr(mpv, "MpvGlGetProcAddressFn", None) or \
            getattr(mpv, "OpenGlCbGetProcAddrFn", None)
        if fn_type is None:
            self.mpvMessage.emit(tr("python-mpv 版本過舊，缺少 render API。"))
            return
        try:
            # 必須保留參考，否則會被 GC 掉導致崩潰
            self._proc_addr_fn = fn_type(_get_proc_address)
            self._ctx = mpv.MpvRenderContext(
                self.mpv,
                "opengl",
                opengl_init_params={"get_proc_address": self._proc_addr_fn},
            )
            self._ctx.update_cb = self._on_mpv_update
        except Exception as exc:
            self._ctx = None
            self.mpvMessage.emit(tr("OpenGL 繪圖初始化失敗：{err}", err=exc))

    def _on_mpv_update(self):
        # 這個 callback 來自 mpv 的繪圖執行緒，用 queued signal 丟回 GUI 執行緒
        try:
            self._needUpdate.emit()
        except Exception:
            pass

    @Slot()
    def _request_update(self):
        if not self._destroyed:
            self.update()

    def paintGL(self):
        """先讓 mpv 畫影片，再用 QPainter 疊上 OSD。

        OSD 不能用子視窗（child widget）來做：在部分平台上，蓋在
        QOpenGLWidget 上的子視窗會讓底下的 OpenGL 內容整個變黑。
        """
        if self._destroyed:
            return
        painter = QPainter(self)
        painter.beginNativePainting()
        self._render_mpv()
        painter.endNativePainting()
        try:
            self.paint_overlay(painter)
        except Exception:
            pass
        painter.end()

    def _render_mpv(self):
        if self._ctx is None:
            return
        ratio = self.devicePixelRatioF()
        w = max(1, int(round(self.width() * ratio)))
        h = max(1, int(round(self.height() * ratio)))
        try:
            self._ctx.render(
                flip_y=True,
                opengl_fbo={"w": w, "h": h, "fbo": self.defaultFramebufferObject()},
            )
        except Exception as exc:
            self._render_errors = getattr(self, "_render_errors", 0) + 1
            if self._render_errors <= 3:
                self.mpvMessage.emit(tr("畫面繪製錯誤：{err}", err=exc))

    def paint_overlay(self, painter):
        """子類別可以覆寫，在影片上面畫東西。"""
        return

    def closeEvent(self, ev):
        self.shutdown()
        super().closeEvent(ev)

    def shutdown(self):
        if self._destroyed:
            return
        self._destroyed = True
        # render context 必須在「自己的 OpenGL context 是 current」時釋放，
        # 否則 mpv 可能在結束時卡住 → 程式沒真的退出，影片檔就一直被鎖著。
        made_current = False
        try:
            if self._ctx is not None and self.context() is not None:
                self.makeCurrent()
                made_current = True
        except Exception:
            pass
        try:
            if self._ctx is not None:
                self._ctx.update_cb = None
                self._ctx.free()
        except Exception:
            pass
        if made_current:
            try:
                self.doneCurrent()
            except Exception:
                pass
        self._ctx = None
        self._proc_addr_fn = None
        for meth in ("terminate", "terminate_destroy", "_terminate"):
            fn = getattr(self.mpv, meth, None)
            if callable(fn):
                try:
                    fn()
                    break
                except Exception:
                    continue

    # ------------------------------------------------------------------
    # 播放控制
    # ------------------------------------------------------------------
    def open(self, path: str):
        self.mpv.play(path)
        self.mpv.pause = False

    def stop(self):
        try:
            self.mpv.command("stop")
        except Exception:
            pass

    def release_file(self, timeout: float = 4.0) -> bool:
        """停止播放並等 mpv 真的把檔案關掉（縮到系統匣時用，讓影片可以被刪除）。

        mpv 的 stop 是非同步的：指令送出後，實際關檔是在 mpv 的播放執行緒做。
        如果馬上把視窗藏起來，render API 就沒人再呼叫 render()，mpv 可能卡在
        等畫面、遲遲不關檔。所以這裡一邊讓 Qt 繼續處理事件（照常畫面），
        一邊等 mpv 進入 idle。成功回傳 True；逾時回傳 False。
        """
        try:
            self.mpv.command("stop")
        except Exception:
            pass
        try:
            self.mpv.command("playlist-clear")
        except Exception:
            pass
        deadline = time.monotonic() + timeout
        while True:
            try:
                idle = bool(self.mpv.idle_active) and not self.mpv.path
            except Exception:
                idle = False
            if idle:
                break
            if time.monotonic() >= deadline:
                return False
            self.update()
            QApplication.processEvents()
            time.sleep(0.01)
        self._position = 0.0
        self._duration = 0.0
        return True

    @property
    def duration(self) -> float:
        return self._duration

    @property
    def position(self) -> float:
        return self._position

    @property
    def fps(self) -> float:
        if self._fps:
            return self._fps
        try:
            v = self.mpv.container_fps
            return float(v) if v else 0.0
        except Exception:
            return 0.0

    @property
    def frame_time(self) -> float:
        f = self.fps
        return 1.0 / f if f else 0.04

    def toggle_pause(self):
        try:
            self.mpv.pause = not self.mpv.pause
        except Exception:
            pass

    def set_paused(self, paused: bool):
        try:
            self.mpv.pause = bool(paused)
        except Exception:
            pass

    def is_paused(self) -> bool:
        try:
            return bool(self.mpv.pause)
        except Exception:
            return True

    def seek_absolute(self, t: float, exact: bool = True):
        t = max(0.0, min(t, self._duration or t))
        try:
            self.mpv.command("seek", f"{t:.6f}", "absolute",
                             "exact" if exact else "keyframes")
        except Exception:
            pass

    def seek_relative(self, dt: float, exact: bool = True):
        try:
            self.mpv.command("seek", f"{dt:.6f}", "relative",
                             "exact" if exact else "keyframes")
        except Exception:
            pass

    def frame_step(self, forward: bool = True):
        try:
            self.mpv.command("frame-step" if forward else "frame-back-step")
        except Exception:
            pass

    # 播放速度 -------------------------------------------------------
    def set_speed(self, speed: float):
        speed = max(0.1, min(10.0, float(speed)))
        try:
            self.mpv.speed = speed
        except Exception:
            pass

    def get_speed(self) -> float:
        try:
            return float(self.mpv.speed)
        except Exception:
            return 1.0

    # 聲音延遲 -------------------------------------------------------
    def set_audio_delay(self, seconds: float):
        try:
            self.mpv.audio_delay = float(seconds)
        except Exception:
            pass

    def get_audio_delay(self) -> float:
        try:
            return float(self.mpv.audio_delay)
        except Exception:
            return 0.0

    # 音量 / 畫面 ----------------------------------------------------
    def set_volume(self, vol: float):
        try:
            self.mpv.volume = max(0.0, min(150.0, float(vol)))
        except Exception:
            pass

    def get_volume(self) -> float:
        try:
            return float(self.mpv.volume)
        except Exception:
            return 100.0

    def set_mute(self, mute: bool):
        try:
            self.mpv.mute = bool(mute)
        except Exception:
            pass

    def is_muted(self) -> bool:
        try:
            return bool(self.mpv.mute)
        except Exception:
            return False

    def set_brightness(self, value: int):
        try:
            self.mpv.brightness = max(-100, min(100, int(value)))
        except Exception:
            pass

    def get_brightness(self) -> int:
        try:
            return int(self.mpv.brightness)
        except Exception:
            return 0

    # HDR -------------------------------------------------------------
    # vo_gpu 的色調映射會把顏色洗淡、對比壓平，HDR 影片看起來灰灰暗暗的。
    # 只在播放 HDR 影片時補一點飽和度與對比，SDR 影片完全不動。
    HDR_BOOST_SATURATION = 40
    HDR_BOOST_CONTRAST = 15

    def set_hdr_tonemap(self, mode: str, peak_detect: bool = True,
                        boost: bool = True):
        """HDR 影片轉到 SDR 螢幕時用的色調映射曲線，播放中也能即時切換。"""
        if mode not in HDR_MODES:
            mode = HDR_DEFAULT
        self._hdr_boost = bool(boost)
        try:
            self.mpv["tone-mapping"] = mode
            self.mpv["hdr-compute-peak"] = "yes" if peak_detect else "no"
        except Exception:
            pass
        self.apply_hdr_boost()

    def apply_hdr_boost(self):
        on = bool(self._hdr) and self._hdr_boost
        try:
            self.mpv["saturation"] = self.HDR_BOOST_SATURATION if on else 0
            self.mpv["contrast"] = self.HDR_BOOST_CONTRAST if on else 0
        except Exception:
            pass

    def hdr_kind(self) -> Optional[str]:
        """目前影片是 HDR 的話回傳 "PQ" / "HLG"，否則 None。"""
        return self._hdr or None

    # 字幕 -----------------------------------------------------------
    def add_subtitle(self, path: str) -> bool:
        """載入外掛字幕並切換過去。影片還沒載入時會失敗（回傳 False）。"""
        try:
            self.mpv.command("sub-add", str(path), "select")
            return True
        except Exception as exc:
            self.mpvMessage.emit(tr("字幕載入失敗：{err}", err=exc))
            return False

    def subtitle_tracks(self) -> list[dict]:
        """回傳字幕軌清單：[{id, title, lang, codec, external, external_filename,
        ff_index, selected}]"""
        try:
            tracks = self.mpv.track_list or []
        except Exception:
            return []
        out = []
        for t in tracks:
            if t.get("type") != "sub":
                continue
            ff = t.get("ff-index", t.get("ff_index"))
            out.append({
                "id": int(t.get("id", 0)),
                "title": t.get("title") or "",
                "lang": t.get("lang") or "",
                "codec": t.get("codec") or "",
                "external": bool(t.get("external")),
                "external_filename": t.get("external-filename",
                                           t.get("external_filename")) or "",
                "ff_index": int(ff) if ff is not None else -1,
                "selected": bool(t.get("selected")),
            })
        return out

    @staticmethod
    def track_label(t: dict) -> str:
        parts = []
        if t.get("title"):
            parts.append(t["title"])
        if t.get("lang"):
            parts.append(f"[{t['lang']}]")
        if t.get("external") and t.get("external_filename"):
            name = os.path.basename(t["external_filename"])
            if name not in parts:
                parts.append(name)
            parts.append(tr("（外掛）"))
        if t.get("codec"):
            parts.append(f"· {t['codec']}")
        return f"#{t['id']} " + " ".join(parts) if parts else f"#{t['id']}"

    def current_subtitle(self) -> Optional[dict]:
        for t in self.subtitle_tracks():
            if t["selected"]:
                return t
        return None

    def set_subtitle_track(self, sid) -> None:
        """sid = 軌道 id；None / False = 關閉字幕。"""
        try:
            self.mpv.sid = sid if sid else "no"
        except Exception:
            pass

    def cycle_subtitle(self) -> Optional[dict]:
        """依序切換：字幕 1 → 字幕 2 → … → 關閉 → 字幕 1。回傳切換後的字幕軌。"""
        tracks = self.subtitle_tracks()
        if not tracks:
            return None
        ids = [t["id"] for t in tracks]
        cur = next((t["id"] for t in tracks if t["selected"]), None)
        if cur is None:
            nxt = ids[0]
        else:
            i = ids.index(cur)
            nxt = ids[i + 1] if i + 1 < len(ids) else None
        self.set_subtitle_track(nxt)
        if nxt is not None:
            self.set_subtitle_visible(True)
        return next((t for t in tracks if t["id"] == nxt), None)

    def set_subtitle_visible(self, visible: bool):
        try:
            self.mpv.sub_visibility = bool(visible)
        except Exception:
            pass

    def is_subtitle_visible(self) -> bool:
        try:
            return bool(self.mpv.sub_visibility)
        except Exception:
            return True

    def set_sub_delay(self, seconds: float):
        try:
            self.mpv.sub_delay = float(seconds)
        except Exception:
            pass

    def get_sub_delay(self) -> float:
        try:
            return float(self.mpv.sub_delay)
        except Exception:
            return 0.0

    def set_sub_scale(self, scale: float):
        try:
            self.mpv.sub_scale = max(0.3, min(4.0, float(scale)))
        except Exception:
            pass

    def get_sub_scale(self) -> float:
        try:
            return float(self.mpv.sub_scale)
        except Exception:
            return 1.0

    def set_sub_pos(self, pos: int):
        try:
            self.mpv.sub_pos = max(0, min(150, int(pos)))
        except Exception:
            pass

    def get_sub_pos(self) -> int:
        try:
            return int(self.mpv.sub_pos)
        except Exception:
            return 100

    # 截圖 -----------------------------------------------------------
    def screenshot_to_file(self, path: str, with_subtitles: bool = True) -> Optional[str]:
        """把目前這一格存成圖檔，格式依副檔名（.png / .jpg）決定。

        with_subtitles=True  → 影片 + 目前顯示中的字幕（跟畫面上看到的一樣，但不含 OSD）
        with_subtitles=False → 只有影片本身
        圖片是影片的原始解析度，跟視窗大小無關。
        回傳 None = 成功，否則回傳錯誤訊息。
        """
        try:
            self.mpv.command("screenshot-to-file", str(path),
                             "subtitles" if with_subtitles else "video")
            return None
        except Exception as exc:
            return str(exc) or exc.__class__.__name__

    @property
    def filename(self) -> str:
        try:
            return self.mpv.path or ""
        except Exception:
            return ""


from .glformat import configure_surface_format  # noqa: E402,F401  （舊的匯入路徑相容）
