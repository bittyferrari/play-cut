"""下載 PlayCut 需要的兩個 Windows 執行檔到 bin\\：

  libmpv-2.dll   播放核心
  ffmpeg.exe     剪輯匯出
  ffprobe.exe    讀取影片資訊

每個來源都有備援網址，某一個掛掉還會再試下一個。
可以重複執行；已經存在的檔案會跳過（加上 --force 可強制重抓）。
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import shutil
import ssl
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BIN = ROOT / "bin"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PlayCut-setup"}
TIMEOUT = 60


def log(msg: str):
    """印訊息。Windows 主控台字型可能沒有某些符號，失敗就退回 ASCII。"""
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def urlopen(url: str, accept: str = ""):
    headers = dict(UA)
    if accept:
        headers["Accept"] = accept
    req = urllib.request.Request(url, headers=headers)
    return urllib.request.urlopen(req, timeout=TIMEOUT)


def download(url: str, dest: Path) -> Path:
    log(f"    下載 {url}")
    with urlopen(url) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        with open(dest, "wb") as fh:
            while True:
                chunk = resp.read(262144)
                if not chunk:
                    break
                fh.write(chunk)
                done += len(chunk)
                if total:
                    pct = done * 100 // total
                    print(f"\r    進度 {pct:3d}%  ({done/1e6:.1f} / {total/1e6:.1f} MB)",
                          end="", flush=True)
    print()
    return dest


def github_asset(repo: str, pattern: str) -> str | None:
    """在 GitHub 最新 release 裡找符合 pattern 的檔案網址。"""
    for api in (f"https://api.github.com/repos/{repo}/releases/latest",
                f"https://api.github.com/repos/{repo}/releases?per_page=5"):
        try:
            with urlopen(api, "application/vnd.github+json") as r:
                data = json.loads(r.read().decode("utf-8"))
        except Exception as exc:
            log(f"    （{repo} 查詢失敗：{exc}）")
            continue
        releases = data if isinstance(data, list) else [data]
        rx = re.compile(pattern, re.I)
        for rel in releases:
            for asset in rel.get("assets", []):
                if rx.search(asset.get("name", "")):
                    return asset.get("browser_download_url")
    return None


# --------------------------------------------------------------------------
# libmpv
# --------------------------------------------------------------------------

def fetch_libmpv(force: bool) -> bool:
    target = BIN / "libmpv-2.dll"
    if target.exists() and not force:
        log("  libmpv-2.dll 已存在，跳過")
        return True

    log("  尋找 libmpv…")
    candidates = []
    # 不要抓 -v3- 的版本：那需要較新的 CPU 指令集
    u = github_asset("zhongfly/mpv-winbuild", r"^mpv-dev-x86_64-(?!v3)\d.*\.7z$")
    if u:
        candidates.append(u)
    u = github_asset("shinchiro/mpv-winbuild-cmake", r"^mpv-dev-x86_64-\d.*\.7z$")
    if u:
        candidates.append(u)

    if not candidates:
        log("  [X] 找不到 libmpv 的下載網址")
        return False

    try:
        import py7zr  # noqa: F401
    except ImportError:
        log("  [X] 缺少 py7zr 套件，請先執行：pip install py7zr")
        return False
    import py7zr

    for url in candidates:
        tmp = Path(tempfile.mkdtemp(prefix="mpv_"))
        try:
            arc = download(url, tmp / "mpv-dev.7z")
            with py7zr.SevenZipFile(arc, "r") as z:
                names = z.getnames()
                want = [n for n in names
                        if n.lower().endswith(("libmpv-2.dll", "mpv-2.dll",
                                               "mpv-1.dll", "libmpv.dll"))]
                if not want:
                    log("    壓縮檔裡找不到 DLL，換下一個來源")
                    continue
                z.extract(path=tmp, targets=want)
            for n in want:
                src = tmp / n
                if src.exists():
                    BIN.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, target)
                    log(f"  [OK] libmpv-2.dll  ({target.stat().st_size/1e6:.1f} MB)")
                    return True
        except Exception as exc:
            log(f"    失敗：{exc}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return False


# --------------------------------------------------------------------------
# ffmpeg
# --------------------------------------------------------------------------

def fetch_ffmpeg(force: bool) -> bool:
    ff, fp = BIN / "ffmpeg.exe", BIN / "ffprobe.exe"
    if ff.exists() and fp.exists() and not force:
        log("  ffmpeg.exe / ffprobe.exe 已存在，跳過")
        return True

    log("  尋找 ffmpeg…")
    candidates = ["https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"]
    u = github_asset("BtbN/FFmpeg-Builds", r"^ffmpeg-master-latest-win64-gpl\.zip$")
    if u:
        candidates.append(u)
    u = github_asset("GyanD/codexffmpeg", r"^ffmpeg-.*-essentials_build\.zip$")
    if u:
        candidates.append(u)

    for url in candidates:
        tmp = Path(tempfile.mkdtemp(prefix="ffmpeg_"))
        try:
            arc = download(url, tmp / "ffmpeg.zip")
            with zipfile.ZipFile(arc) as z:
                got = 0
                for name in z.namelist():
                    base = os.path.basename(name).lower()
                    if base in ("ffmpeg.exe", "ffprobe.exe"):
                        BIN.mkdir(parents=True, exist_ok=True)
                        with z.open(name) as fsrc, open(BIN / base, "wb") as fdst:
                            shutil.copyfileobj(fsrc, fdst)
                        got += 1
                if got >= 2:
                    log(f"  [OK] ffmpeg.exe  ({ff.stat().st_size/1e6:.1f} MB)")
                    log(f"  [OK] ffprobe.exe ({fp.stat().st_size/1e6:.1f} MB)")
                    return True
                log("    壓縮檔裡找不到執行檔，換下一個來源")
        except Exception as exc:
            log(f"    失敗：{exc}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return False


MANUAL = """
------------------------------------------------------------
自動下載失敗時，可以手動放檔案（兩個都放到 bin\\ 資料夾）：

1) libmpv-2.dll
   到 https://github.com/zhongfly/mpv-winbuild/releases
   下載 mpv-dev-x86_64-<日期>.7z（不要選檔名含 v3 的）
   解壓後把 libmpv-2.dll 複製到  bin\\libmpv-2.dll

2) ffmpeg.exe 與 ffprobe.exe
   到 https://www.gyan.dev/ffmpeg/builds/
   下載 release essentials 的 zip，解壓後在 bin\\ 資料夾裡
   把 ffmpeg.exe 與 ffprobe.exe 複製到  bin\\

放好之後直接跑 run.bat 就可以了。
------------------------------------------------------------
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="已存在也重新下載")
    args = ap.parse_args()

    BIN.mkdir(parents=True, exist_ok=True)
    log(f"下載目的地：{BIN}\n")

    ok_mpv = fetch_libmpv(args.force)
    print()
    ok_ff = fetch_ffmpeg(args.force)

    print()
    if ok_mpv and ok_ff:
        log("[OK] 全部就緒！接下來點兩下 run.bat 就可以啟動。")
        return 0
    if not ok_mpv:
        log("[X] libmpv 沒有裝好 —— 沒有它播放器無法啟動")
    if not ok_ff:
        log("[X] ffmpeg 沒有裝好 —— 播放可以用，但無法匯出片段")
    log(MANUAL)
    return 1


if __name__ == "__main__":
    sys.exit(main())
