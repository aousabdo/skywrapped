"""The six portrait cards and the landscape poster, ported from the approved mockup (mockup-cards-v1.html).

Every word on a card comes from a ``Wrapped`` record: target names are ``TargetStat.label`` / ``common_name``
and gear names are ``SetupStat.label``, nothing else from the frames. Stdlib only.
"""
from __future__ import annotations

import calendar
import math
from dataclasses import dataclass
from datetime import date

from ..catalogue import lookup
from ..stats import TargetStat, Wrapped
from ..targets import UNNAMED
from . import svg
from .svg import fmt_hours, fmt_int, round_half_up, text
from .themes import THEMES, Theme

W, H = 1080, 1350          # portrait (Instagram 4:5)
PW, PH = 1600, 900         # poster (X)
LEFT, RIGHT = 80, 1000     # the portrait margins
BOX = RIGHT - LEFT

MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")
MON = tuple(m[:3] for m in MONTHS)


@dataclass(frozen=True)
class Card:
    name: str
    width: int
    height: int
    svg: str


def level(hours: float) -> int:
    """Calendar shade: -1 for no imaging, then ramp 0-4 for < 2, < 6, < 12, < 20 and 20+ hours."""
    if hours <= 0:
        return -1
    for i, top in enumerate((2, 6, 12, 20)):
        if hours < top:
            return i
    return 4


# ------------------------------------------------------------------ words

def _years(w: Wrapped) -> str:
    if w.year is not None:
        return str(w.year)
    a, b = w.first_night.year, w.last_night.year
    return str(a) if a == b else f"{a}–{b}"


def _date(w: Wrapped, d) -> str:
    s = f"{MON[d.month - 1]} {d.day}"
    return s if w.year is not None else f"{s}, {d.year}"


def _short(t: TargetStat) -> str:
    """The common name minus a trailing " Nebula", else the label."""
    if t.common_name:
        n = t.common_name.strip()
        return n[:-len(" Nebula")] if n.endswith(" Nebula") and len(n) > len(" Nebula") else n
    return t.label


_GREEK = {"alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta", "iota", "kappa", "lambda", "mu",
          "nu", "xi", "omicron", "pi", "rho", "sigma", "tau", "upsilon", "phi", "chi", "psi", "omega"}


def _is_star_name(t: TargetStat, name: str) -> bool:
    """Stars and star fields take no article ("44 Tauri", "NY Cephei"): decided by the catalogue kind; only a
    target the catalogue does not know falls back on its first word (a digit or a Greek letter name)."""
    o = lookup(t.key)
    if o is not None:
        return o.kind in ("star", "star_field")
    first = name.split(" ", 1)[0]
    return first[:1].isdigit() or first.lower() in _GREEK


def _the(t: TargetStat) -> str:
    """How a sentence names a target: "the Lagoon", "the Pleiades", "M 8", "an unnamed target"."""
    if not t.common_name:
        return "an unnamed target" if t.label == UNNAMED else t.label
    n = _short(t)
    if _is_star_name(t, n):
        return n
    return n if n.lower().startswith("the ") or "'s " in n or "’s " in n else f"the {n}"


def _light_years(d: float) -> str:
    """'40 million', '2.5 million' (one decimal below 10 million), '25,600'; below 10,000 ly two significant
    figures ('440', '1,300'), since the table's distances are approximate (R22: the card says "about")."""
    if d >= 1e6:
        m = d / 1e6
        return f"{m:.1f} million" if m < 10 else f"{round_half_up(m):,} million"
    if d < 1e4:
        step = 10 ** max(0, math.floor(math.log10(d)) - 1) if d >= 1 else 1
        return f"{round_half_up(d / step) * step:,}"
    return f"{round_half_up(d):,}"


def _tick(k: int) -> str:
    return f"{10 ** k:,}" if k < 6 else f"{10 ** (k - 6):,} million"


def _plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many


# ------------------------------------------------------------------ shared pieces

class _Ink:
    """Shorthand for one theme's text styles."""

    def __init__(self, t: Theme):
        self.t = t

    def kicker(self, s: str, y: float = 150, x: float = LEFT, box: float = BOX, size: float = 30) -> str:
        return text(x, y, s, font=self.t.body, size=size, fill=self.t.accent, ls=5, upper=True, box=box)

    def label(self, s: str, x: float, y: float, box: float, size: float = 28) -> str:
        return text(x, y, s, font=self.t.body, size=size, fill=self.t.muted, ls=4, upper=True, box=box)

    def head(self, s, x: float, y: float, size: float, box: float, fill: str | None = None, **kw) -> str:
        return text(x, y, s, font=self.t.head, size=size, fill=fill or self.t.fg, box=box, **kw)

    def body(self, s, x: float, y: float, size: float, box: float, fill: str | None = None, **kw) -> str:
        return text(x, y, s, font=self.t.body, size=size, fill=fill or self.t.muted, box=box, **kw)

    def head_width(self, s: str, size: float, ls: float = 0.0) -> float:
        return svg.width(s, self.t.head, size, ls)

    def body_width(self, s: str, size: float) -> float:
        return svg.width(s, self.t.body, size)


def _rect(x, y, w, h, fill, rx=0, opacity=None, extra="") -> str:
    o = f' opacity="{opacity:g}"' if opacity is not None and opacity < 1 else ""
    r = f' rx="{svg.num(rx)}"' if rx else ""
    return (f'<rect x="{svg.num(x)}" y="{svg.num(y)}" width="{svg.num(w)}" height="{svg.num(h)}"{r} '
            f'fill="{fill}"{o}{extra}/>')


def _bar(x, y, full, h, frac, fill, track, rx, opacity=None) -> str:
    out = _rect(x, y, full, h, track, rx) if track else ""
    return out + _rect(x, y, max(h, full * frac), h, fill, rx, opacity)


def _footer(t: Theme, years: str, width: int, height: int, index: str | None) -> str:
    y = height - 62
    out = text(LEFT, y, f"SKYWRAPPED · {years}", font=t.body, size=26, fill=t.muted, ls=3,
               box=width - 2 * LEFT - 160)
    if index:
        out += text(width - LEFT, y, index, font=t.body, size=26, fill=t.muted, anchor="end", box=140)
    return out


def _hours_by_day(w: Wrapped) -> dict:
    out: dict = {}
    for n in w.per_night:
        k = n.date if w.year is not None else (n.date.month, n.date.day)
        out[k] = out.get(k, 0.0) + n.hours
    return out


def _grid(t: Theme, w: Wrapped, x0: float, y0: float, cs: float, gap: float, row: float, label_size: float,
          label_box: float, rx: float) -> str:
    """Twelve rows of day squares, one row per month."""
    hours = _hours_by_day(w)
    ref = w.year if w.year is not None else 2000  # a leap year shows Feb 29 when all years are shown
    out = []
    for m in range(1, 13):
        y = y0 + (m - 1) * row
        out.append(text(x0 - label_size * 0.55, y + cs - 3, MON[m - 1], font=t.body, size=label_size,
                        fill=t.muted, anchor="end", box=label_box))
        for d in range(1, calendar.monthrange(ref, m)[1] + 1):
            if w.year is not None:
                key = date(w.year, m, d)
                tag = key.isoformat()
            else:
                key, tag = (m, d), f"{m:02d}-{d:02d}"
            lv = level(hours.get(key, 0.0))
            out.append(_rect(x0 + (d - 1) * (cs + gap), y, cs, cs, t.cell0 if lv < 0 else t.ramp[lv], rx,
                             extra=f' data-day="{tag}"'))
    return "".join(out)


# ------------------------------------------------------------------ the portrait cards

def cover(t: Theme, w: Wrapped) -> str:
    k = _Ink(t)
    out = [k.kicker(f"My {_years(w)} under the night sky"),
           k.head(fmt_hours(w.hours), 76, 560, t.cover_size, RIGHT - 76, ls=-8)]
    line = [("hours of starlight", None)] + ([(" so far", t.muted)] if w.partial else [])
    out.append(k.head(line, 84, 650, 70, RIGHT - 84))
    if w.from_stacks_only:
        out.append(k.body("from stacked files", 84, 712, 34, RIGHT - 84))
    out.append(f'<line x1="84" x2="{W - 84}" y1="760" y2="760" stroke="{t.muted}" stroke-opacity=".35" '
               f'stroke-width="2"/>')
    for i, (v, what) in enumerate(((fmt_int(w.nights), "nights out"), (fmt_int(w.frames), "frames"),
                                   (fmt_int(w.targets), "targets"))):
        x = 84 + i * 310
        box = 290 if i < 2 else RIGHT - x
        out.append(k.head(v, x, 870, 84, box, fill=t.accent if i == 0 else t.fg))
        out.append(k.body(what, x + 4, 920, 30, box - 4))
    month, h = w.best_month
    out.append(k.body([("Best month: ", None), (f"{MONTHS[month - 1]}, {fmt_hours(h)} h", t.fg)], 84, 1080, 34,
                      RIGHT - 84))
    return "".join(out)


def night_calendar(t: Theme, w: Wrapped) -> str:
    k = _Ink(t)
    cs, gap, x0, y0, row = 23, 4.6, 150, 330, 49
    out = [k.kicker("Every night you went out"),
           k.head(f"{fmt_int(w.nights)} nights, one sky", LEFT, 245, 64, BOX),
           _grid(t, w, x0, y0, cs, gap, row, 26, x0 - 14 - LEFT, t.cell_rx)]
    y_sq, y_txt, sq, sq_gap = y0 + 11 * row + cs + 44, y0 + 11 * row + cs + 65, 24, 10
    more_w = k.body_width("more", 24)
    sq_end = RIGHT - more_w - 12
    sq_start = sq_end - (5 * sq + 4 * sq_gap)
    out.append(k.body("more", RIGHT, y_txt, 24, more_w + 1, anchor="end"))
    out += [_rect(sq_start + i * (sq + sq_gap), y_sq, sq, sq, c, t.cell_rx) for i, c in enumerate(t.ramp)]
    less_end = sq_start - 12
    less_w = k.body_width("less", 24)
    out.append(k.body("less", less_end, y_txt, 24, less_w + 1, anchor="end"))
    out.append(k.body("each square is a night · brighter = more hours", LEFT, y_txt, 26,
                      less_end - less_w - 28 - LEFT))
    return "".join(out)


def top_targets(t: Theme, w: Wrapped) -> str:
    k = _Ink(t)
    tops = w.top_targets[:5]
    first = tops[0]
    out = [k.kicker("Your most-loved targets"),
           k.head(f"{fmt_hours(first.hours)} hours on {_the(first)}", LEFT, 245, 64, BOX)]
    top_h = first.hours or 1.0
    for i, s in enumerate(tops):
        y = 380 + i * 170
        hrs = f"{fmt_hours(s.hours)} h"
        hw = k.head_width(hrs, 54)
        out.append(k.head(hrs, RIGHT, y, 54, math.ceil(hw) + 1, fill=t.accent if i == 0 else t.fg, anchor="end"))
        out.append(k.head(s.label, LEFT, y, 54, BOX - hw - 30))
        if s.common_name:
            out.append(k.body(s.common_name, LEFT, y + 42, 30, BOX))
        out.append(_bar(LEFT, y + 66, BOX, 14, s.hours / top_h, t.accent if i == 0 else t.accent2, t.cell0, 7))
    return "".join(out)


MAX_DOTS = 30


def _dots(dist, oldest, youngest):
    """The axis dots: every distanced target but the oldest and youngest, capped at MAX_DOTS (most-observed first)."""
    rest = [s for s in dist if s is not oldest and s is not youngest]
    return rest[:MAX_DOTS]


def journey(t: Theme, w: Wrapped) -> str | None:
    """The light-travel-time card, or None when fewer than two targets (of all, not just the top) have a distance."""
    dist = [s for s in w.top_targets if s.distance_ly and s.distance_ly > 0]
    if len(dist) < 2:
        return None
    k = _Ink(t)
    oldest = max(dist, key=lambda s: s.distance_ly)
    youngest = min((s for s in dist if s is not oldest), key=lambda s: s.distance_ly)
    out = [k.kicker("How far your light travelled"),
           k.head("The oldest light you caught", LEFT, 300, 58, BOX),
           k.head([("left ", None), (oldest.label, t.accent)], LEFT, 372, 58, BOX),
           k.head("about", LEFT, 520, 60, 300, fill=t.accent)]
    nx = LEFT + svg.real_width("about", t.head, 60) + 20
    out += [k.head(_light_years(oldest.distance_ly), nx, 520, 150, RIGHT - nx, fill=t.accent, ls=-3),
            k.head("years ago", 84, 590, 54, RIGHT - 84)]

    y, x0, x1 = 820, 110, W - 110
    lo = math.floor(math.log10(min(s.distance_ly for s in dist)))
    hi = max(lo + 3, math.ceil(math.log10(oldest.distance_ly)))

    def X(d: float) -> float:
        return x0 + (math.log10(d) - lo) / (hi - lo) * (x1 - x0)

    out.append(f'<line x1="{x0}" x2="{x1}" y1="{y}" y2="{y}" stroke="{t.muted}" stroke-opacity=".6" '
               f'stroke-width="3"/>')
    ticks = list(range(lo + 1, hi))
    step = 1 if len(ticks) <= 5 else 2
    pitch = (x1 - x0) / (hi - lo)
    for j, e in enumerate(ticks):
        tx = X(10 ** e)
        out.append(f'<line x1="{svg.num(tx)}" x2="{svg.num(tx)}" y1="{y - 16}" y2="{y + 16}" stroke="{t.muted}" '
                   f'stroke-opacity=".5" stroke-width="2"/>')
        if j % step == 0:
            out.append(k.body(_tick(e), tx, y + 62, 24, step * pitch - 12, anchor="middle"))
    for s in _dots(dist, oldest, youngest):
        out.append(f'<circle cx="{svg.num(X(s.distance_ly))}" cy="{y}" r="9" fill="{t.fg}" opacity=".75"/>')
    yx, ox = X(youngest.distance_ly), X(oldest.distance_ly)
    out.append(f'<circle cx="{svg.num(yx)}" cy="{y}" r="15" fill="{t.accent2}"/>')
    out.append(f'<circle cx="{svg.num(ox)}" cy="{y}" r="15" fill="{t.accent}"/>')

    y_start = max(LEFT, yx - 20)
    o_end = min(RIGHT, ox + 20)
    y_box, o_box = min(420, RIGHT - y_start), min(420, o_end - LEFT)
    y_w = min(y_box, k.body_width(_short(youngest), 26))
    o_w = min(o_box, k.body_width(_short(oldest), 26))
    o_y = y - 44 if y_start + y_w + 24 <= o_end - o_w else y - 84
    out.append(k.body(_short(youngest), y_start, y - 44, 26, y_box, fill=t.accent2))
    out.append(k.body(_short(oldest), o_end, o_y, 26, o_box, fill=t.accent, anchor="end"))
    out.append(k.body("light-years", W / 2, y + 108, 24, 300, anchor="middle"))
    out.append(k.body([("The youngest: ", None), (f"{_the(youngest)}, about {_light_years(youngest.distance_ly)} years",
                                                  t.fg)], LEFT, 1080, 34, BOX))
    return "".join(out)


def records(t: Theme, w: Wrapped) -> str:
    k = _Ink(t)

    def block(y: float, key: str, big: str, unit: str, sub: str) -> str:
        shown, size = svg.fit(big, t.head, 130, 560)
        nw = svg.real_width(shown, t.head, size)
        ux = 76 + nw + 14
        return (k.label(key, LEFT, y, BOX) + k.head(big, 76, y + 120, 130, 560)
                + k.head(unit, ux, y + 120, 56, RIGHT - ux, fill=t.accent)
                + k.body(sub, LEFT, y + 172, 32, BOX))

    n, start, end = w.longest_streak
    streak = f"{_date(w, start)} to {_date(w, end)}" if start != end else _date(w, start)
    b = w.busiest_night
    tg = f"{b.targets} {_plural(b.targets, 'target', 'targets')}"
    busy = (f"{_date(w, b.date)}: {b.telescopes} telescopes, {tg} at once" if b.telescopes > 1
            else f"{_date(w, b.date)}: {tg}")
    pct = round_half_up(w.bright_moon_share * 100)
    moon = (f"{pct}% of your hours were under a bright Moon" if w.moon_uses_altitude
            else f"{pct}% of your hours were on bright-Moon nights")
    return "".join([
        k.kicker("Records"),
        block(260, "Longest streak", fmt_int(n), _plural(n, "night in a row", "nights in a row"), streak),
        block(560, "Busiest night", fmt_hours(b.hours), "hours", busy),
        block(860, "Moon", fmt_int(w.full_moon_nights),
              _plural(w.full_moon_nights, "full-moon night", "full-moon nights"), moon),
    ])


def gear(t: Theme, w: Wrapped) -> str:
    k = _Ink(t)
    n = len(w.setups)
    out = [k.kicker("The gear that did it"),
           k.head(f"{n} {_plural(n, 'setup', 'setups')}, one sky", LEFT, 245, 64, BOX)]
    rows = w.setups[:7]
    top_h = (rows[0].hours if rows else 0) or 1.0
    for i, s in enumerate(rows):
        y = 360 + i * 118
        hrs = f"{fmt_hours(s.hours)} h"
        hw = k.head_width(hrs, 38)
        out.append(k.body(s.label, LEFT, y, 34, BOX - hw - 30, fill=t.fg))
        out.append(k.head(hrs, RIGHT, y, 38, math.ceil(hw) + 1, fill=t.accent if i == 0 else t.fg, anchor="end"))
        out.append(_bar(LEFT, y + 22, BOX, 16, s.hours / top_h, t.accent if i == 0 else t.accent2, None, 8,
                        opacity=round(1 - i * 0.08, 2)))
    return "".join(out)


# ------------------------------------------------------------------ the poster

def poster(t: Theme, w: Wrapped) -> str:
    k = _Ink(t)
    col = 680  # left column, 80 to 760
    out = [k.kicker(f"My {_years(w)} under the night sky", y=130, box=col, size=28),
           k.head(fmt_hours(w.hours), 74, 380, 230 if t.serif else 250, col + 6, ls=-6)]
    line = [("hours of starlight", None)] + ([(" so far", t.muted)] if w.partial else [])
    out.append(k.head(line, LEFT, 455, 54, col))
    if w.from_stacks_only:
        out.append(k.body("from stacked files", LEFT, 497, 28, col))
    out.append(f'<line x1="{LEFT}" x2="{LEFT + col}" y1="535" y2="535" stroke="{t.muted}" stroke-opacity=".35" '
               f'stroke-width="2"/>')
    for i, (v, what) in enumerate(((fmt_int(w.nights), "nights out"), (fmt_int(w.frames), "frames"),
                                   (fmt_int(w.targets), "targets"))):
        x = LEFT + i * 235
        box = 215 if i < 2 else LEFT + col - x
        out.append(k.head(v, x, 622, 64, box, fill=t.accent if i == 0 else t.fg))
        out.append(k.body(what, x + 3, 662, 26, box - 3))
    month, h = w.best_month
    out.append(k.body([("Best month: ", None), (f"{MONTHS[month - 1]}, {fmt_hours(h)} h", t.fg)], LEFT, 748, 30,
                      col))

    x0, x1 = 880, PW - LEFT  # right column
    rbox = x1 - x0
    out.append(k.label("Your most-loved targets", x0, 130, rbox, size=24))
    tops = w.top_targets[:3]
    top_h = (tops[0].hours if tops else 0) or 1.0
    for i, s in enumerate(tops):
        y = 200 + i * 92
        hrs = f"{fmt_hours(s.hours)} h"
        hw = k.head_width(hrs, 38)
        out.append(k.head(s.label, x0, y, 38, rbox - hw - 24))
        out.append(k.head(hrs, x1, y, 38, math.ceil(hw) + 1, fill=t.accent if i == 0 else t.fg, anchor="end"))
        out.append(_bar(x0, y + 18, rbox, 10, s.hours / top_h, t.accent if i == 0 else t.accent2, t.cell0, 5))
    out.append(k.label(f"{fmt_int(w.nights)} nights, one sky", x0, 486, rbox, size=24))
    cs, gap, row = 14, 5.6, 24
    gx0 = x1 - (30 * (cs + gap) + cs)
    out.append(_grid(t, w, gx0, 508, cs, gap, row, 16, gx0 - 9 - x0, min(t.cell_rx, 3)))
    return "".join(out)


# ------------------------------------------------------------------ the set

PORTRAIT = (("cover", 1, cover), ("calendar", 2, night_calendar), ("targets", 3, top_targets),
            ("journey", 4, journey), ("records", 5, records), ("gear", 6, gear))


def render_cards(w: Wrapped, theme: str = "observatory") -> list[Card]:
    """The portrait cards (cover, calendar, targets, journey when it can be drawn, records, gear), then the poster.

    Each card's starfield is seeded by its fixed slot, so dropping the journey card never changes the others' skies;
    the footer's "i/n" counts the portrait cards actually made.
    """
    if theme not in THEMES:
        raise ValueError(f"unknown theme {theme!r}; choose from {', '.join(THEMES)}")
    t = THEMES[theme]
    years = _years(w)
    made = []
    for name, slot, fn in PORTRAIT:
        inner = fn(t, w)
        if inner is not None:
            made.append((name, slot, inner))
    cards = [Card(name, W, H, svg.frame(t, slot, W, H, inner, _footer(t, years, W, H, f"{i}/{len(made)}")))
             for i, (name, slot, inner) in enumerate(made, 1)]
    cards.append(Card("poster", PW, PH, svg.frame(t, 7, PW, PH, poster(t, w), _footer(t, years, PW, PH, None))))
    return cards
