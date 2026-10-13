#!/bin/bash
# ---------------------------------------------------------------
#  PlayCut setup (macOS)
#  在 Finder 點兩下即可執行（會開一個「終端機」視窗）。
#  需要：Homebrew（https://brew.sh）與 Python 3.9 以上。
# ---------------------------------------------------------------
set -u
cd "$(dirname "$0")"

VENV=".venv-mac"

pause_exit() { echo; read -r -p "按 Enter 關閉視窗…" _; exit "${1:-0}"; }

echo
echo "============================================================"
echo "   PlayCut  setup  (macOS)"
echo "============================================================"
echo

# ---- Homebrew ---------------------------------------------------
BREW=""
for c in brew /opt/homebrew/bin/brew /usr/local/bin/brew; do
  if command -v "$c" >/dev/null 2>&1; then BREW="$(command -v "$c")"; break; fi
done
if [ -z "$BREW" ]; then
  echo "[X] 找不到 Homebrew。請先在「終端機」貼上這行安裝："
  echo
  echo '    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
  echo
  echo "    裝好後再點兩下 setup_mac.command。"
  pause_exit 1
fi
eval "$("$BREW" shellenv)"

# ---- libmpv + ffmpeg -------------------------------------------
echo "[1/3] 安裝 mpv（播放核心）與 ffmpeg（剪輯核心）…"
echo "      第一次會花幾分鐘。"
echo
"$BREW" install mpv ffmpeg || { echo "[X] brew install 失敗。"; pause_exit 1; }
echo

# ---- Python -----------------------------------------------------
PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$c" >/dev/null 2>&1 && \
     "$c" -c 'import sys;sys.exit(0 if sys.version_info>=(3,9) else 1)' 2>/dev/null; then
    PY="$(command -v "$c")"; break
  fi
done
if [ -z "$PY" ]; then
  echo "[!] 找不到 Python 3.9 以上，用 Homebrew 安裝 python@3.12 …"
  "$BREW" install python@3.12 || { echo "[X] 安裝 Python 失敗。"; pause_exit 1; }
  PY="$("$BREW" --prefix)/bin/python3.12"
fi
echo "[2/3] 使用 $("$PY" --version) ($PY)"
echo

# ---- virtual environment ---------------------------------------
echo "[3/3] 建立獨立環境並安裝套件…"
if [ ! -x "$VENV/bin/python" ]; then
  "$PY" -m venv "$VENV" || { echo "[X] 建立 $VENV 失敗。"; pause_exit 1; }
fi
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install -r requirements.txt || { echo "[X] 套件安裝失敗，請檢查網路。"; pause_exit 1; }

echo
echo "============================================================"
echo "   完成！點兩下  run_mac.command  啟動 PlayCut。"
echo "   （build_mac.command 可以打包成 PlayCut.app）"
echo "============================================================"
pause_exit 0
