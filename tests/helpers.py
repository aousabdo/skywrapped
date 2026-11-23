"""Test helpers shared by several test modules."""
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

from skywrapped._fitsnorm import Frame, read_header, to_frame

_T0 = datetime(2026, 9, 6, 3, 0, 0)
_counter = [0]


def fr(ra=None, dec=None, fov=(3.0, 2.0), hint=None, frame_type="light", exposure_s=300.0, start=None,
       t=None, night=None, stack=None, **kw):
    """A Frame with sensible defaults; successive calls get successive start times.

    ``t``: start = fixed base + t seconds. ``night=(y, m, d)``: an evening UTC start on that date, so the
    frame lands on that night with default_offset_h=0. ``stack=N``: an N-sub stack (integration N x exposure).
    """
    _counter[0] += 1
    if start is None:
        if t is not None:
            start = _T0 + timedelta(seconds=t)
        elif night is not None:
            start = datetime(*night, 20, 0, 0) + timedelta(seconds=_counter[0] % 7200)
        else:
            start = _T0 + timedelta(seconds=exposure_s * _counter[0])
    if stack:
        kw.setdefault("is_stack", True)
        kw.setdefault("sub_count", stack)
        kw.setdefault("integration_s", exposure_s * stack)
    base = dict(
        path=f"Light_{_counter[0]:05d}.fit", vendor="asiair", frame_type=frame_type, is_stack=False, sub_count=1,
        exposure_s=exposure_s, integration_s=exposure_s, start_utc=start, start_local=None, object_hint=hint,
        ra_deg=ra, dec_deg=dec, fov_deg=fov if ra is not None else None, focal_mm=264.0, camera=None,
        telescope=None, filter=None, gain=100.0, iso=None, sensor_c=None, site=None,
    )
    base.update(kw)
    return Frame(**base)


_HEADERS = Path(__file__).parent / "fixtures" / "headers"
LIGHT_FIXTURES = ["asiair_2600air", "asiair_duo_awstack", "asiair_4400", "asiair_6200mm", "origin_678c", "origin_178"]


def cw(frames, *, year=None, default_offset_h=0.0, today=None, skipped=None):
    """compute_wrapped with test defaults."""
    from datetime import date

    from skywrapped.stats import compute_wrapped
    return compute_wrapped(frames, year=year, default_offset_h=default_offset_h,
                           today=today or date(2026, 12, 1), skipped=skipped)


def frames_from_fixtures(path_prefix="", hint=None, names=LIGHT_FIXTURES):
    """Real normalised frames from the header fixtures (location cards are sentinels), with a path prefix and
    optionally a replaced OBJECT hint."""
    out = []
    for n in names:
        values, comments = read_header((_HEADERS / f"{n}.hdr").read_bytes())
        f = to_frame(values, comments, f"{path_prefix}Light_{n}.fit")
        out.append(replace(f, object_hint=hint) if hint is not None else f)
    return out


def put(path, data: bytes):
    """Write data to path, creating parent folders."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def grow_sparse(path, size: int):
    """Extend a file to ``size`` bytes without writing the data (a sparse file)."""
    with open(path, "r+b") as fh:
        fh.truncate(size)


def reads_during(fn, monkeypatch):
    """Run fn(); return (bytes returned by reads, list of sizes requested) for files skywrapped.scan opened."""
    import builtins

    from skywrapped import scan
    returned = [0]
    requested = []
    real_open = builtins.open

    class _Counting:
        def __init__(self, fh):
            self._fh = fh

        def read(self, size=-1):
            requested.append(size)
            data = self._fh.read(size)
            returned[0] += len(data)
            return data

        def __enter__(self):
            self._fh.__enter__()
            return self

        def __exit__(self, *a):
            return self._fh.__exit__(*a)

        def __getattr__(self, name):
            return getattr(self._fh, name)

    monkeypatch.setattr(scan, "open", lambda *a, **k: _Counting(real_open(*a, **k)), raising=False)
    fn()
    return returned[0], requested


def bytes_read_during(fn, monkeypatch) -> int:
    """Run fn() and return how many bytes skywrapped.scan read from files it opened."""
    return reads_during(fn, monkeypatch)[0]


_SAMPLE = Path(__file__).parent / "fixtures" / "sample_wrapped.json"


def sample(*, distances=None, partial=False, from_stacks_only=False, top_label=None, year="keep", setups=None):
    """A Wrapped holding the invented sample (tests/fixtures/sample_wrapped.json, summary.json's shape).

    ``distances=k`` keeps a distance on only the first k distanced top targets; ``top_label`` replaces the top
    target's label and common name; ``setups=k`` keeps the first k setups; ``year=None`` makes it all-time.
    """
    import json
    from datetime import date

    from skywrapped.stats import NightStat, SetupStat, TargetStat, Wrapped
    d = json.loads(_SAMPLE.read_text(encoding="utf-8"))
    day = date.fromisoformat

    def night(n):
        return NightStat(day(n["date"]), n["hours"], n["telescopes"], n["targets"], n["moon"])

    tops = [TargetStat(t["key"], t["label"], t["common_name"], t["hours"], t["frames"], t["nights"], t["distance_ly"])
            for t in d["top_targets"]]
    if distances is not None:
        kept = 0
        for t in tops:
            if t.distance_ly is not None:
                kept += 1
                if kept > distances:
                    t.distance_ly = None
    if top_label is not None:
        tops[0].label = tops[0].common_name = top_label
    gear = [SetupStat(s["label"], s["hours"], s["frames"]) for s in d["setups"]]
    streak = d["longest_streak"]
    return Wrapped(
        year=d["year"] if year == "keep" else year, partial=partial,
        first_night=day(d["first_night"]), last_night=day(d["last_night"]),
        hours=d["hours"], frames=d["frames"], nights=d["nights"], targets=d["targets"],
        per_night=[night(n) for n in d["per_night"]],
        best_month=(d["best_month"]["month"], d["best_month"]["hours"]),
        longest_streak=(streak["nights"], day(streak["start"]), day(streak["end"])),
        busiest_night=night(d["busiest_night"]), bright_moon_share=d["bright_moon_share"],
        full_moon_nights=d["full_moon_nights"], moon_uses_altitude=d["moon_uses_altitude"],
        top_targets=tops, setups=gear if setups is None else gear[:setups],
        coldest_sensor_c=d["coldest_sensor_c"], from_stacks_only=from_stacks_only,
        night_boundaries_estimated=d["night_boundaries_estimated"], skipped=dict(d["skipped"]),
    )
