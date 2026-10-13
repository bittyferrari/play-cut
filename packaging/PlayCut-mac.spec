# -*- mode: python ; coding: utf-8 -*-
# macOS 用的 PyInstaller 設定。請用 build_mac.command 執行，不要直接跑。
import os
import shutil
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent
LIB_DIRS = [ROOT / "bin", Path("/opt/homebrew/lib"), Path("/usr/local/lib"), Path("/opt/local/lib")]
BIN_DIRS = [ROOT / "bin", Path("/opt/homebrew/bin"), Path("/usr/local/bin"), Path("/opt/local/bin")]


def find_libmpv():
    env = os.environ.get("PLAYCUT_LIBMPV")
    if env:
        return os.path.realpath(env)
    for d in LIB_DIRS:
        for name in ("libmpv.2.dylib", "libmpv.dylib"):
            if (d / name).exists():
                return os.path.realpath(d / name)
    raise SystemExit("找不到 libmpv.dylib，請先執行 brew install mpv")


def find_tool(name):
    env = os.environ.get("PLAYCUT_" + name.upper())
    if env:
        return os.path.realpath(env)
    for d in BIN_DIRS:
        if (d / name).exists():
            return os.path.realpath(d / name)
    found = shutil.which(name)
    if found:
        return os.path.realpath(found)
    raise SystemExit(f"找不到 {name}，請先執行 brew install ffmpeg")


libmpv = find_libmpv()
# 以固定檔名放進 .app，程式會在 Contents/Frameworks 找 libmpv.2.dylib / libmpv.dylib
binaries = [
    (libmpv, "."),
    (find_tool("ffmpeg"), "bin"),
    (find_tool("ffprobe"), "bin"),
]
print("libmpv :", binaries[0][0])
print("ffmpeg :", binaries[1][0])
print("ffprobe:", binaries[2][0])

a = Analysis(
    [str(ROOT / "run_app.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=[(str(ROOT / "playcut" / "resources"), "playcut/resources")],
    hiddenimports=["playcut"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PlayCut",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    argv_emulation=False,
)

coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="PlayCut")

icns = ROOT / "build" / "mac" / "PlayCut.icns"
VIDEO_EXTS = ["mp4", "m4v", "mov", "mkv", "avi", "webm", "wmv", "flv", "ts", "m2ts", "mts", "mpg", "mpeg", "3gp"]

app = BUNDLE(
    coll,
    name="PlayCut.app",
    icon=str(icns) if icns.exists() else None,
    bundle_identifier="app.playcut.PlayCut",
    info_plist={
        "CFBundleName": "PlayCut",
        "CFBundleDisplayName": "PlayCut",
        "CFBundleShortVersionString": "1.0.0",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "11.0",
        # 讓 Finder「打開方式」清單裡出現 PlayCut
        "CFBundleDocumentTypes": [{
            "CFBundleTypeName": "Video",
            "CFBundleTypeRole": "Viewer",
            "LSHandlerRank": "Alternate",
            "CFBundleTypeExtensions": VIDEO_EXTS,
            "LSItemContentTypes": ["public.movie", "public.video", "public.mpeg-4", "com.apple.quicktime-movie"],
        }],
    },
)
