"""驗證匯出的起點是否真的零偏移（以及聲音延遲是否正確套用）。

用法：python3 tests/test_cut_accuracy.py
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playcut import exporter as EX
from playcut.ffio import Tools, list_keyframes, probe

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
WORK = Path(tempfile.mkdtemp(prefix="cuttest_"))
SRC = WORK / "source.mp4"

FPS = 25
DUR = 60


def sh(cmd: list[str]) -> str:
    cp = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return cp.stdout.decode("utf-8", "replace")


def make_source():
    vf = (
        "drawtext=fontfile=%s:text='%%{pts\\:hms}  f=%%{n}':fontsize=30:"
        "fontcolor=white:box=1:boxcolor=black@0.7:x=12:y=12" % FONT
    )
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", f"testsrc2=size=640x360:rate={FPS}:duration={DUR}",
        "-f", "lavfi", "-i",
        f"aevalsrc='sin(2*PI*1000*t)*lt(mod(t\\,1)\\,0.06)':s=48000:d={DUR}",
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-g", "125", "-keyint_min", "125", "-sc_threshold", "0",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-ac", "1",
        "-shortest", str(SRC),
    ]
    out = sh(cmd)
    assert SRC.exists(), out


def frame_png(path: str, t: float, dst: Path):
    sh(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{t:.6f}", "-i", path, "-frames:v", "1", str(dst)])


def psnr(a: Path, b: Path) -> float:
    out = sh(["ffmpeg", "-hide_banner", "-i", str(a), "-i", str(b),
              "-lavfi", "psnr", "-f", "null", "-"])
    m = re.search(r"average:(\d+\.?\d*|inf)", out)
    if not m:
        return -1.0
    return 1e9 if m.group(1) == "inf" else float(m.group(1))


def duration(path: str) -> float:
    out = sh(["ffprobe", "-v", "error", "-show_entries", "format=duration",
              "-of", "csv=p=0", path]).strip()
    try:
        return float(out)
    except ValueError:
        return -1.0


def beep_onsets(path: str, limit: int = 4) -> list[float]:
    out = sh(["ffmpeg", "-hide_banner", "-i", path,
              "-af", "silencedetect=n=-35dB:d=0.15", "-f", "null", "-"])
    ends = [float(m) for m in re.findall(r"silence_end: (\d+\.?\d*)", out)]
    starts = [float(m) for m in re.findall(r"silence_start: (-?\d+\.?\d*)", out)]
    onsets = sorted(ends)
    if starts and starts[0] > 0.001:
        onsets = [0.0] + onsets
    return onsets[:limit]


def main():
    print(f"工作目錄: {WORK}")
    print("→ 產生測試影片 (60s / 25fps / 每 5 秒一個關鍵影格)…")
    make_source()
    info = probe(str(SRC))
    print(f"   {info.v_codec} {info.v_width}x{info.v_height} "
          f"{info.v_fps:.3f}fps  audio={info.a_codec} {info.a_sample_rate}Hz")
    kf = list_keyframes(str(SRC), 0, 25)
    print(f"   關鍵影格: {[round(k,3) for k in kf]}")

    # 12.36s = 第 309 格，剛好卡在 10.0 與 15.0 兩個關鍵影格中間
    START, END = 12.36, 20.0
    ref = WORK / "ref.png"
    frame_png(str(SRC), START, ref)
    kf_ref = WORK / "kf_ref.png"
    frame_png(str(SRC), 10.0, kf_ref)

    rows = []
    for mode in (EX.MODE_SMART, EX.MODE_REENCODE, EX.MODE_LOSSLESS):
        out = WORK / f"cut_{mode}.mp4"
        opts = EX.ExportOptions(mode=mode, audio_delay=0.0, apply_audio_delay=False,
                                out_dir=str(WORK))
        runner = EX.Runner()
        import time
        t0 = time.time()
        EX.export_segment(str(SRC), info, EX.Segment(START, END), str(out), opts, runner)
        elapsed = time.time() - t0

        got = WORK / f"first_{mode}.png"
        frame_png(str(out), 0.0, got)
        p_ok = psnr(ref, got)
        p_kf = psnr(kf_ref, got)
        d = duration(str(out))
        size = out.stat().st_size / 1024
        rows.append((mode, p_ok, p_kf, d, elapsed, size))
        print(f"\n[{mode}]  {elapsed:.1f}s  {size:.0f}KB  長度={d:.3f}s (應為 {END-START:.3f}s)")
        print(f"   首格 vs 來源 {START}s  PSNR = {p_ok:.2f} dB   "
              f"{'✅ 精準' if p_ok > 33 else '❌ 偏移'}")
        print(f"   首格 vs 關鍵影格 10.0s PSNR = {p_kf:.2f} dB  "
              f"{'← 偏移到關鍵影格' if p_kf > 33 else ''}")

    print("\n" + "=" * 62)
    print("聲音延遲烘焙測試：來源每整秒有一聲 beep，delay=+0.5s")
    print("  預期輸出的聲音取自來源 11.86s 起 → 第一聲 beep 在 0.14s")
    for mode in (EX.MODE_SMART, EX.MODE_REENCODE):
        out = WORK / f"delay_{mode}.mp4"
        opts = EX.ExportOptions(mode=mode, audio_delay=0.5, apply_audio_delay=True,
                                out_dir=str(WORK))
        EX.export_segment(str(SRC), info, EX.Segment(START, END), str(out),
                          opts, EX.Runner())
        ons = beep_onsets(str(out))
        expect = 0.14
        err = abs(ons[0] - expect) if ons else 99
        print(f"  [{mode}] beep 位置 {[round(o,3) for o in ons]}  "
              f"誤差 {err*1000:.0f} ms  {'✅' if err < 0.06 else '❌'}")

    print("\n" + "=" * 62)
    ok = True
    for mode, p_ok, p_kf, d, el, size in rows:
        if mode in (EX.MODE_SMART, EX.MODE_REENCODE):
            if p_ok < 33:
                ok = False
                print(f"❌ {mode} 起點偏移")
            if abs(d - (END - START)) > 0.12:
                ok = False
                print(f"❌ {mode} 長度不對 ({d})")
    print("全部通過 ✅" if ok else "有測試失敗 ❌")
    print(f"檔案保留在 {WORK}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
