"""截圖功能測試：只有影片 / 含字幕、檔名、同名不覆蓋、剪貼簿、寫不進去時改存別處。

執行：python tests/test_screenshot.py
（需要 ffmpeg、libmpv 與可用的 OpenGL）
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")
os.environ.setdefault("PLAYCUT_AO", "null")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

RESULTS: list[tuple[str, bool, str]] = []
SRT = "1\n00:00:00,000 --> 00:00:10,000\nHELLO SUBTITLE\n"


def check(name: str, ok: bool, detail: str = ""):
    RESULTS.append((name, bool(ok), detail))
    print(f"  {'✅' if ok else '❌'} {name}{('  — ' + detail) if detail else ''}")


def pump(app, ms=400):
    from PySide6.QtCore import QElapsedTimer
    t = QElapsedTimer()
    t.start()
    while t.elapsed() < ms:
        app.processEvents()


def bright_pixels(path: Path) -> int:
    """黑底影片上「亮的像素」數量：有字幕 > 0，沒字幕 = 0。"""
    from PySide6.QtGui import QImage
    img = QImage(str(path))
    n = 0
    for y in range(0, img.height(), 2):
        for x in range(0, img.width(), 2):
            if QImage.pixelColor(img, x, y).lightness() > 128:
                n += 1
    return n


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="fp_shot_"))
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", "color=c=black:size=480x270:rate=25:duration=10",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(work / "clip.mp4")],
                   check=True)
    (work / "clip.srt").write_text(SRT, encoding="utf-8")   # 同名 → 自動載入

    from playcut.mpvwidget import MPV_IMPORT_ERROR, configure_surface_format
    if MPV_IMPORT_ERROR is not None:
        print(f"略過：{MPV_IMPORT_ERROR}")
        return 0
    configure_surface_format()
    from PySide6.QtCore import QSettings
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(work / "cfg"))
    import playcut.mainwindow as MW

    w = MW.MainWindow()
    w.resize(900, 600)
    w.show()
    w.load(str(work / "clip.mp4"))
    pump(app, 1500)
    w.video.set_paused(True)
    w.video.seek_absolute(2.0)
    pump(app, 800)
    check("有自動載入字幕", w.video.current_subtitle() is not None)

    print("\n[1] 只有影片 / 含字幕")
    w.take_screenshot(False)
    vid = w._last_screenshot
    check("只有影片：存在影片旁邊", vid.parent == work and vid.exists(), str(vid))
    check("檔名 = 影片名_時間.png", vid.name == "clip_00-00-02.000.png", vid.name)
    img = QImage(str(vid))
    check("原始解析度 480×270", (img.width(), img.height()) == (480, 270),
          f"{img.width()}×{img.height()}")
    check("只有影片：沒有字幕", bright_pixels(vid) == 0, str(bright_pixels(vid)))

    w.take_screenshot(True)
    sub = w._last_screenshot
    check("含字幕：檔名有 _sub", sub.name == "clip_00-00-02.000_sub.png", sub.name)
    check("含字幕：畫得出字幕", bright_pixels(sub) > 50, str(bright_pixels(sub)))

    print("\n[2] 同名不覆蓋 / 格式 / 剪貼簿")
    w.take_screenshot(False)
    check("第二張加 (2)", w._last_screenshot.name == "clip_00-00-02.000 (2).png",
          w._last_screenshot.name)
    w.settings.setValue("screenshotFormat", "jpg")
    w.act_shot_clip.setChecked(True)
    QApplication.clipboard().clear()
    w.take_screenshot(False)
    check("JPG", w._last_screenshot.suffix == ".jpg" and w._last_screenshot.exists(),
          w._last_screenshot.name)
    check("有複製到剪貼簿", not QApplication.clipboard().image().isNull())

    print("\n[3] 隱藏字幕時")
    w.video.set_subtitle_visible(False)
    pump(app, 300)
    w.take_screenshot(True)
    check("隱藏字幕 → 含字幕版也沒字", bright_pixels(w._last_screenshot) == 0)
    w.video.set_subtitle_visible(True)

    print("\n[4] 自訂資料夾 / 寫不進去")
    out = work / "shots"
    w.settings.setValue("screenshotDir", str(out))
    w._sync_screenshot_ui()
    check("選單取消勾選「存到影片旁邊」", not w.act_shot_beside.isChecked())
    w.take_screenshot(False)
    check("存到自訂資料夾", w._last_screenshot.parent == out and w._last_screenshot.exists())
    fb = work / "fallback"
    MW.MainWindow._fallback_screenshot_dir = staticmethod(lambda: fb)
    bad = work / "not_a_dir.txt"
    bad.write_text("x")
    w.settings.setValue("screenshotDir", str(bad / "sub"))   # 建不出這個資料夾
    w.take_screenshot(False)
    check("寫不進去時改存備用資料夾", w._last_screenshot.parent == fb
          and w._last_screenshot.exists(), str(w._last_screenshot))

    w.close()
    w.video.shutdown()
    return summary()


def summary() -> int:
    bad = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(bad)}/{len(RESULTS)} 通過")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
