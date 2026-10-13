"""字幕功能測試：解析 / 對時 / 編碼、播放器載入與切換、匯出另存 .srt 與燒錄。

執行：python tests/test_subtitles.py
（需要 ffmpeg；UI 部分需要 libmpv 與可用的 OpenGL）
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

RESULTS: list[tuple[str, bool, str]] = []

SRT = ("1\r\n00:00:01,000 --> 00:00:03,000\r\n第一句 HELLO\r\n\r\n"
       "2\r\n00:00:05,000 --> 00:00:07,500\r\n第二句\r\n第二行\r\n\r\n"
       "3\r\n00:00:09,000 --> 00:00:11,000\r\nthird\r\n")


def check(name: str, ok: bool, detail: str = ""):
    RESULTS.append((name, bool(ok), detail))
    print(f"  {'✅' if ok else '❌'} {name}{('  — ' + detail) if detail else ''}")


def ff(*args):
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args],
                   check=True)


def make_media(work: Path):
    """黑底影片（方便檢查字幕有沒有畫出來）+ Big5 外掛字幕 + 內嵌字幕的 mkv。"""
    ff("-f", "lavfi", "-i", "color=c=black:size=480x270:rate=25:duration=12",
       "-f", "lavfi", "-i", "sine=frequency=440:duration=12",
       "-c:v", "libx264", "-g", "50", "-pix_fmt", "yuv420p", "-c:a", "aac",
       "-shortest", str(work / "clip.mp4"))
    (work / "clip.srt").write_bytes(SRT.encode("cp950"))          # 同名 → 自動載入
    (work / "other.srt").write_text(SRT.replace("third", "OTHER"), encoding="utf-8")
    (work / "u8.srt").write_text(SRT, encoding="utf-8")
    ff("-i", str(work / "clip.mp4"), "-i", str(work / "u8.srt"),
       "-map", "0", "-map", "1", "-c", "copy", "-c:s", "srt", str(work / "emb.mkv"))


def pump(app, ms=400):
    from PySide6.QtCore import QElapsedTimer
    t = QElapsedTimer()
    t.start()
    while t.elapsed() < ms:
        app.processEvents()


def ymax(path: Path, t: float) -> int:
    cp = subprocess.run(
        ["ffmpeg", "-hide_banner", "-ss", f"{t}", "-i", str(path), "-frames:v", "1",
         "-vf", "signalstats,metadata=print:key=lavfi.signalstats.YMAX",
         "-f", "null", "-"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = cp.stdout.decode("utf-8", "replace")
    for line in out.splitlines():
        if "YMAX=" in line:
            return int(float(line.split("YMAX=")[1]))
    return -1


# --------------------------------------------------------------------------
def test_logic(work: Path):
    from playcut import subtitles as SUB

    print("\n[1] 解析與編碼")
    cues = SUB.parse_srt(SUB.read_text(str(work / "clip.srt")))
    check("Big5 字幕讀得出中文", cues and cues[0].text == "第一句 HELLO",
          repr(cues[0].text if cues else None))
    check("3 句、多行保留", len(cues) == 3 and cues[1].text == "第二句\n第二行")
    vtt = SUB.parse_srt("WEBVTT\n\nid1\n00:01.500 --> 00:02.000 align:start\nhi\n")
    check("WebVTT 也能解析", len(vtt) == 1 and abs(vtt[0].start - 1.5) < 1e-6)
    check("is_subtitle", SUB.is_subtitle("a.SRT") and not SUB.is_subtitle("a.mp4"))

    print("\n[2] 片段對時")
    cut = SUB.cut_cues(cues, 4.7, 10.3, delay=0.5)
    check("延遲 + 裁切 + 平移", [(round(c.start, 3), round(c.end, 3)) for c in cut]
          == [(0.8, 3.3), (4.8, 5.6)], str([(c.start, c.end) for c in cut]))
    out = SUB.format_srt(cut)
    check("輸出 SRT 格式", out.startswith("1\n00:00:00,800 --> 00:00:03,300\n"))

    print("\n[3] 濾鏡路徑跳脫")
    esc = SUB.filter_escape_path(r"C:\Users\a'b\[x], y;z\s.srt")
    check("Windows 磁碟冒號", esc.startswith(r"C\\:/"), esc)
    check("特殊字元都有跳脫", r"\[" in esc and r"\," in esc and r"\;" in esc, esc)
    check("圖像字幕判斷",
          SUB.SubSource(codec="hdmv_pgs_subtitle").is_bitmap
          and not SUB.SubSource(external_path="a.sub", codec="microdvd").is_bitmap)


def test_export(work: Path):
    from playcut import exporter as EX, subtitles as SUB

    print("\n[4] 匯出：另存 .srt + 燒錄（外掛 Big5 字幕、字幕延遲 0.5s）")
    out = work / "out1"
    segs = [EX.Segment(0.5, 4.0), EX.Segment(4.7, 10.3)]
    opts = EX.ExportOptions(out_dir=str(out), export_srt=True, burn_subtitles=True,
                            subtitle=SUB.SubSource(codec="subrip",
                                                   external_path=str(work / "clip.srt"),
                                                   delay=0.5))
    files = EX.export_all(str(work / "clip.mp4"), segs, opts)
    check("輸出 2 個檔", len(files) == 2)
    srt1 = Path(files[0]).with_suffix(".srt")
    check("旁邊有 .srt", srt1.exists())
    txt = srt1.read_text(encoding="utf-8-sig") if srt1.exists() else ""
    check(".srt 時間正確", "00:00:01,000 --> 00:00:03,000" in txt, txt[:60])
    check("燒錄：有字幕的時間點有白字", ymax(Path(files[0]), 2.0) > 150)
    check("燒錄：沒字幕的時間點是黑的", ymax(Path(files[0]), 0.3) < 40)

    print("\n[5] 匯出：內嵌字幕、合併、無損模式（燒錄會自動改重編碼）")
    out = work / "out2"
    opts = EX.ExportOptions(mode=EX.MODE_LOSSLESS, out_dir=str(out), merge=True,
                            export_srt=True, burn_subtitles=True,
                            subtitle=SUB.SubSource(codec="subrip", ff_index=2))
    files = EX.export_all(str(work / "emb.mkv"), segs, opts)
    check("合併成 1 個檔", len(files) == 1)
    txt = Path(files[0]).with_suffix(".srt").read_text(encoding="utf-8-sig")
    check("合併後第 2 段字幕接在後面", "00:00:03,800 --> 00:00:06,300" in txt
          or "00:00:03,8" in txt, txt)
    check("合併檔燒錄正確", ymax(Path(files[0]), 1.5) > 150
          and ymax(Path(files[0]), 3.0) < 40)


def test_ui(work: Path):
    os.environ.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")
    from PySide6.QtCore import QMimeData, QPointF, QUrl, Qt
    from PySide6.QtGui import QDropEvent
    from PySide6.QtWidgets import QApplication

    from playcut.mpvwidget import configure_surface_format
    configure_surface_format()
    app = QApplication.instance() or QApplication(sys.argv)
    from playcut.mainwindow import MainWindow, apply_dark_theme
    from playcut.exportdialog import ExportDialog
    apply_dark_theme(app)

    print("\n[6] 播放器：同名字幕自動載入")
    win = MainWindow()
    win.resize(1000, 640)
    win.show()
    pump(app, 400)
    win.load(str(work / "clip.mp4"))
    for _ in range(40):
        pump(app, 150)
        if win.video.duration > 0 and win.video.subtitle_tracks():
            break
    tracks = win.video.subtitle_tracks()
    check("自動載入 clip.srt", any(t["external"] for t in tracks),
          str([t["external_filename"] for t in tracks]))
    cur = win.video.current_subtitle()
    check("自動選取字幕", cur is not None)

    win.video.set_paused(True)
    win.video.seek_absolute(2.0)
    pump(app, 800)
    img = win.video.grabFramebuffer()
    bright = sum(1 for y in range(0, img.height(), 3) for x in range(0, img.width(), 3)
                 if img.pixelColor(x, y).lightness() > 180)
    check("畫面上有畫出字幕", bright > 20, f"亮點 {bright}")

    print("\n[7] 載入其他字幕 / 切換 / 隱藏 / 延遲")
    win.add_subtitle_file(str(work / "other.srt"))
    pump(app, 500)
    tracks = win.video.subtitle_tracks()
    check("新增字幕軌", len(tracks) == 2, str(len(tracks)))
    cur = win.video.current_subtitle()
    check("新字幕自動選取", cur and cur["external_filename"].endswith("other.srt"))
    win.add_subtitle_file(str(work / "other.srt"))
    pump(app, 300)
    check("重複載入不會多一條", len(win.video.subtitle_tracks()) == 2)

    win.cycle_subtitle()
    pump(app, 300)
    check("切換到關閉", win.video.current_subtitle() is None)
    win.cycle_subtitle()
    pump(app, 300)
    check("再切回第一條", (win.video.current_subtitle() or {}).get("id") == tracks[0]["id"])

    win.toggle_subtitle()
    pump(app, 200)
    check("隱藏字幕", not win.video.is_subtitle_visible())
    check("隱藏時匯出不帶字幕", win._current_sub_source() is None)
    win.toggle_subtitle()
    pump(app, 200)

    win._nudge_sub_delay(0.1)
    win._nudge_sub_delay(0.1)
    pump(app, 200)
    check("字幕延遲 +200ms", abs(win.video.get_sub_delay() - 0.2) < 1e-6)
    src = win._current_sub_source()
    check("匯出拿到字幕來源", src is not None and src.external_path.endswith("clip.srt")
          and abs(src.delay - 0.2) < 1e-6, str(src))
    win._set_sub_delay(0.0)

    win._nudge_sub_scale(0.2)
    check("字幕放大", abs(win.video.get_sub_scale() - 1.2) < 1e-6)
    win._reset_sub_style()

    win._populate_sub_menu()
    labels = [a.text() for a in win.menu_sub_tracks.actions()]
    check("字幕選單列出軌道", len([t for t in labels if t.startswith("#")]) == 2, str(labels))
    win._update_sub_ui()
    check("按鈕顯示有字幕", "✓" in win.btn_sub.text())

    print("\n[8] 拖放：影片 + 字幕一起拖進來 / 內嵌字幕")
    md = QMimeData()
    md.setUrls([QUrl.fromLocalFile(str(work / "emb.mkv")),
                QUrl.fromLocalFile(str(work / "other.srt"))])
    ev = QDropEvent(QPointF(10, 10), Qt.CopyAction, md, Qt.LeftButton, Qt.NoModifier)
    win.dropEvent(ev)
    for _ in range(40):
        pump(app, 150)
        if len(win.video.subtitle_tracks()) >= 2:
            break
    tracks = win.video.subtitle_tracks()
    check("內嵌 + 拖進來的字幕都在", any(not t["external"] for t in tracks)
          and any(t["external"] for t in tracks), str(tracks))
    emb = next(t for t in tracks if not t["external"])
    win.video.set_subtitle_track(emb["id"])
    pump(app, 300)
    src = win._current_sub_source()
    check("內嵌字幕 → ff_index", src is not None and src.ff_index == 2, str(src))

    dlg = ExportDialog(win, win.current_file, [], 0.0, subtitle=src)
    check("匯出對話框可勾字幕選項", dlg.export_srt.isEnabled() and dlg.burn_sub.isEnabled())
    dlg.burn_sub.setChecked(True)
    o = dlg._options()
    check("選項傳到 ExportOptions", o.burn_subtitles and o.subtitle is src)
    dlg.deleteLater()
    dlg2 = ExportDialog(win, win.current_file, [], 0.0, subtitle=None)
    check("沒字幕時選項停用", not dlg2.export_srt.isEnabled())
    dlg2.deleteLater()

    win.close()
    pump(app, 300)


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="subtest_"))
    make_media(work)
    test_logic(work)
    test_export(work)
    if "--no-ui" not in sys.argv:
        test_ui(work)
    print("\n" + "=" * 60)
    ok = sum(1 for _, g, _ in RESULTS if g)
    print(f"通過 {ok}/{len(RESULTS)}")
    for name, g, d in RESULTS:
        if not g:
            print(f"  ❌ {name} {d}")
    return 0 if ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
