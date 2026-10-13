"""離屏 UI 煙霧測試：確認視窗能建起來、影片能播、旗標與片段推導正確。"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QEvent, QPointF, QTimer, Qt
from PySide6.QtGui import QPointingDevice
from PySide6.QtWidgets import QApplication

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = ""):
    RESULTS.append((name, bool(ok), detail))
    print(f"  {'✅' if ok else '❌'} {name}{('  — ' + detail) if detail else ''}")


def make_video(path: Path):
    subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=25:duration=30",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=30",
        "-c:v", "libx264", "-preset", "veryfast", "-g", "125",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path)],
        check=True)


def pump(app, ms=400):
    from PySide6.QtCore import QElapsedTimer
    t = QElapsedTimer()
    t.start()
    while t.elapsed() < ms:
        app.processEvents()


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="uismoke_"))
    video = work / "clip.mp4"
    make_video(video)

    from playcut.mpvwidget import configure_surface_format
    configure_surface_format()
    app = QApplication(sys.argv)

    from playcut.mainwindow import MainWindow, apply_dark_theme
    from playcut.markers import ROLE_IN, ROLE_OUT
    from playcut import exporter as EX
    apply_dark_theme(app)

    print("\n[1] 建立主視窗")
    win = MainWindow()
    win.resize(1000, 640)
    win.show()
    pump(app, 500)
    check("主視窗建立成功", True)
    check("播放畫面元件存在", win.video is not None)

    print("\n[2] 載入影片並播放")
    win.load(str(video))
    for _ in range(40):
        pump(app, 150)
        if win.video.duration > 0:
            break
    check("讀到影片長度", win.video.duration > 25,
          f"duration={win.video.duration:.2f}s")
    check("讀到 fps", win.video.fps > 0, f"fps={win.video.fps}")

    win.video.set_paused(False)
    p0 = win.video.position
    pump(app, 1200)
    check("畫面有在前進", win.video.position >= p0,
          f"{p0:.2f} → {win.video.position:.2f}")

    print("\n[3] 播放速度")
    win.video.set_speed(2.0)
    pump(app, 200)
    check("速度設定為 2×", abs(win.video.get_speed() - 2.0) < 1e-6)
    win._nudge_speed(-1)
    pump(app, 100)
    check("降速鍵有作用", win.video.get_speed() < 2.0,
          f"{win.video.get_speed():g}×")
    win.video.set_speed(1.0)

    print("\n[4] 聲音延遲")
    win.spn_delay.setValue(250)
    pump(app, 200)
    check("mpv audio-delay = 0.25s",
          abs(win.video.get_audio_delay() - 0.25) < 1e-3,
          f"{win.video.get_audio_delay()}")
    win.spn_delay.setValue(-120)
    pump(app, 200)
    check("負延遲也可以",
          abs(win.video.get_audio_delay() + 0.12) < 1e-3)
    win.spn_delay.setValue(0)

    print("\n[5] 精準定位與逐格")
    win.video.set_paused(True)
    win.video.seek_absolute(12.36, exact=True)
    pump(app, 700)
    check("seek 到 12.36s", abs(win.video.position - 12.36) < 0.05,
          f"{win.video.position:.3f}")
    before = win.video.position
    win.video.frame_step(True)
    pump(app, 500)
    check("下一格前進約 1 格",
          0.02 < (win.video.position - before) < 0.08,
          f"+{(win.video.position-before)*1000:.0f}ms")

    print("\n[6] 插旗標與片段推導")
    win.video.seek_absolute(60.0 if win.video.duration > 70 else 5.0, exact=True)
    pump(app, 400)
    win.markers.clear()
    win.markers.add(5.0)
    win.markers.add(10.0)
    win.markers.add(15.0)
    win.markers.add(22.5)
    win._refresh_markers()
    pump(app, 200)
    segs = win.markers.segments(win.video.duration or 30.0)
    check("4 個旗標 → 2 段", len(segs) == 2,
          f"{[(round(s.start,2), round(s.end,2)) for s in segs]}")
    check("第 1 段 5→10", abs(segs[0].start - 5) < 1e-6 and abs(segs[0].end - 10) < 1e-6)
    check("旗標表格列數正確", win.tbl.rowCount() == 4)
    roles = win.markers.roles()
    check("角色自動交替", roles == [ROLE_IN, ROLE_OUT, ROLE_IN, ROLE_OUT], str(roles))

    win.markers[2].role = ROLE_OUT
    r2 = win.markers.roles()
    win.markers[2].role = "auto"
    check("可以強制指定角色", r2[2] == ROLE_OUT, str(r2))

    print("\n[7] 落單起點延伸到片尾")
    win.markers.clear()
    win.markers.add(3.0)
    s = win.markers.segments(win.video.duration or 30.0)
    check("單一起點 → 延伸到結尾", len(s) == 1 and s[0].end > 25,
          f"{round(s[0].start,2)}→{round(s[0].end,2)}")

    print("\n[8] 旗標存檔 / 讀檔")
    win.markers.clear()
    win.markers.add(7.25, "開場")
    win.markers.add(19.5, "結束")
    win.chk_autosave.setChecked(True)   # 預設關閉，測試時手動打開
    win._autosave()
    pf = Path(str(video) + ".playcut.json")
    check("專案檔已寫出", pf.exists(), pf.name)
    win.markers.clear()
    data = win.markers.load(str(video))
    check("讀回 2 個旗標", len(win.markers) == 2)
    check("備註有保留", win.markers[0].label == "開場")
    check("聲音延遲也一起存", "audio_delay" in data)

    print("\n[9] 進度條繪製與點擊")
    win.timeline.set_duration(win.video.duration)
    win.timeline.set_position(10.0)
    from PySide6.QtGui import QPixmap
    pm = QPixmap(win.timeline.size())
    win.timeline.render(pm)
    check("進度條可以正常繪製", not pm.isNull())
    x = win.timeline._x_from_t(15.0)
    check("時間↔座標換算可逆",
          abs(win.timeline._t_from_x(x) - 15.0) < 0.2,
          f"{win.timeline._t_from_x(x):.3f}")

    print("\n[10] 觸控滑動拉進度")
    v = win.video
    v.swipe_span = 120.0
    v.seek_absolute(10.0, exact=True)
    pump(app, 500)
    W, H = v.width(), v.height()
    start_pos = v.position
    v._begin(QPointF(W * 0.5, H * 0.5))
    v._move(QPointF(W * 0.5 + 200, H * 0.5 + 3))   # 往右滑 200px
    predicted = min(v.duration, start_pos + (200 / W) * 120.0)
    check("滑動中的目標時間正確", abs(v._target - predicted) < 0.3,
          f"target={v._target:.2f} 預期={predicted:.2f}")
    check("判定為拉進度手勢", v._mode == "seek", str(v._mode))
    v._end(QPointF(W * 0.5 + 200, H * 0.5 + 3))
    pump(app, 900)
    check("放開後真的跳過去", abs(v.position - predicted) < 0.6,
          f"{v.position:.2f}")

    print("\n[11] 上下滑 = 音量 / 亮度")
    v.set_volume(80)
    v._begin(QPointF(W * 0.8, H * 0.5))
    v._move(QPointF(W * 0.8 + 2, H * 0.5 - 100))   # 右半邊往上滑
    check("右半上下滑 = 音量", v._mode == "volume", str(v._mode))
    check("音量有變大", v.get_volume() > 80, f"{v.get_volume():.0f}")
    v._end(QPointF(W * 0.8 + 2, H * 0.5 - 100))
    v._begin(QPointF(W * 0.15, H * 0.5))
    v._move(QPointF(W * 0.15 + 2, H * 0.5 - 100))
    check("左半上下滑 = 亮度", v._mode == "brightness", str(v._mode))
    v._end(QPointF(W * 0.15 + 2, H * 0.5 - 100))
    v.set_brightness(0)
    v.set_volume(100)

    print("\n[12] OSD 疊加層")
    v.flash("測試訊息", "副標", 0.5, 2000)
    pump(app, 150)
    check("OSD 會顯示", v.osd.isVisible())
    pm2 = QPixmap(v.size())
    pm2.fill(Qt.transparent)
    v.osd.render(pm2)
    check("OSD 可以繪製", not pm2.isNull())
    frame = v.grabFramebuffer()
    seen = set()
    for yy in range(0, frame.height(), 11):
        for xx in range(0, frame.width(), 11):
            seen.add(frame.pixel(xx, yy))
    check("影片畫面有真的畫出來（不是全黑）", len(seen) > 10,
          f"{len(seen)} 種顏色")

    print("\n[13] 匯出對話框")
    win.markers.clear()
    win.markers.add(4.0)
    win.markers.add(9.0)
    win._refresh_markers()
    from playcut.exportdialog import ExportDialog
    dlg = ExportDialog(win, str(video), win.markers.segments(win.video.duration),
                       audio_delay=0.25, default_dir=str(work))
    check("匯出對話框建立成功", dlg is not None)
    check("預設是智慧剪輯", dlg.mode.currentData() == EX.MODE_SMART)
    opts = dlg._options()
    check("選項讀得出來", opts.mode == EX.MODE_SMART and opts.out_dir == str(work))
    dlg.close()

    print("\n[14] 實際跑一次匯出")
    out = work / "seg.mp4"
    from playcut.ffio import probe
    info = probe(str(video))
    EX.export_segment(str(video), info, EX.Segment(4.0, 9.0), str(out),
                      EX.ExportOptions(mode=EX.MODE_SMART, audio_delay=0.25,
                                       apply_audio_delay=True), EX.Runner())
    check("片段檔產生", out.exists() and out.stat().st_size > 1000,
          f"{out.stat().st_size//1024}KB" if out.exists() else "無")

    print("\n[15] 全螢幕切換與關閉")
    win.toggle_fullscreen()
    pump(app, 200)
    win.exit_fullscreen()
    pump(app, 200)
    check("全螢幕切換沒有炸掉", True)
    win.close()
    pump(app, 400)
    check("關閉沒有炸掉", True)

    print("\n" + "=" * 60)
    bad = [r for r in RESULTS if not r[1]]
    print(f"通過 {len(RESULTS)-len(bad)}/{len(RESULTS)}")
    for name, _, detail in bad:
        print(f"  ❌ {name} {detail}")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
