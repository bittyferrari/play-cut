"""下載 PlayCut 需要的兩個 Windows 執行檔到 bin\\：

  libmpv-2.dll   播放核心
  ffmpeg.exe     剪輯匯出
  ffprobe.exe    讀取影片資訊

每個來源都有備援網址，某一個掛掉還會再試下一個。
可以重複執行；已經存在的檔案會跳過（加上 --force 可強制重抓）。

CPU 架構會自動判斷（看執行這支腳本的 Python 是 x64 還是 ARM64），
也可以用 --arch x64 / --arch arm64 指定。bin\\ 裡已經有檔案、但架構不對時
（例如把 x64 電腦上的專案資料夾整個複製到 ARM 筆電），會自動重新下載。

ARM64 版的 libmpv 壓縮檔用了 7z 的 ARM64 濾鏡，py7zr 解不開，
所以會改用 7-Zip（已安裝的 7z.exe，或自動下載官方的 7zr.exe）。
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BIN = ROOT / "bin"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PlayCut-setup"}
TIMEOUT = 60

# PE 檔頭裡的 Machine 欄位
PE_MACHINE = {"x64": 0x8664, "arm64": 0xAA64}
PE_NAMES = {0x8664: "x64", 0xAA64: "arm64", 0x014C: "x86"}


def host_arch() -> str:
    """執行這支腳本的 Python 是哪個架構（x64 Python 在 ARM 電腦上模擬執行時回傳 x64，
    這是對的：打包出來的程式架構跟 Python 一樣）。"""
    m = platform.machine().lower()
    if m in ("arm64", "aarch64"):
        return "arm64"
    return "x64"


ARCH = host_arch()


def pe_arch(path: Path) -> str | None:
    """讀 exe / dll 的 PE 檔頭，回傳 'x64' / 'arm64' / 'x86'；讀不出來就回傳 None。"""
    try:
        with open(path, "rb") as fh:
            head = fh.read(4096)
        if head[:2] != b"MZ":
            return None
        off = struct.unpack_from("<I", head, 0x3C)[0]
        if head[off:off + 4] != b"PE\0\0":
            return None
        return PE_NAMES.get(struct.unpack_from("<H", head, off + 4)[0], "unknown")
    except Exception:
        return None


def have_ok(path: Path) -> bool:
    """檔案存在而且架構正確。"""
    if not path.exists():
        return False
    got = pe_arch(path)
    if got is not None and got != ARCH:
        log(f"  {path.name} 是 {got} 版本，跟目前的 {ARCH} 不符，重新下載")
        return False
    return True


def check_arch(path: Path) -> bool:
    got = pe_arch(path)
    if got is not None and got != ARCH:
        log(f"    {path.name} 是 {got} 版本，不是 {ARCH}，換下一個來源")
        return False
    return True


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
    # 在 GitHub Actions 上執行時帶 token，避免 API 查詢次數被限制
    token = os.environ.get("GITHUB_TOKEN")
    if token and url.startswith("https://api.github.com/"):
        headers["Authorization"] = f"Bearer {token}"
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

MPV_DLL_NAMES = ("libmpv-2.dll", "mpv-2.dll", "mpv-1.dll", "libmpv.dll")   # 依優先順序


def _pick_dll(root: Path) -> Path | None:
    found = {p.name.lower(): p for p in root.rglob("*.dll")}
    for name in MPV_DLL_NAMES:
        if name in found:
            return found[name]
    return None


def _extract_py7zr(arc: Path, out: Path) -> Path | None:
    """用 py7zr 解。沒裝或遇到不支援的壓縮方式（例如 ARM64 濾鏡）就回傳 None。"""
    try:
        import py7zr
    except ImportError:
        return None
    try:
        with py7zr.SevenZipFile(arc, "r") as z:
            want = [n for n in z.getnames() if n.lower().endswith(MPV_DLL_NAMES)]
            if not want:
                return None
            z.extract(path=out, targets=want)
        return _pick_dll(out)
    except Exception as exc:
        log(f"    py7zr 解不開（{exc.__class__.__name__}），改用 7-Zip")
        return None


def _seven_zip_candidates() -> list[str]:
    cands = []
    for name in ("7z", "7za", "7zz", "7zr"):
        p = shutil.which(name)
        if p:
            cands.append(p)
    if sys.platform == "win32":
        for env in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)"):
            base = os.environ.get(env)
            if base:
                p = Path(base) / "7-Zip" / "7z.exe"
                if p.exists():
                    cands.append(str(p))
    return list(dict.fromkeys(cands))


def _download_7zr(tmp: Path) -> str | None:
    """下載 7-Zip 官方的獨立版 7zr.exe（約 600 KB，只會解 .7z）。
    它是 x86 程式，在 ARM64 Windows 上會自動用模擬執行。"""
    if sys.platform != "win32":
        return None
    urls = []
    u = github_asset("ip7z/7zip", r"^7zr\.exe$")
    if u:
        urls.append(u)
    urls.append("https://www.7-zip.org/a/7zr.exe")
    for url in urls:
        try:
            return str(download(url, tmp / "7zr.exe"))
        except Exception as exc:
            log(f"    7zr.exe 下載失敗：{exc}")
    return None


def _extract_7zip(arc: Path, out: Path, tmp: Path) -> Path | None:
    tools = _seven_zip_candidates()
    if not tools:
        log("    找不到 7-Zip，下載 7zr.exe…")
        t = _download_7zr(tmp)
        if t:
            tools = [t]
    for exe in tools:
        try:
            cp = subprocess.run([exe, "x", "-y", f"-o{out}", str(arc)],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                timeout=600)
        except Exception as exc:
            log(f"    {exe} 執行失敗：{exc}")
            continue
        dll = _pick_dll(out)
        if dll:
            return dll
        tail = cp.stdout.decode("utf-8", "replace").strip().splitlines()[-3:]
        log(f"    {exe} 解壓失敗：{' / '.join(tail)}")
    return None


def extract_libmpv(arc: Path, tmp: Path) -> Path | None:
    dll = _extract_py7zr(arc, tmp / "py7zr")
    if dll:
        return dll
    return _extract_7zip(arc, tmp / "7zip", tmp)


def fetch_libmpv(force: bool) -> bool:
    target = BIN / "libmpv-2.dll"
    if have_ok(target) and not force:
        log("  libmpv-2.dll 已存在，跳過")
        return True

    log(f"  尋找 libmpv（{ARCH}）…")
    candidates = []
    if ARCH == "arm64":
        patterns = [("zhongfly/mpv-winbuild", r"^mpv-dev-aarch64-\d.*\.7z$"),
                    ("shinchiro/mpv-winbuild-cmake", r"^mpv-dev-aarch64-\d.*\.7z$")]
    else:
        # 不要抓 -v3- 的版本：那需要較新的 CPU 指令集
        patterns = [("zhongfly/mpv-winbuild", r"^mpv-dev-x86_64-(?!v3)\d.*\.7z$"),
                    ("shinchiro/mpv-winbuild-cmake", r"^mpv-dev-x86_64-\d.*\.7z$")]
    for repo, pat in patterns:
        u = github_asset(repo, pat)
        if u:
            candidates.append(u)

    if not candidates:
        log("  [X] 找不到 libmpv 的下載網址")
        return False

    for url in candidates:
        tmp = Path(tempfile.mkdtemp(prefix="mpv_"))
        try:
            arc = download(url, tmp / "mpv-dev.7z")
            src = extract_libmpv(arc, tmp)
            if not src:
                log("    解壓失敗或壓縮檔裡找不到 DLL，換下一個來源")
                continue
            if not check_arch(src):
                continue
            BIN.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)
            log(f"  [OK] libmpv-2.dll  {ARCH}  ({target.stat().st_size/1e6:.1f} MB)")
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
    if have_ok(ff) and have_ok(fp) and not force:
        log("  ffmpeg.exe / ffprobe.exe 已存在，跳過")
        return True

    log(f"  尋找 ffmpeg（{ARCH}）…")
    candidates = []
    if ARCH == "arm64":
        # gyan.dev 只有 x64；ARM64 用 BtbN 的 winarm64 版本
        patterns = [("BtbN/FFmpeg-Builds", r"^ffmpeg-n[\d.]+-latest-winarm64-gpl-[\d.]+\.zip$"),
                    ("BtbN/FFmpeg-Builds", r"^ffmpeg-master-latest-winarm64-gpl\.zip$")]
    else:
        candidates.append("https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip")
        patterns = [("BtbN/FFmpeg-Builds", r"^ffmpeg-master-latest-win64-gpl\.zip$"),
                    ("GyanD/codexffmpeg", r"^ffmpeg-.*-essentials_build\.zip$")]
    for repo, pat in patterns:
        u = github_asset(repo, pat)
        if u:
            candidates.append(u)
    if ARCH == "arm64":
        # GitHub API 查不到時（例如被限流）的固定網址
        candidates.append("https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
                          "ffmpeg-master-latest-winarm64-gpl.zip")
    candidates = list(dict.fromkeys(candidates))

    for url in candidates:
        tmp = Path(tempfile.mkdtemp(prefix="ffmpeg_"))
        try:
            arc = download(url, tmp / "ffmpeg.zip")
            got = {}
            with zipfile.ZipFile(arc) as z:
                for name in z.namelist():
                    base = os.path.basename(name).lower()
                    if base in ("ffmpeg.exe", "ffprobe.exe") and base not in got:
                        dst = tmp / base
                        with z.open(name) as fsrc, open(dst, "wb") as fdst:
                            shutil.copyfileobj(fsrc, fdst)
                        got[base] = dst
            if len(got) < 2:
                log("    壓縮檔裡找不到執行檔，換下一個來源")
                continue
            if not all(check_arch(p) for p in got.values()):
                continue
            BIN.mkdir(parents=True, exist_ok=True)
            for base, src in got.items():
                shutil.copy2(src, BIN / base)
            log(f"  [OK] ffmpeg.exe  {ARCH}  ({ff.stat().st_size/1e6:.1f} MB)")
            log(f"  [OK] ffprobe.exe {ARCH}  ({fp.stat().st_size/1e6:.1f} MB)")
            return True
        except Exception as exc:
            log(f"    失敗：{exc}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return False


MANUAL_X64 = """
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

MANUAL_ARM64 = """
------------------------------------------------------------
自動下載失敗時，可以手動放檔案（ARM64 版本，都放到 bin\\ 資料夾）：

1) libmpv-2.dll
   到 https://github.com/zhongfly/mpv-winbuild/releases
   下載 mpv-dev-aarch64-<日期>.7z
   用 7-Zip（https://www.7-zip.org/）解壓，
   把 libmpv-2.dll 複製到  bin\\libmpv-2.dll
   （這個壓縮檔用到較新的格式，Windows 內建的解壓縮可能打不開）

2) ffmpeg.exe 與 ffprobe.exe
   到 https://github.com/BtbN/FFmpeg-Builds/releases
   下載 ffmpeg-master-latest-winarm64-gpl.zip，解壓後在 bin\\ 資料夾裡
   把 ffmpeg.exe 與 ffprobe.exe 複製到  bin\\

放好之後直接跑 run.bat 就可以了。
------------------------------------------------------------
"""


def main() -> int:
    global ARCH, BIN
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="已存在也重新下載")
    ap.add_argument("--arch", choices=("auto", "x64", "arm64"), default="auto",
                    help="要下載哪個架構的版本（預設跟目前的 Python 一樣）")
    ap.add_argument("--bin-dir", type=Path, default=None,
                    help="下載到這個資料夾（預設是專案的 bin\\）")
    args = ap.parse_args()
    if args.arch != "auto":
        ARCH = args.arch
    if args.bin_dir:
        BIN = args.bin_dir.resolve()

    BIN.mkdir(parents=True, exist_ok=True)
    log(f"下載目的地：{BIN}")
    log(f"CPU 架構：{ARCH}\n")

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
    log(MANUAL_ARM64 if ARCH == "arm64" else MANUAL_X64)
    return 1


if __name__ == "__main__":
    sys.exit(main())
