"""從舊名稱 FlagPlayer 升級上來的相容處理。

• 環境變數：舊的 FLAGPLAYER_* 仍然有效（沒設定對應的 PLAYCUT_* 時才套用）。
• 設定：第一次以 PlayCut 啟動時，把 FlagPlayer 的 QSettings 整份複製過來。
"""
from __future__ import annotations

import os

OLD_NAME = "FlagPlayer"
NEW_NAME = "PlayCut"
_MIGRATED_KEY = "_migrated_from_flagplayer"


def apply_legacy_env() -> None:
    for key, value in list(os.environ.items()):
        if key.startswith("FLAGPLAYER_"):
            os.environ.setdefault("PLAYCUT_" + key[len("FLAGPLAYER_"):], value)


def migrate_settings() -> None:
    """把舊設定搬到新名稱底下（只做一次，舊設定保留不刪）。失敗就算了，不影響啟動。"""
    try:
        from PySide6.QtCore import QSettings
        new = QSettings(NEW_NAME, NEW_NAME)
        if new.value(_MIGRATED_KEY, False, type=bool):
            return
        old = QSettings(OLD_NAME, OLD_NAME)
        if not new.allKeys():
            for k in old.allKeys():
                new.setValue(k, old.value(k))
        new.setValue(_MIGRATED_KEY, True)
        new.sync()
    except Exception:
        pass
