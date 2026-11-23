"""Assign each frame to an observing night. Stdlib only."""
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from ._fitsnorm import Frame

_NOON = timedelta(hours=12)


@dataclass
class NightInfo:
    nights: list  # list[date | None]
    utc: list  # list[datetime | None]
    estimated: bool


def _assign(frames, default_offset_h):
    nights, utcs, default_idx = [], [], []
    for i, f in enumerate(frames):
        if f.start_local is not None:
            off = f.site[1] / 15 if f.site else default_offset_h
            nights.append((f.start_local - _NOON).date())
            utcs.append(f.start_local - timedelta(hours=off))
        elif f.start_utc is not None:
            if f.site:
                off = f.site[1] / 15
            else:
                off = default_offset_h
                default_idx.append(i)
            nights.append((f.start_utc + timedelta(hours=off) - _NOON).date())
            utcs.append(f.start_utc)
        else:
            nights.append(None)
            utcs.append(None)
    return nights, utcs, default_idx


def _hour(t: datetime) -> float:
    return t.hour + t.minute / 60 + t.second / 3600


def assign_nights(frames: list, default_offset_h: float) -> NightInfo:
    nights, utcs, idx = _assign(frames, default_offset_h)
    if idx:
        day = sum(
            1 for i in idx
            if 8 <= _hour(utcs[i] + timedelta(hours=default_offset_h)) < 16
        )
        if day / len(idx) > 0.5:
            s = sum(math.sin(math.radians(_hour(utcs[i]) * 15)) for i in idx)
            c = sum(math.cos(math.radians(_hour(utcs[i]) * 15)) for i in idx)
            mean_h = (math.degrees(math.atan2(s, c)) / 15) % 24
            off = round(((0.5 - mean_h) % 24) * 2) / 2
            while off >= 14:
                off -= 24
            while off < -12:
                off += 24
            nights, utcs, _ = _assign(frames, off)
            return NightInfo(nights, utcs, True)
    return NightInfo(nights, utcs, False)
