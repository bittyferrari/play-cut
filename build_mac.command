#!/bin/bash
# ---------------------------------------------------------------
#  打包成 dist/PlayCut.app（macOS）
#  必須在 Mac 上執行；成品只能在同架構（Apple Silicon / Intel）的 Mac 上跑。
# ---------------------------------------------------------------
set -eu
cd "$(dirname "$0")"
VENV=".venv-mac"
pause_exit() { echo; read -r -p "按 Enter 關閉視窗…" _; exit "${1:-0}"; }
trap 'echo; echo "[X] 打包失敗。"; pause_exit 1' ERR

if [ ! -x "$VENV/bin/python" ]; then
  echo "[X] 請先執行 setup_mac.command。"; pause_exit 1
fi
for c in /opt/homebrew/bin/brew /usr/local/bin/brew; do
  [ -x "$c" ] && eval "$("$c" shellenv)" && break
done

echo "安裝 PyInstaller…"
"$VENV/bin/python" -m pip install --upgrade pyinstaller

# ---- 產生 .icns 圖示 ---------------------------------------------
ICNS="build/mac/PlayCut.icns"
if [ ! -f "$ICNS" ]; then
  echo "產生 App 圖示…"
  SET="build/mac/PlayCut.iconset"
  rm -rf "$SET"; mkdir -p "$SET"
  SRC="playcut/resources/icon.png"
  for s in 16 32 128 256 512; do
    sips -z $s $s "$SRC" --out "$SET/icon_${s}x${s}.png" >/dev/null
    d=$((s * 2))
    sips -z $d $d "$SRC" --out "$SET/icon_${s}x${s}@2x.png" >/dev/null
  done
  iconutil -c icns "$SET" -o "$ICNS" || echo "[!] 圖示產生失敗，改用預設圖示。"
fi

echo
echo "打包中（需要幾分鐘）…"
"$VENV/bin/python" -m PyInstaller --noconfirm --clean \
  --workpath build/mac --distpath dist \
  packaging/PlayCut-mac.spec

# ad-hoc 簽章：Apple Silicon 上沒簽章的程式完全不能執行
codesign --force --deep --sign - dist/PlayCut.app

echo
echo "壓縮成 dist/PlayCut-mac.zip …"
rm -f dist/PlayCut-mac.zip
ditto -c -k --keepParent dist/PlayCut.app dist/PlayCut-mac.zip

echo
echo "============================================================"
echo "   完成：dist/PlayCut.app"
echo "         dist/PlayCut-mac.zip（傳給別台 Mac 用這個）"
echo
echo "   別台 Mac 第一次開啟時會被 Gatekeeper 擋下："
echo "   在 App 上按右鍵 → 打開 → 再按一次「打開」即可。"
echo "   （macOS 15 以後：系統設定 → 隱私權與安全性 → 仍要打開）"
echo "============================================================"
pause_exit 0
