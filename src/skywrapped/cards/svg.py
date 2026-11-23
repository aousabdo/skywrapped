"""SVG building blocks: embedded fonts, text that fits its box, the card frame (background, stars, footer).

Stdlib only. Text width is measured twice and the larger wins: the plan's estimate (characters x size x 0.5 for
the serif, 0.56 for the sans) and the shipped glyphs' real advance widths (``fonts/metrics.json``, written by
``scripts/subset_fonts.py``). A line that is too wide shrinks to no less than 70% of its size, then is cut with an
ellipsis, so nothing ever runs out of its box.
"""
from __future__ import annotations

import base64
import json
import math
import re
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files

from .themes import Theme

MIN_SCALE = 0.7
ELLIPSIS = "…"


@dataclass(frozen=True)
class Font:
    file: str
    family: str
    weight: int
    serif: bool

    @property
    def css(self) -> str:
        return f"'{self.family}', {'serif' if self.serif else 'sans-serif'}"


FONTS = {
    "serif": Font("EBGaramond-Regular.ttf", "Skywrapped EB Garamond", 400, True),
    "sans": Font("Inter-Regular.ttf", "Skywrapped Inter", 400, False),
    "display": Font("InterDisplay-ExtraBold.ttf", "Skywrapped Inter Display", 800, False),
}


def _fonts_dir():
    return files("skywrapped.cards").joinpath("fonts")


def font_files() -> list[str]:
    """Paths of the bundled TTFs (for PNG rendering, which can't read the SVG's embedded fonts)."""
    return [str(_fonts_dir().joinpath(f.file)) for f in FONTS.values()]


@lru_cache(maxsize=None)
def _metrics() -> dict:
    return json.loads(_fonts_dir().joinpath("metrics.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def _font_face(key: str) -> str:
    f = FONTS[key]
    data = base64.b64encode(_fonts_dir().joinpath(f.file).read_bytes()).decode("ascii")
    return (f"@font-face{{font-family:'{f.family}';font-weight:{f.weight};font-style:normal;"
            f"src:url(data:font/ttf;base64,{data}) format('truetype');}}")


def font_css(keys) -> str:
    return "".join(_font_face(k) for k in keys)


# ------------------------------------------------------------------ small formatters

# characters XML 1.0 cannot hold at all: C0 controls but tab/newline/return, U+FFFE/U+FFFF, lone surrogates
_NOT_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff\ud800-\udfff]")


def esc(s: str) -> str:
    """Text for SVG: characters XML cannot carry are dropped, markup characters escaped."""
    return (_NOT_XML.sub("", str(s)).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def num(v: float) -> str:
    """A coordinate or size: at most one decimal, no trailing ".0"."""
    s = f"{v:.1f}"
    s = s[:-2] if s.endswith(".0") else s
    return "0" if s == "-0" else s


def round_half_up(v: float) -> int:
    return int(math.floor(v + 0.5))


def fmt_hours(h: float) -> str:
    """R6: hours of 10 or more as whole numbers with separators ("412", "1,204"), below 10 with one decimal."""
    if round(h, 1) >= 10:
        return f"{round_half_up(h):,}"
    return f"{h:.1f}"


def fmt_int(n: int) -> str:
    return f"{n:,}"


# ------------------------------------------------------------------ measuring and fitting

def real_width(s: str, font: str, size: float, ls: float = 0.0) -> float:
    m = _metrics()[FONTS[font].file]
    adv, upm = m["advance"], m["upm"]
    units = sum(adv.get(ch, 0.6 * upm) for ch in s)  # a glyph the subset lacks counts wide
    return units * size / upm + ls * len(s)


def est_width(s: str, font: str, size: float) -> float:
    return len(s) * size * (0.5 if FONTS[font].serif else 0.56)


def width(s: str, font: str, size: float, ls: float = 0.0) -> float:
    return max(est_width(s, font, size), real_width(s, font, size, ls))


def fit(s: str, font: str, base: float, box: float, ls: float = 0.0) -> tuple[str, float]:
    """Shrink ``s`` to fit ``box`` (never below 70% of ``base``), then cut it with an ellipsis."""
    if width(s, font, base, ls) <= box:
        return s, base
    floor = math.ceil(base * MIN_SCALE * 10) / 10
    size = max(floor, math.floor(base * box / width(s, font, base, ls) * 10) / 10)
    while size > floor and width(s, font, size, ls) > box:
        size = max(floor, round(size - 0.1, 1))
    if width(s, font, size, ls) <= box:
        return s, size
    cut = s
    while cut and width(cut.rstrip() + ELLIPSIS, font, size, ls) > box:
        cut = cut[:-1]
    return cut.rstrip() + ELLIPSIS, size


Part = tuple[str, "str | None"]  # (text, fill or None for the element's own fill)


def text(x: float, y: float, content, *, font: str, size: float, fill: str, box: float, anchor: str = "start",
         ls: float = 0.0, upper: bool = False, opacity: float | None = None) -> str:
    """A fitted <text>. ``content`` is a string or a list of (text, fill) parts drawn as coloured tspans."""
    parts: list[Part] = [(content, None)] if isinstance(content, str) else list(content)
    if upper:
        parts = [(p.upper(), c) for p, c in parts]
    full = "".join(p for p, _ in parts)
    shown, fitted = fit(full, font, size, box, ls)
    if shown != full:  # cut: keep the parts up to the cut, then the ellipsis
        keep, left = [], len(shown) - 1
        for p, c in parts:
            if left <= 0:
                break
            keep.append((p[:left], c))
            left -= len(p[:left])
        keep = [(p, c) for p, c in keep if p]
        if keep:
            p, c = keep[-1]
            keep[-1] = (p.rstrip() + ELLIPSIS, c)
        else:
            keep = [(ELLIPSIS, None)]
        parts = keep
    for i in range(1, len(parts)):  # resvg drops a tspan's leading space: keep spaces in the run before it
        p, c = parts[i]
        lead = len(p) - len(p.lstrip(" "))
        if lead:
            parts[i - 1] = (parts[i - 1][0] + p[:lead], parts[i - 1][1])
            parts[i] = (p[lead:], c)
    f = FONTS[font]
    attrs = [f'x="{num(x)}"', f'y="{num(y)}"', f'font-family="{f.css}"', f'font-size="{num(fitted)}"']
    if f.weight != 400:
        attrs.append(f'font-weight="{f.weight}"')
    attrs.append(f'fill="{fill}"')
    if ls:
        attrs.append(f'letter-spacing="{num(ls)}"')
    if anchor != "start":
        attrs.append(f'text-anchor="{anchor}"')
    if opacity is not None:
        attrs.append(f'opacity="{opacity:g}"')
    attrs += [f'data-base="{num(size)}"', f'data-box="{num(box)}"']
    inner = "".join(esc(p) if c is None else f'<tspan fill="{c}">{esc(p)}</tspan>' for p, c in parts)
    return f"<text {' '.join(attrs)}>{inner}</text>"


# ------------------------------------------------------------------ the frame

def _rng(seed: int):
    """The mockup's Lehmer generator, so each card's starfield matches it."""
    state = [seed]

    def r() -> float:
        state[0] = (state[0] * 16807) % 2147483647
        return state[0] / 2147483647
    return r


def frame(theme: Theme, idx: int, width_px: int, height_px: int, inner: str, footer: str) -> str:
    """The whole SVG: fonts, background glows, a starfield seeded by the card's slot, the content, the footer."""
    uid = f"sw-{theme.name}-{idx}"
    defs = []
    layers = [f'<rect width="{width_px}" height="{height_px}" fill="{theme.bg}"/>']
    for k, g in enumerate(theme.glows):
        gid = f"{uid}-g{k}"
        defs.append(f'<radialGradient id="{gid}" cx="{g.cx}%" cy="{g.cy}%" r="{g.r}%">'
                    f'<stop offset="0" stop-color="{g.color}" stop-opacity="{g.opacity:g}"/>'
                    f'<stop offset="1" stop-color="{g.end}" stop-opacity="0"/></radialGradient>')
        layers.append(f'<rect width="{width_px}" height="{height_px}" fill="url(#{gid})"/>')
    r = _rng(idx * 977 + 13)
    stars = []
    for _ in range(theme.stars):
        x, y = r() * width_px, r() * height_px
        rad = theme.star_r[0] + r() * theme.star_r[1]
        o = 0.15 + r() * 0.6
        stars.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rad:.1f}" fill="#fff" opacity="{o:.2f}"/>')
    style = font_css(sorted({theme.head, theme.body}))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width_px}" height="{height_px}" '
            f'viewBox="0 0 {width_px} {height_px}" role="img">'
            f'<defs><style>{style}</style>{"".join(defs)}</defs>'
            f'{"".join(layers)}<g>{"".join(stars)}</g>{inner}{footer}</svg>')
