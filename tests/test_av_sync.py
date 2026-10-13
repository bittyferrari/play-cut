"""影音同步測試：來源每整秒有一次白色閃光 + 同時的嗶聲。

剪輯後量測輸出裡閃光與嗶聲的時間，兩者差距就是影音不同步的量。
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playcut import exporter as EX
from playcut.ffio import probe

WORK = Path(tempfile.mkdtemp(prefix="synctest_"))
SRC = WORK / "sync_src.mp4"
DUR = 40


def sh(cmd):
    return subprocess.run(cmd, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT).stdout.decode("utf-8", "replace")


def make_source():
    sh([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", f"color=c=black:s=320x180:r=25:d={DUR}",
        "-f", "lavfi", "-i",
        f"aevalsrc='sin(2*PI*1000*t)*lt(mod(t\\,1)\\,0.08)':s=48000:d={DUR}",
        "-vf", "drawbox=x=0:y=0:w=iw:h=ih:color=white@1:t=fill:"
               "enable='lt(mod(t\\,1)\\,0.08)'",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-g", "125", "-keyint_min", "125", "-sc_threshold", "0",
        "-bf", "3", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-ac", "2",
        "-shortest", str(SRC),
    ])
    assert SRC.exists()


def flash_times(path, limit=5):
    out = sh(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path),
              "-vf", "signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-",
              "-f", "null", "-"])
    times, cur = [], None
    prev_bright = False
    for line in out.splitlines():
        m = re.match(r"frame:\s*\d+\s+pts:\s*\d+\s+pts_time:(\S+)", line)
        if m:
            cur = float(m.group(1))
            continue
        m = re.search(r"YAVG=(\d+\.?\d*)", line)
        if m and cur is not None:
            bright = float(m.group(1)) > 128
            if bright and not prev_bright:
                times.append(cur)
            prev_bright = bright
    return times[:limit]


def beep_times(path, limit=5):
    out = sh(["ffmpeg", "-hide_banner", "-i", str(path),
              "-af", "silencedetect=n=-35dB:d=0.2", "-f", "null", "-"])
    ends = sorted(float(x) for x in re.findall(r"silence_end: (\d+\.?\d*)", out))
    starts = sorted(float(x) for x in re.findall(r"silence_start: (-?\d+\.?\d*)", out))
    if starts and starts[0] > 0.01:
        ends = [0.0] + ends
    return ends[:limit]


def report(tag, path, expect_first):
    f = flash_times(path)
    b = beep_times(path)
    print(f"\n[{tag}]")
    print(f"   閃光 {[round(x,3) for x in f]}")
    print(f"   嗶聲 {[round(x,3) for x in b]}")
    ok = True
    if not f or not b:
        print("   ❌ 量測失敗")
        return False
    start_err = f[0] - expect_first
    print(f"   起點誤差 {start_err*1000:+.0f} ms  "
          f"{'✅' if abs(start_err) < 0.045 else '❌'}")
    ok &= abs(start_err) < 0.045
    n = min(len(f), len(b))
    desyncs = [(f[i] - b[i]) * 1000 for i in range(n)]
    worst = max(desyncs, key=abs)
    print(f"   影音差 {[round(d) for d in desyncs]} ms  最大 {worst:+.0f} ms  "
          f"{'✅' if abs(worst) < 45 else '❌'}")
    ok &= abs(worst) < 45
    # 相鄰閃光間距應該都是 1.000s（接合處不可以有跳動）
    gaps = [round(f[i+1] - f[i], 3) for i in range(len(f) - 1)]
    bad = [g for g in gaps if abs(g - 1.0) > 0.045]
    print(f"   閃光間距 {gaps}  {'✅' if not bad else '❌ 接合處有跳動'}")
    ok &= not bad
    return ok


def main():
    print(f"工作目錄 {WORK}")
    make_source()
    info = probe(str(SRC))
    print("來源就緒（每秒閃光+嗶聲同時發生，關鍵影格每 5 秒，含 B-frame）")
    print("原始檔本身的量測基準：")
    report("source @12.36 參考", SRC, 0)  # 只看影音差與間距

    START, END = 12.36, 20.0
    expect_first = 13.0 - START  # 0.64
    all_ok = True
    for mode in (EX.MODE_SMART, EX.MODE_REENCODE):
        out = WORK / f"sync_{mode}.mkv"
        EX.export_segment(str(SRC), info, EX.Segment(START, END), str(out),
                          EX.ExportOptions(mode=mode), EX.Runner())
        all_ok &= report(mode, out, expect_first)
    print("\n" + ("全部通過 ✅" if all_ok else "有問題 ❌"))
    print(WORK)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
