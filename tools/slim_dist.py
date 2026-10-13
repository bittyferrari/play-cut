"""把 PyInstaller onedir 打包結果裡用不到的 Qt 檔案刪掉（build_folder.bat 會自動呼叫）。

用法：python tools/slim_dist.py [dist\\PlayCut]

會刪掉的東西（程式完全沒用到，已確認留下來的 DLL 不依賴它們）：
  * QML / Quick / 虛擬鍵盤 —— 是 qtvirtualkeyboardplugin 連帶拉進來的
  * Qt PDF 與 qpdf 圖片外掛
  * tls / networkinformation / TUIO 觸控外掛（QtNetwork 本體保留，tray.py 要用）
  * 用不到的平台外掛（direct2d / offscreen / minimal）
  * Qt 內建翻譯只留 i18n.py 會載入的語言（ja / zh_CN / zh_TW）

刻意保留：opengl32sw.dll（沒有顯示卡驅動或遠端桌面時的軟體 OpenGL 備援）。
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REMOVE = [
    # QML / Quick / 虛擬鍵盤
    "Qt6Quick.dll", "Qt6Qml.dll", "Qt6QmlModels.dll", "Qt6QmlMeta.dll",
    "Qt6QmlWorkerScript.dll", "Qt6VirtualKeyboard.dll",
    "plugins/platforminputcontexts",
    # PDF
    "Qt6Pdf.dll", "plugins/imageformats/qpdf.dll",
    # 網路外掛（QtNetwork 本體要留：tray.py 的單一實例用 QLocalServer，
    # 走本機 named pipe，不需要 TLS / 網路狀態外掛）
    "plugins/tls", "plugins/networkinformation", "plugins/generic",
    # 用不到的平台外掛
    "plugins/platforms/qdirect2d.dll", "plugins/platforms/qoffscreen.dll",
    "plugins/platforms/qminimal.dll",
]

KEEP_LANGS = ("ja", "zh_CN", "zh_TW")


def slim(app_dir: Path) -> int:
    qt = app_dir / "_internal" / "PySide6"
    if not qt.is_dir():
        print(f"[X] 找不到 {qt}")
        return 1

    freed = 0

    def size(p: Path) -> int:
        if p.is_file():
            return p.stat().st_size
        return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())

    def drop(p: Path):
        nonlocal freed
        if not p.exists():
            return
        freed += size(p)
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()

    for rel in REMOVE:
        drop(qt / rel)

    tr_dir = qt / "translations"
    if tr_dir.is_dir():
        for f in tr_dir.glob("*.qm"):
            keep = (not f.name.startswith("qt_help_")
                    and any(f.stem.endswith("_" + lang) for lang in KEEP_LANGS))
            if not keep:
                drop(f)

    print(f"[OK] 精簡完成，省下 {freed / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "dist" / "PlayCut"
    sys.exit(slim(target))
