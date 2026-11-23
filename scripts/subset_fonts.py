#!/usr/bin/env python
"""Build the card fonts in src/skywrapped/cards/fonts/ from the two OFL variable fonts.

Build-time only (needs ``fonttools`` from the ``dev`` extra); the runtime never imports fontTools.

    .venv/bin/python scripts/subset_fonts.py

Inputs (git-ignored, downloaded once):
    .cache/fonts/ebgaramond/EBGaramond[wght].ttf   + OFL.txt   (google/fonts, ofl/ebgaramond)
    .cache/fonts/inter/Inter[opsz,wght].ttf        + OFL.txt   (google/fonts, ofl/inter)

Each output is one static instance (the variable axes pinned), subset to Latin (Basic Latin, Latin-1 Supplement,
Latin Extended-A) plus the punctuation the cards print, without hinting, under a family name of its own so a
system copy of the same font can never stand in for it. EB Garamond's figures are switched to its proportional
lining set. Beside the fonts it writes ``metrics.json`` (advance widths per character, for text fitting without
fontTools) and ``OFL.txt`` (both licences, as the OFL requires).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache" / "fonts"
OUT = ROOT / "src" / "skywrapped" / "cards" / "fonts"
MAX_BYTES = 60 * 1024

# Latin, plus the brief's extra glyphs (· – — ° − ’) and the ones fitting and quoting need (‘ “ ” …)
UNICODES = (list(range(0x20, 0x7F)) + list(range(0xA0, 0x100)) + list(range(0x100, 0x180))
            + [0x2013, 0x2014, 0x2018, 0x2019, 0x201C, 0x201D, 0x2026, 0x2212])

FONTS = [
    # (source, axes, output file, family, weight, style name, lining figures from pnum)
    ("ebgaramond/EBGaramond[wght].ttf", {"wght": 400}, "EBGaramond-Regular.ttf",
     "Skywrapped EB Garamond", 400, "Regular", True),
    ("inter/Inter[opsz,wght].ttf", {"wght": 400, "opsz": 14}, "Inter-Regular.ttf",
     "Skywrapped Inter", 400, "Regular", False),
    ("inter/Inter[opsz,wght].ttf", {"wght": 800, "opsz": 32}, "InterDisplay-ExtraBold.ttf",
     "Skywrapped Inter Display", 800, "ExtraBold", False),
]


def _single_subst(font: TTFont, tag: str) -> dict[str, str]:
    """The glyph mapping of a GSUB feature made of single substitutions."""
    gsub = font["GSUB"].table
    out: dict[str, str] = {}
    for rec in gsub.FeatureList.FeatureRecord:
        if rec.FeatureTag != tag:
            continue
        for li in rec.Feature.LookupListIndex:
            for st in gsub.LookupList.Lookup[li].SubTable:
                st = getattr(st, "ExtSubTable", st)
                out.update(getattr(st, "mapping", {}) or {})
    return out


def _proportional_figures(font: TTFont) -> None:
    """Point the cmap's digits at the proportional lining figures (pnum), so they need no feature."""
    sub = _single_subst(font, "pnum")
    for table in font["cmap"].tables:
        for cp in range(0x30, 0x3A):
            g = table.cmap.get(cp)
            if g in sub:
                table.cmap[cp] = sub[g]


def _rename(font: TTFont, family: str, weight: int, style: str) -> None:
    name = font["name"]
    ps = (family + "-" + style).replace(" ", "")
    for nid in (1, 2, 3, 4, 6, 16, 17, 25):
        name.removeNames(nameID=nid)
    for nid, text in ((1, family), (2, "Regular"), (3, f"{ps};skywrapped"), (4, f"{family} {style}".strip()),
                      (6, ps)):
        name.setName(text, nid, 3, 1, 0x409)
        name.setName(text, nid, 1, 0, 0)
    font["OS/2"].usWeightClass = weight
    font["OS/2"].fsSelection = (font["OS/2"].fsSelection & ~0b1100001) | 0b1000000  # REGULAR, not bold/italic
    font["head"].macStyle = 0


def build_one(src: Path, axes: dict, family: str, weight: int, style: str, lining: bool) -> TTFont:
    font = TTFont(src)
    font = instancer.instantiateVariableFont(font, axes)
    if lining:
        _proportional_figures(font)
    opts = subset.Options()
    opts.layout_features = ["kern", "liga"]
    opts.hinting = False
    opts.glyph_names = False
    opts.name_IDs = [0, 1, 2, 3, 4, 5, 6, 13, 14]
    opts.drop_tables += ["STAT", "MVAR", "HVAR", "gasp", "prep", "DSIG"]
    sub = subset.Subsetter(opts)
    sub.populate(unicodes=UNICODES)
    sub.subset(font)
    _rename(font, family, weight, style)
    font.recalcTimestamp = False  # reproducible bytes: keep the source's head.modified
    return font


def metrics(font: TTFont) -> dict:
    cmap = font.getBestCmap()
    hmtx = font["hmtx"]
    return {
        "upm": font["head"].unitsPerEm,
        "advance": {chr(cp): hmtx[g][0] for cp, g in sorted(cmap.items())},
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    table = {}
    for src, axes, out_name, family, weight, style, lining in FONTS:
        path = CACHE / src
        if not path.exists():
            print(f"missing {path}: download it first (see the docstring)", file=sys.stderr)
            return 1
        font = build_one(path, axes, family, weight, style, lining)
        out = OUT / out_name
        font.save(out)
        size = out.stat().st_size
        print(f"{out_name}: {size:,} bytes, {len(font.getGlyphOrder())} glyphs, family {family!r} {weight}")
        if size > MAX_BYTES:
            print(f"{out_name} is over {MAX_BYTES:,} bytes", file=sys.stderr)
            return 1
        reread = TTFont(out)
        table[out_name] = {"family": family, "weight": weight, **metrics(reread)}
    (OUT / "metrics.json").write_text(json.dumps(table, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                                      + "\n", encoding="utf-8")
    parts = []
    for label, files, src in (("EB Garamond", "EBGaramond-Regular.ttf", "ebgaramond/OFL.txt"),
                              ("Inter", "Inter-Regular.ttf, InterDisplay-ExtraBold.ttf", "inter/OFL.txt")):
        text = (CACHE / src).read_text(encoding="utf-8").strip()
        parts.append(f"{label} ({files}): subset static instances of the original font.\n\n{text}\n")
    (OUT / "OFL.txt").write_text(("\n" + "=" * 78 + "\n\n").join(parts), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
