#!/bin/bash
# PlayCut 啟動（macOS）。加上 --debug 會保留終端機並印出 mpv 詳細訊息。
cd "$(dirname "$0")"
VENV=".venv-mac"

if [ ! -x "$VENV/bin/python" ]; then
  echo "[X] 還沒安裝。請先點兩下 setup_mac.command。"
  read -r -p "按 Enter 關閉視窗…" _; exit 1
fi

export PYTHONUTF8=1
if [ "${1:-}" = "--debug" ]; then
  shift
  export PLAYCUT_MPV_LOG=v
  "$VENV/bin/python" -m playcut "$@"
  read -r -p "按 Enter 關閉視窗…" _
else
  # 背景啟動，讓終端機視窗可以直接關掉
  nohup "$VENV/bin/python" -m playcut "$@" >/dev/null 2>&1 &
  disown
  echo "PlayCut 已啟動，可以關掉這個視窗。"
fi
