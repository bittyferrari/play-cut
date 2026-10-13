"""旗標（flag）與片段（segment）資料模型，以及專案檔存取。"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from .exporter import Segment

ROLE_IN = "in"
ROLE_OUT = "out"
ROLE_AUTO = "auto"


@dataclass
class Marker:
    t: float
    label: str = ""
    role: str = ROLE_AUTO      # auto = 依序自動配對成 起點/終點
    color: str = ""

    def to_dict(self) -> dict:
        return {"t": round(self.t, 6), "label": self.label, "role": self.role}

    @staticmethod
    def from_dict(d: dict) -> "Marker":
        return Marker(float(d.get("t", 0.0)), d.get("label", "") or "",
                      d.get("role", ROLE_AUTO) or ROLE_AUTO)


class MarkerList:
    """按時間排序的旗標集合，可推導出要匯出的片段。

    預設行為就是使用者要的：第 1 個旗標 = 起點，第 2 個 = 終點，
    第 3 個 = 起點，第 4 個 = 終點… 依此類推。
    個別旗標可以被強制指定成 in / out。
    """

    def __init__(self):
        self.items: list[Marker] = []

    # ---- 基本操作 ----
    def add(self, t: float, label: str = "", role: str = ROLE_AUTO) -> Marker:
        m = Marker(float(t), label, role)
        self.items.append(m)
        self.sort()
        return m

    def remove(self, index: int) -> None:
        if 0 <= index < len(self.items):
            del self.items[index]

    def clear(self) -> None:
        self.items.clear()

    def sort(self) -> None:
        self.items.sort(key=lambda m: m.t)

    def __len__(self) -> int:
        return len(self.items)

    def __iter__(self):
        return iter(self.items)

    def __getitem__(self, i) -> Marker:
        return self.items[i]

    def index_of(self, m: Marker) -> int:
        return self.items.index(m)

    def nearest(self, t: float, max_dist: float = 1e9) -> Optional[int]:
        best, bd = None, max_dist
        for i, m in enumerate(self.items):
            d = abs(m.t - t)
            if d < bd:
                best, bd = i, d
        return best

    def next_after(self, t: float, eps: float = 1e-4) -> Optional[float]:
        for m in self.items:
            if m.t > t + eps:
                return m.t
        return None

    def prev_before(self, t: float, eps: float = 1e-4) -> Optional[float]:
        prev = None
        for m in self.items:
            if m.t < t - eps:
                prev = m.t
            else:
                break
        return prev

    # ---- 角色推導 ----
    def roles(self) -> list[str]:
        """回傳每個旗標實際扮演的角色（in / out）。"""
        out: list[str] = []
        expect_in = True
        for m in self.items:
            if m.role in (ROLE_IN, ROLE_OUT):
                r = m.role
            else:
                r = ROLE_IN if expect_in else ROLE_OUT
            out.append(r)
            expect_in = (r == ROLE_OUT)
        return out

    def segments(self, duration: float = 0.0) -> list[Segment]:
        """把旗標配成片段。最後落單的起點會延伸到影片結尾。"""
        segs: list[Segment] = []
        roles = self.roles()
        pending: Optional[Marker] = None
        for m, r in zip(self.items, roles):
            if r == ROLE_IN:
                pending = m
            else:
                if pending is not None and m.t > pending.t:
                    segs.append(Segment(pending.t, m.t,
                                        pending.label or m.label or ""))
                pending = None
        if pending is not None and duration > pending.t + 1e-3:
            segs.append(Segment(pending.t, duration, pending.label or ""))
        return segs

    # ---- 專案檔 ----
    @staticmethod
    def project_path(video_path: str) -> Path:
        p = Path(video_path)
        return p.with_suffix(p.suffix + ".playcut.json")

    @staticmethod
    def legacy_project_path(video_path: str) -> Path:
        """改名前（FlagPlayer）用的專案檔名，只讀不寫。"""
        p = Path(video_path)
        return p.with_suffix(p.suffix + ".flags.json")

    def save(self, video_path: str, extra: Optional[dict] = None) -> Path:
        path = self.project_path(video_path)
        data = {
            "version": 1,
            "app": "PlayCut",
            "video": os.path.basename(video_path),
            "markers": [m.to_dict() for m in self.items],
        }
        if extra:
            data.update(extra)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                        encoding="utf-8")
        return path

    def load(self, video_path: str) -> dict:
        path = self.project_path(video_path)
        if not path.exists():
            path = self.legacy_project_path(video_path)
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        self.items = [Marker.from_dict(d) for d in data.get("markers", [])]
        self.sort()
        return data

    def load_from(self, json_path: str) -> dict:
        data = json.loads(Path(json_path).read_text(encoding="utf-8"))
        self.items = [Marker.from_dict(d) for d in data.get("markers", [])]
        self.sort()
        return data

    # ---- 其他格式 ----
    def to_csv(self) -> str:
        lines = ["index,role,time_seconds,timecode,label"]
        from .ffio import fmt_time
        for i, (m, r) in enumerate(zip(self.items, self.roles()), 1):
            lines.append(f'{i},{r},{m.t:.3f},{fmt_time(m.t)},"{m.label}"')
        return "\n".join(lines)
