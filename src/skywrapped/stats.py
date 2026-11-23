"""The year in numbers: every figure on a card comes from one ``Wrapped`` record. With year=None, best_month
aggregates the calendar month across years. Stdlib only.

Counting rules that keep the public numbers honest: only light frames count (calibration and frames whose type
keyword names no light are reported, never added to the hours), duplicates collapse, and a stack is ignored when its target also has sub frames from the same
camera on the same night (those subs are its own); a Seestar or Dwarf stack from any other night counts,
but a desktop stack (AstroWizard, Siril, a master) is ignored whenever its target has sub frames at all.
``to_summary`` carries computed statistics only: no coordinates, paths, or raw OBJECT text.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta

from ._fitsnorm import Frame
from .astro import moon_altitude, moon_illumination
from .catalogue import distance_ly
from .nights import assign_nights
from .targets import group_targets

CALIBRATION = ("dark", "flat", "bias", "darkflat", "calibration")
FOCAL_TOLERANCE = 0.03
BRIGHT_MOON = 0.5
FULL_MOON = 0.9
SESSION_STACKERS = ("seestar", "dwarf")
SKIP_KEYS = ("calibration", "not_light", "type_assumed", "duplicate", "stack_with_subs", "outside_year", "excluded",
             "unreadable", "metadata_file", "no_time")


class NoLightsError(ValueError):
    """No light frame is left to count. ``years``: the years of the nights that do have lights, when only the
    year filter left none (else empty)."""

    def __init__(self, message: str = "no light frames to count", years=()):
        super().__init__(message)
        self.years = tuple(years)


@dataclass
class TargetStat:
    key: str
    label: str
    common_name: str | None
    hours: float
    frames: int
    nights: int
    distance_ly: float | None


@dataclass
class SetupStat:
    label: str  # "<TELESCOP or '<focal> mm'> · <camera minus 'ZWO '>", both cleaned by _fitsnorm.labels
    hours: float
    frames: int


@dataclass
class NightStat:
    date: date
    hours: float
    telescopes: int
    targets: int
    moon: float  # hour-weighted illuminated fraction


@dataclass
class Wrapped:
    year: int | None
    partial: bool
    first_night: date
    last_night: date
    hours: float
    frames: int
    nights: int
    targets: int
    per_night: list[NightStat]
    best_month: tuple[int, float]
    longest_streak: tuple[int, date, date]
    busiest_night: NightStat
    bright_moon_share: float
    full_moon_nights: int
    moon_uses_altitude: bool
    top_targets: list[TargetStat]
    setups: list[SetupStat]
    coldest_sensor_c: float | None
    from_stacks_only: bool
    night_boundaries_estimated: bool
    skipped: dict[str, int]


def _focal_groups(values: list[float]) -> dict[float, int]:
    """Map each distinct focal length to a group id; values within 3% of the group's first (lowest) merge."""
    groups: dict[float, int] = {}
    base: list[float] = []
    for v in sorted(set(values)):
        if base and v <= base[-1] * (1 + FOCAL_TOLERANCE):
            groups[v] = len(base) - 1
        else:
            base.append(v)
            groups[v] = len(base) - 1
    return groups


def _time_key(f: Frame, focal_group):
    """Two files with this key are one exposure (a copy). A stack is never a copy of a sub: a Seestar stack starts
    with its first sub and has the same EXPTIME."""
    t = f.start_utc or f.start_local
    return None if t is None else (f.camera, t.replace(microsecond=0), f.exposure_s, f.is_stack, focal_group, f.filter)


def compute_wrapped(frames: list[Frame], *, year: int | None, default_offset_h: float, today: date,
                    skipped: dict[str, int] | None = None) -> Wrapped:
    skip = {k: 0 for k in SKIP_KEYS}
    for k, v in (skipped or {}).items():
        skip[k] = skip.get(k, 0) + v

    # 1. lights only; unknown frames count but are flagged; duplicates collapse
    lights: list[Frame] = []
    seen = set()
    dup_groups = _focal_groups([f.focal_mm for f in frames if f.focal_mm is not None and f.frame_type not in CALIBRATION])
    for f in frames:
        if f.frame_type in CALIBRATION:
            skip["calibration"] += 1
            continue
        if f.frame_type == "other":  # a type keyword that names no light (SNAPSHOT, FOCUS, TEST...)
            skip["not_light"] += 1
            continue
        key = _time_key(f, dup_groups.get(f.focal_mm))
        if key is not None:
            if key in seen:
                skip["duplicate"] += 1
                continue
            seen.add(key)
        lights.append(f)

    # 2. nights; frames with no time cannot be placed
    info = assign_nights(lights, default_offset_h)
    placed = []  # (frame, night, utc)
    for f, n, u in zip(lights, info.nights, info.utc):
        if n is None:
            skip["no_time"] += 1
        else:
            placed.append((f, n, u))

    # 3. targets over every placed frame, so a stack is judged against all of its sub frames
    as_light = [replace(f, frame_type="light") if f.frame_type != "light" else f for f, _, _ in placed]
    targets = group_targets(as_light)
    target_of = {}
    for ti, t in enumerate(targets):
        for i in t.frame_idx:
            target_of[i] = ti
    # A session stacker (Seestar, Dwarf) stacks the night it shoots, so its stack is dropped only where its own
    # subs are: same target, same camera, same night (a stack without a camera matches any camera). Any other
    # stack (AstroWizard, Siril, a master) is built from many nights and is dropped when its target has subs at all.
    sub_nights = {(target_of.get(i), f.camera, n) for i, (f, n, _) in enumerate(placed) if not f.is_stack}
    sub_targets = {t for t, _, _ in sub_nights}
    night_targets = {(t, n) for t, _, n in sub_nights}

    def has_subs(ti, f, n) -> bool:
        if f.vendor not in SESSION_STACKERS:
            return ti in sub_targets
        return (ti, n) in night_targets if f.camera is None else (ti, f.camera, n) in sub_nights
    kept = []  # (frame, night, utc, target index)
    other_years: set[int] = set()
    for i, (f, n, u) in enumerate(placed):
        ti = target_of.get(i)
        if f.is_stack and has_subs(ti, f, n):
            skip["stack_with_subs"] += 1
        elif year is not None and n.year != year:
            skip["outside_year"] += 1
            other_years.add(n.year)
        else:
            kept.append((f, n, u, ti))
    if not kept:
        raise NoLightsError(years=sorted(other_years))
    skip["type_assumed"] += sum(1 for f, *_ in kept if f.frame_type == "unknown")

    # 4. per-frame weights
    def hrs(f: Frame) -> float:
        return (f.integration_s if f.is_stack else f.exposure_s) / 3600
    def cnt(f: Frame) -> int:
        return max(1, f.sub_count) if f.is_stack else 1

    groups = _focal_groups([f.focal_mm for f, *_ in kept if f.focal_mm is not None])
    def group_of(f: Frame):
        return groups.get(f.focal_mm) if f.focal_mm is not None else None

    total_h = sum(hrs(f) for f, *_ in kept)
    total_frames = sum(cnt(f) for f, *_ in kept)

    # moon, hour-weighted, at mid-exposure
    moon_of = []
    bright_h = 0.0
    for f, n, u, ti in kept:
        mid = u + timedelta(seconds=f.exposure_s / 2) if u else None
        ill = moon_illumination(mid)
        moon_of.append(ill)
        up = True
        if f.site:
            up = moon_altitude(mid, f.site[0], f.site[1]) > 0
        if ill > BRIGHT_MOON and up:
            bright_h += hrs(f)

    by_night: dict[date, list[int]] = {}
    for k, (f, n, u, ti) in enumerate(kept):
        by_night.setdefault(n, []).append(k)
    per_night = []
    for n in sorted(by_night):
        ks = by_night[n]
        h = sum(hrs(kept[k][0]) for k in ks)
        moon = sum(moon_of[k] * hrs(kept[k][0]) for k in ks) / h if h else 0.0
        per_night.append(NightStat(n, h, len({group_of(kept[k][0]) for k in ks} - {None}),
                                   len({kept[k][3] for k in ks} - {None}), moon))

    month_h: dict[int, float] = {}
    for ns in per_night:
        month_h[ns.date.month] = month_h.get(ns.date.month, 0.0) + ns.hours
    best_month = max(sorted(month_h.items()), key=lambda kv: kv[1])

    best = (0, None, None)
    run_start = prev = None
    run = 0
    for ns in per_night:
        if prev is not None and ns.date - prev == timedelta(days=1):
            run += 1
        else:
            run, run_start = 1, ns.date
        prev = ns.date
        if run > best[0]:
            best = (run, run_start, ns.date)

    busiest = max(per_night, key=lambda ns: ns.hours)  # first on ties

    # targets: one entry per Target object
    t_stats = []
    for ti, t in enumerate(targets):
        ks = [k for k, row in enumerate(kept) if row[3] == ti]
        if not ks:
            continue
        t_stats.append(TargetStat(t.key, t.label, t.common_name, sum(hrs(kept[k][0]) for k in ks),
                                  sum(cnt(kept[k][0]) for k in ks), len({kept[k][1] for k in ks}),
                                  distance_ly(t.key)))
    n_targets = len(t_stats)
    t_stats.sort(key=lambda s: -s.hours)

    # setups: (camera, focal group)
    s_acc: dict[tuple, list] = {}
    for f, *_ in kept:
        e = s_acc.setdefault((f.camera, group_of(f)), [0.0, 0, {}, []])
        e[0] += hrs(f)
        e[1] += cnt(f)
        if f.telescope:
            e[2][f.telescope] = e[2].get(f.telescope, 0) + 1
        if f.focal_mm is not None:
            e[3].append(f.focal_mm)
    setups = []
    for (cam, _g), (h, c, tels, focals) in s_acc.items():
        if tels:
            scope = max(sorted(tels), key=lambda k: tels[k])
        elif focals:
            scope = f"{round(sum(focals) / len(focals))} mm"
        else:
            scope = "Unknown scope"
        cam_label = (cam[4:] if cam.upper().startswith("ZWO ") else cam) if cam else None
        if cam_label and cam_label.casefold() != scope.casefold():  # "Dwarf 3 · Dwarf 3" is just "Dwarf 3"
            setups.append(SetupStat(f"{scope} · {cam_label}", h, c))
        else:
            setups.append(SetupStat(scope, h, c))
    setups.sort(key=lambda s: -s.hours)

    temps = [f.sensor_c for f, *_ in kept if f.sensor_c is not None]
    return Wrapped(
        year=year, partial=(year is not None and year == today.year),
        first_night=per_night[0].date, last_night=per_night[-1].date,
        hours=total_h, frames=total_frames, nights=len(per_night), targets=n_targets,
        per_night=per_night, best_month=best_month, longest_streak=best, busiest_night=busiest,
        bright_moon_share=bright_h / total_h if total_h else 0.0,
        full_moon_nights=sum(1 for ns in per_night if ns.moon >= FULL_MOON),
        moon_uses_altitude=any(f.site for f, *_ in kept),
        top_targets=t_stats, setups=setups,
        coldest_sensor_c=min(temps) if temps else None,
        from_stacks_only=all(f.is_stack for f, *_ in kept),
        night_boundaries_estimated=info.estimated, skipped=skip,
    )


def _night(n: NightStat) -> dict:
    return {"date": n.date.isoformat(), "hours": n.hours, "telescopes": n.telescopes, "targets": n.targets,
            "moon": n.moon}


def to_summary(w: Wrapped) -> dict:
    """JSON-safe computed statistics. Never includes site coordinates, paths, or raw OBJECT text."""
    streak = w.longest_streak
    return {
        "year": w.year, "partial": w.partial,
        "first_night": w.first_night.isoformat(), "last_night": w.last_night.isoformat(),
        "hours": w.hours, "frames": w.frames, "nights": w.nights, "targets": w.targets,
        "per_night": [_night(n) for n in w.per_night],
        "best_month": {"month": w.best_month[0], "hours": w.best_month[1]},
        "longest_streak": {"nights": streak[0], "start": streak[1].isoformat(), "end": streak[2].isoformat()},
        "busiest_night": _night(w.busiest_night),
        "bright_moon_share": w.bright_moon_share, "full_moon_nights": w.full_moon_nights,
        "moon_uses_altitude": w.moon_uses_altitude,
        "top_targets": [{"key": t.key, "label": t.label, "common_name": t.common_name, "hours": t.hours,
                         "frames": t.frames, "nights": t.nights, "distance_ly": t.distance_ly}
                        for t in w.top_targets],
        "setups": [{"label": s.label, "hours": s.hours, "frames": s.frames} for s in w.setups],
        "coldest_sensor_c": w.coldest_sensor_c, "from_stacks_only": w.from_stacks_only,
        "night_boundaries_estimated": w.night_boundaries_estimated, "skipped": dict(w.skipped),
    }
