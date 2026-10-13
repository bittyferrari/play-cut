"""列出程式裡所有 tr() / N_() 的字串，並檢查各語言翻譯表有沒有漏。

    python tools/i18n_keys.py          # 列出缺少的翻譯
    python tools/i18n_keys.py --dump   # 印出全部 key
"""
from __future__ import annotations

import ast
import string
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "playcut"
sys.path.insert(0, str(ROOT))

FUNCS = {"tr", "N_", "tr_for"}


def collect_keys() -> dict[str, list[str]]:
    keys: dict[str, list[str]] = {}
    for py in sorted(PKG.rglob("*.py")):
        if "locales" in py.parts:
            continue
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id in FUNCS and node.args):
                continue
            arg = node.args[1] if node.func.id == "tr_for" and len(node.args) > 1 else node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                keys.setdefault(arg.value, []).append(f"{py.name}:{node.lineno}")
    return keys


def fields(s: str) -> set[str]:
    return {f for _, f, _, _ in string.Formatter().parse(s) if f}


def check() -> int:
    from playcut import i18n
    keys = collect_keys()
    bad = 0
    for lang, table in i18n._TABLES.items():
        if lang == i18n.SOURCE_LANG:
            continue
        missing = [k for k in keys if k not in table]
        extra = [k for k in table if k not in keys]
        wrong = [k for k in keys if k in table and fields(k) != fields(table[k])]
        for k in missing:
            print(f"[{lang}] 缺少: {k!r}  ({', '.join(keys[k])})")
        for k in wrong:
            print(f"[{lang}] 參數不一致: {k!r} -> {table[k]!r}")
        for k in extra:
            print(f"[{lang}] 多餘（程式已不用）: {k!r}")
        bad += len(missing) + len(wrong)
        print(f"[{lang}] {len(keys) - len(missing)}/{len(keys)} 已翻譯")
    return 1 if bad else 0


if __name__ == "__main__":
    if "--dump" in sys.argv:
        for k in collect_keys():
            print(repr(k))
    else:
        sys.exit(check())
