#!/usr/bin/env python
"""Write tests/fixtures/sample_wrapped.json: the card tests' Wrapped, in summary.json's shape.

    .venv/bin/python scripts/make_sample_wrapped.py

Everything in it is INVENTED: the headline numbers (412 h, 87 nights, 19,240 frames, 41 targets, best month August
63 h, a 9-night streak Jul 29 to Aug 6, busiest night Oct 17 with 3 telescopes and 5 targets, 7 full-moon nights,
31% bright Moon), the generic rigs, the hours on a list of well-known objects, and the nights themselves (seeded
pseudo-random nights through the year, built so that they add up to those headlines). It is nobody's observing log.
The README's sample images are drawn from it.
"""
from __future__ import annotations

import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from skywrapped.stats import SKIP_KEYS  # noqa: E402

OUT = ROOT / "tests" / "fixtures" / "sample_wrapped.json"
YEAR, SEED = 2026, 20261122
TOTAL_HOURS, FRAMES, TARGETS = 412, 19240, 41
NIGHTS = {1: 4, 2: 3, 3: 5, 4: 8, 5: 10, 6: 11, 7: 9, 8: 11, 9: 10, 10: 7, 11: 6, 12: 3}           # 87
MONTH_HOURS = {1: 9, 2: 6, 3: 12, 4: 28, 5: 41, 6: 47, 7: 44, 8: 63, 9: 58, 10: 52, 11: 38, 12: 14}  # 412
BEST_MONTH = 8
STREAK = (date(YEAR, 7, 29), date(YEAR, 8, 6))
BUSIEST = date(YEAR, 10, 17)
# nights pinned to a calendar shade the tests check: >= 20 h, < 20, < 12, < 6, < 2 (and Jan 1 left empty)
FIXED = {BUSIEST: 21.6, date(YEAR, 8, 20): 14.2, date(YEAR, 9, 12): 8.4, date(YEAR, 6, 6): 3.7,
         date(YEAR, 6, 9): 0.9}
EMPTY = {date(YEAR, 1, 1), STREAK[0] - timedelta(days=1), STREAK[1] + timedelta(days=1)}

# well-known objects with invented hours; distances are the bundled table's (src/skywrapped/data/distances.csv)
TOPS = [("M42", "M 42", "Orion Nebula", 58.6, 1494), ("M31", "M 31", "Andromeda Galaxy", 44.2, 2511401),
        ("NGC7000", "NGC 7000", "North America Nebula", 37.9, 2639), ("IC1805", "IC 1805", "Heart Nebula", 31.5, 6406),
        ("M45", "M 45", "Pleiades", 26.8, 440), ("M33", "M 33", "Triangulum Galaxy", 21.3, 2853865),
        ("M27", "M 27", "Dumbbell Nebula", 17.4, 1248), ("M51", "M 51", "Whirlpool Galaxy", 14.1, 27397104),
        ("M81", "M 81", "Bode's Galaxy", 11.7, 11921002), ("M101", "M 101", None, 9.6, 22667842)]
RIGS = [("80 mm refractor · ASI2600MC", 158), ('8" SCT · ASI533MC', 104), ("Seestar S50", 77), ("Dwarf 3", 49),
        ("200 mm lens · ASI183MM", 24)]


def _month_days(m: int) -> list[date]:
    d, out = date(YEAR, m, 1), []
    while d.month == m:
        out.append(d)
        d += timedelta(days=1)
    return out


def _longest_run(days: list[date]) -> tuple[int, date, date]:
    best, run, start, prev = (0, None, None), 0, None, None
    for d in sorted(days):
        run, start = (run + 1, start) if prev and d - prev == timedelta(days=1) else (1, d)
        prev = d
        if run > best[0]:
            best = (run, start, d)
    return best


def _nights(rng: random.Random) -> list[date]:
    streak = {STREAK[0] + timedelta(days=i) for i in range((STREAK[1] - STREAK[0]).days + 1)}
    chosen = set(streak) | set(FIXED)
    for m, n in NIGHTS.items():
        have = [d for d in chosen if d.month == m]
        free = [d for d in _month_days(m) if d not in chosen and d not in EMPTY]
        rng.shuffle(free)
        chosen.update(free[:n - len(have)])
    return sorted(chosen)


def _hours(rng: random.Random, days: list[date]) -> dict[date, float]:
    hours: dict[date, float] = {}
    for m, total in MONTH_HOURS.items():
        mine = [d for d in days if d.month == m]
        free = [d for d in mine if d not in FIXED]
        weights = [0.3 + rng.random() ** 1.5 for _ in free]
        left = total - sum(FIXED.get(d, 0.0) for d in mine)
        for d, wgt in zip(free, weights):
            hours[d] = round(left * wgt / sum(weights), 2)
        hours[free[-1]] = round(left - sum(hours[d] for d in free[:-1]), 2)  # the month adds up exactly
        hours.update({d: FIXED[d] for d in mine if d in FIXED})
    return hours


def build(seed: int) -> dict | None:
    rng = random.Random(seed)
    days = _nights(rng)
    hours = _hours(rng, days)
    run = _longest_run(days)
    others = [d for d in days if not STREAK[0] <= d <= STREAK[1]]
    ok = (len(days) == sum(NIGHTS.values()) and run == (9, *STREAK) and _longest_run(others)[0] < 9
          and max(hours, key=hours.get) == BUSIEST and list(hours.values()).count(hours[BUSIEST]) == 1
          and all(0.05 < h for h in hours.values()) and abs(sum(hours.values()) - TOTAL_HOURS) < 1e-6
          and max(MONTH_HOURS, key=MONTH_HOURS.get) == BEST_MONTH)
    if not ok:
        return None
    per = [{"date": d.isoformat(), "hours": hours[d], "telescopes": 3 if d == BUSIEST else 1 + int(rng.random() * 3),
            "targets": 5 if d == BUSIEST else 1 + int(rng.random() * 3), "moon": round(rng.random(), 2)}
           for d in days]
    return {
        "_comment": "Card-test sample: INVENTED numbers, generic rigs and well-known targets with made-up hours, "
                    "over seeded synthetic nights (scripts/make_sample_wrapped.py). Nobody's observing log.",
        "year": YEAR, "partial": False, "first_night": per[0]["date"], "last_night": per[-1]["date"],
        "hours": float(TOTAL_HOURS), "frames": FRAMES, "nights": len(per), "targets": TARGETS, "per_night": per,
        "best_month": {"month": BEST_MONTH, "hours": float(MONTH_HOURS[BEST_MONTH])},
        "longest_streak": {"nights": run[0], "start": STREAK[0].isoformat(), "end": STREAK[1].isoformat()},
        "busiest_night": next(p for p in per if p["date"] == BUSIEST.isoformat()),
        "bright_moon_share": 0.31, "full_moon_nights": 7, "moon_uses_altitude": True,
        "top_targets": [{"key": k, "label": lab, "common_name": c, "hours": h, "frames": round(h * 3600 / 180),
                         "nights": max(1, int(h // 6)), "distance_ly": d} for k, lab, c, h, d in TOPS],
        "setups": [{"label": lab, "hours": float(h), "frames": int(h * 3600 / 120)} for lab, h in RIGS],
        "coldest_sensor_c": None, "from_stacks_only": False, "night_boundaries_estimated": False,
        "skipped": {k: 0 for k in SKIP_KEYS},
    }


def main() -> int:
    for seed in range(SEED, SEED + 1000):
        doc = build(seed)
        if doc:
            text = json.dumps(doc, ensure_ascii=False, indent=1)
            OUT.write_text(text + "\n", encoding="utf-8")
            print(f"seed {seed}: {len(doc['per_night'])} nights, {sum(p['hours'] for p in doc['per_night']):.2f} h")
            return 0
    print("no seed in range met the constraints", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
