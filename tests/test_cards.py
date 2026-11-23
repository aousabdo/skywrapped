import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path

import pytest

from helpers import cw, frames_from_fixtures, sample
from skywrapped.cards import THEMES, Card, font_files, render_cards

GOLDEN = Path(__file__).parent / "golden"
NS = "{http://www.w3.org/2000/svg}"


@dataclass
class T:
    text: str
    size: float
    base_size: float
    box_width: float
    serif: bool
    family: str
    x: float
    anchor: str
    letter_spacing: float


def texts(svg: str) -> list[T]:
    """Every <text> on a card, with the size it was fitted to, its base size and its box (data-base, data-box)."""
    out = []
    for el in ET.fromstring(svg).iter(NS + "text"):
        assert el.get("data-box") and el.get("data-base"), f"unfitted text: {''.join(el.itertext())!r}"
        fam = el.get("font-family")
        out.append(T("".join(el.itertext()), float(el.get("font-size")), float(el.get("data-base")),
                     float(el.get("data-box")), "Garamond" in fam, fam, float(el.get("x")),
                     el.get("text-anchor", "start"), float(el.get("letter-spacing", "0"))))
    return out


def est_width(t: T) -> float:
    """The brief's estimate: characters x size x 0.5 (serif) or 0.56 (sans)."""
    return len(t.text) * t.size * (0.5 if t.serif else 0.56)


def golden(theme: str, name: str) -> str:
    path = GOLDEN / f"{theme}-{name}.svg"
    if os.environ.get("SKYWRAPPED_UPDATE_GOLDEN") == "1":
        path.parent.mkdir(exist_ok=True)
        path.write_bytes({c.name: c.svg for c in render_cards(sample(), theme)}[name].encode("utf-8"))
    return path.read_bytes().decode("utf-8")


def card(cards: list[Card], name: str) -> str:
    return next(c.svg for c in cards if c.name == name)


def body(svg: str) -> str:
    """All the text a card prints, one string per <text>, joined by newlines."""
    return "\n".join(t.text for t in texts(svg))


# ------------------------------------------------------------------ the brief's tests

def test_card_set_and_sizes():
    cards = render_cards(sample(), "observatory")
    assert [c.name for c in cards] == ["cover", "calendar", "targets", "journey", "records", "gear", "poster"]
    assert (cards[0].width, cards[0].height) == (1080, 1350) and (cards[-1].width, cards[-1].height) == (1600, 900)
    for c in cards:
        ET.fromstring(c.svg)


def test_cover_copy():
    s = render_cards(sample(), "nebula")[0].svg
    assert "MY 2026 UNDER THE NIGHT SKY" in s and ">412<" in s and "hours of starlight" in s


def test_journey_dropped_and_renumbered():
    cards = render_cards(sample(distances=1), "observatory")
    assert "journey" not in [c.name for c in cards] and "5/5" in cards[4].svg


def test_partial_and_stacks_copy():
    assert "so far" in render_cards(sample(partial=True))[0].svg
    assert "from stacked files" in render_cards(sample(from_stacks_only=True))[0].svg


def test_text_fits():
    for c in render_cards(sample(top_label="NGC 7293 " + "very long common name " * 4)):
        for t in texts(c.svg):
            assert est_width(t) <= t.box_width and t.size >= 0.7 * t.base_size


def test_fonts_embedded_no_urls():
    s = render_cards(sample())[0].svg
    assert "@font-face" in s and "data:font/ttf;base64," in s and "http" not in s.replace("http://www.w3.org", "")


@pytest.mark.parametrize("theme", ["observatory", "nebula"])
def test_golden(theme):
    for c in render_cards(sample(), theme):
        assert c.svg == golden(theme, c.name)


def test_deterministic():
    assert render_cards(sample())[0].svg == render_cards(sample())[0].svg


def test_cards_private(fixture):  # the same sentinels as Task 8's privacy test, through to the SVGs
    w = cw(frames_from_fixtures(path_prefix="SECRETFOLDER/", hint="my secret field"))
    for c in render_cards(w):
        for s in ["12.3456", "65.4321", "12.35", "65.43", "SECRETFOLDER", "secret field"]:
            assert s not in c.svg


# ------------------------------------------------------------------ themes, fonts, fitting

def test_theme_values():
    o, n = THEMES["observatory"], THEMES["nebula"]
    assert (o.bg, o.glow, o.fg, o.muted, o.accent, o.accent2, o.cell0) == (
        "#07090f", "#0f1a2e", "#ece6d8", "#8c93a3", "#d9a55b", "#7fa7c9", "#141a26")
    assert o.ramp == ("#3a2f22", "#6b4f2c", "#a77b3e", "#d9a55b", "#f5d9a0") and o.serif
    assert (n.bg, n.glow, n.fg, n.muted, n.accent, n.accent2, n.cell0) == (
        "#160a33", "#0a3340", "#ffffff", "#c3b8e0", "#ffd166", "#ff6f91", "rgba(255,255,255,0.08)")
    assert n.ramp == ("#3d2a7a", "#6a3fb5", "#c04fd0", "#ff6f91", "#ffd166") and not n.serif
    s = render_cards(sample(), "nebula")[0].svg
    assert "#c2185b" in s and "#00bfa5" in s and 'cx="88%" cy="8%"' in s and 'cx="5%" cy="100%"' in s


def test_unknown_theme():
    with pytest.raises(ValueError):
        render_cards(sample(), "sepia")


def test_font_files_small_and_embedded_per_theme():
    import base64
    paths = font_files()
    assert len(paths) == 3 and all(Path(p).is_file() and Path(p).stat().st_size <= 60 * 1024 for p in paths)
    data = {Path(p).name: base64.b64encode(Path(p).read_bytes()).decode() for p in paths}
    obs, neb = render_cards(sample(), "observatory")[0].svg, render_cards(sample(), "nebula")[0].svg
    assert data["EBGaramond-Regular.ttf"] in obs and data["Inter-Regular.ttf"] in obs
    assert data["InterDisplay-ExtraBold.ttf"] not in obs
    assert data["InterDisplay-ExtraBold.ttf"] in neb and data["Inter-Regular.ttf"] in neb
    assert data["EBGaramond-Regular.ttf"] not in neb
    assert (Path(paths[0]).parent / "OFL.txt").read_text(encoding="utf-8").count("SIL Open Font License") >= 2


def _real_width(t: T, fonts) -> float:
    font = fonts[t.family.split("'")[1]]
    cmap, hmtx, upm = font.getBestCmap(), font["hmtx"], font["head"].unitsPerEm
    assert all(ord(ch) in cmap for ch in t.text), f"glyph missing for {t.text!r}"
    return sum(hmtx[cmap[ord(ch)]][0] for ch in t.text) * t.size / upm + t.letter_spacing * len(t.text)


@pytest.mark.parametrize("theme", ["observatory", "nebula"])
def test_text_fits_real_glyphs(theme):
    """The real advance widths of the shipped glyphs (read with fontTools, not the package's own table) fit each
    box, and each box sits inside the card."""
    TTFont = pytest.importorskip("fontTools.ttLib").TTFont
    fonts = {}
    for p in font_files():
        f = TTFont(p)
        fonts[f["name"].getDebugName(1)] = f
    long = "NGC 7293 " + "very long common name " * 4
    for w in (sample(), sample(top_label=long), sample(partial=True, from_stacks_only=True)):
        for c in render_cards(w, theme):
            for t in texts(c.svg):
                assert _real_width(t, fonts) <= t.box_width + 0.01, (c.name, t.text)
                left = {"start": t.x, "end": t.x - t.box_width, "middle": t.x - t.box_width / 2}[t.anchor]
                assert -0.01 <= left and left + t.box_width <= c.width + 0.01, (c.name, t.text)


def test_no_tspan_starts_with_a_space():  # resvg drops it: "hours of starlightso far"
    for c in render_cards(sample(partial=True)):
        for el in ET.fromstring(c.svg).iter(NS + "tspan"):
            assert not (el.text or "").startswith(" "), (c.name, el.text)
    assert "hours of starlight so far" in body(render_cards(sample(partial=True))[0].svg)


def test_long_name_cut_with_ellipsis():
    long = "NGC 7293 " + "very long common name " * 4
    s = body(card(render_cards(sample(top_label=long)), "targets"))
    assert "…" in s and long.strip() not in s


def test_cards_package_is_stdlib_only():
    code = ("import sys; sys.path.insert(0, 'tests'); from helpers import sample; "
            "from skywrapped.cards import render_cards; render_cards(sample()); render_cards(sample(), 'nebula'); "
            "bad = sorted(m for m in sys.modules if m.split('.')[0] in ('fontTools', 'numpy', 'astropy', 'resvg_py')); "
            "print(bad); sys.exit(1 if bad else 0)")
    r = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).parent.parent, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


# ------------------------------------------------------------------ copy and numbers

def test_numbers_r6():
    w = sample()
    w.hours, w.frames = 1204.4, 1234567
    s = body(render_cards(w)[0].svg)
    assert "1,204" in s.split("\n") and "1,234,567" in s.split("\n")
    w.hours = 7.54
    assert "7.5" in body(render_cards(w)[0].svg).split("\n")
    w.hours = 9.97
    assert "10" in body(render_cards(w)[0].svg).split("\n")


def test_cover_best_month_and_footer():
    cards = render_cards(sample())
    s = body(cards[0].svg)
    assert "Best month: August, 63 h" in s and "nights out" in s and "frames" in s and "targets" in s
    assert "87" in s.split("\n") and "19,240" in s.split("\n") and "41" in s.split("\n")
    for i, c in enumerate(cards[:-1], 1):
        lines = body(c.svg).split("\n")
        assert "SKYWRAPPED · 2026" in lines and f"{i}/6" in lines
    assert "SKYWRAPPED · 2026" in body(cards[-1].svg) and "/6" not in body(cards[-1].svg)


def test_calendar_copy_and_levels():
    w = sample()
    s = card(render_cards(w), "calendar")
    text = body(s)
    assert "EVERY NIGHT YOU WENT OUT" in text and "87 nights, one sky" in text
    assert "each square is a night · brighter = more hours" in text
    ramp = THEMES["observatory"].ramp
    root = ET.fromstring(s)
    cells = [r for r in root.iter(NS + "rect") if r.get("data-day")]
    assert len(cells) == 365
    fill = {r.get("data-day"): r.get("fill") for r in cells}
    assert fill["2026-10-17"] == ramp[4] and fill["2026-08-20"] == ramp[3]   # 21.6 h, 14.2 h (pinned in make_sample_wrapped.py)
    assert fill["2026-09-12"] == ramp[2] and fill["2026-06-06"] == ramp[1]   # 8.4 h, 3.7 h
    assert fill["2026-06-09"] == ramp[0]                                     # 0.9 h
    assert fill["2026-01-01"] == THEMES["observatory"].cell0


def test_calendar_level_edges():
    from skywrapped.cards.layouts import level
    assert [level(h) for h in (0, 0.01, 1.99, 2, 5.99, 6, 11.99, 12, 19.99, 20, 35)] == [
        -1, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4]


def test_targets_copy():
    text = body(card(render_cards(sample()), "targets"))
    assert "YOUR MOST-LOVED TARGETS" in text and "59 hours on the Orion" in text
    for line in ("M 42", "59 h", "Orion Nebula", "M 31", "44 h", "Andromeda Galaxy", "IC 1805", "32 h"):
        assert line in text.split("\n")
    w = sample()
    w.top_targets[0].common_name = None
    assert "59 hours on M 42" in body(card(render_cards(w), "targets"))


def test_journey_copy():
    text = body(card(render_cards(sample()), "journey"))
    assert "HOW FAR YOUR LIGHT TRAVELLED" in text and "The oldest light you caught" in text
    lines = text.split("\n")
    assert "left M 51" in lines and "years ago" in lines and "light-years" in lines
    assert "about 27 million" in text.replace("about\n", "about ")   # R22: distances say "about"
    assert "The youngest: the Pleiades, about 440 years" in lines     # R22: < 10,000 ly to 2 significant figures


def test_journey_numbers():
    w = sample()
    for t in w.top_targets:
        if t.key in ("M51", "M101"):
            t.distance_ly = None
    lines = body(card(render_cards(w), "journey")).split("\n")
    assert "12 million" in lines and "left M 81" in lines           # 1.19e7
    for t in w.top_targets:
        if t.key == "M81":
            t.distance_ly = None
        if t.key == "M33":
            t.distance_ly = None
    assert "2.5 million" in body(card(render_cards(w), "journey")).split("\n")   # 2.5e6, one decimal below 10 M
    w = sample()
    for t in w.top_targets:
        if t.distance_ly and t.distance_ly > 1e4:
            t.distance_ly = None
    lines = body(card(render_cards(w), "journey")).split("\n")
    assert "6,400" in lines and "left IC 1805" in lines
    for t in w.top_targets:
        if t.key not in ("IC1805", "M27"):
            t.distance_ly = None
        elif t.key == "M27":
            t.distance_ly = 1344
    lines = body(card(render_cards(w), "journey")).split("\n")
    assert "The youngest: the Dumbbell, about 1,300 years" in lines
    from skywrapped.cards.layouts import _light_years
    assert [_light_years(d) for d in (444, 650, 1344, 5700, 9960, 25600, 2.5e6, 4.0e7)] == [
        "440", "650", "1,300", "5,700", "10,000", "25,600", "2.5 million", "40 million"]


def test_records_copy():
    text = body(card(render_cards(sample()), "records"))
    lines = text.split("\n")
    assert "RECORDS" in lines and "LONGEST STREAK" in lines and "BUSIEST NIGHT" in lines and "MOON" in lines
    assert "9" in lines and "nights in a row" in lines and "Jul 29 to Aug 6" in lines
    assert "22" in lines and "hours" in lines and "Oct 17: 3 telescopes, 5 targets at once" in lines
    assert "7" in lines and "full-moon nights" in lines and "31% of your hours were under a bright Moon" in lines
    w = sample()
    w.moon_uses_altitude = False
    w.busiest_night = replace(w.busiest_night, telescopes=1)
    lines = body(card(render_cards(w), "records")).split("\n")
    assert "31% of your hours were on bright-Moon nights" in lines and "Oct 17: 5 targets" in lines


def test_gear_copy():
    text = body(card(render_cards(sample()), "gear"))
    lines = text.split("\n")
    assert "THE GEAR THAT DID IT" in lines and "5 setups, one sky" in lines
    assert "80 mm refractor · ASI2600MC" in lines and "158 h" in lines and "200 mm lens · ASI183MM" in lines
    assert '8" SCT · ASI533MC' in lines and "24 h" in lines
    assert "1 setup, one sky" in body(card(render_cards(sample(setups=1)), "gear")).split("\n")


def test_all_time_years():
    w = sample(year=None)
    w.first_night = date(2024, 3, 1)
    cards = render_cards(w)
    assert "MY 2024–2026 UNDER THE NIGHT SKY" in body(cards[0].svg)
    assert "SKYWRAPPED · 2024–2026" in body(cards[1].svg)


def test_article_by_catalogue_kind_only():
    from skywrapped.cards.layouts import _the
    from skywrapped.stats import TargetStat

    def name(key, common):
        return _the(TargetStat(key, key, common, 1.0, 1, 1, None))
    for key, common in (("44TAU", "44 Tauri"), ("NYCEP", "NY Cephei"), ("ZETOPH", "Zeta Ophiuchi")):
        assert name(key, common) == common
    assert name("M17", "Omega Nebula") == "the Omega"
    assert name("RHOOPH", "Rho Ophiuchi cloud complex") == "the Rho Ophiuchi cloud complex"
    assert name("NGC104", "47 Tuc Cluster") == "the 47 Tuc Cluster"
    assert name("NGC7293", "Helix Nebula") == "the Helix"
    assert name("M45", "Pleiades") == "the Pleiades"


def test_article_sweep_over_the_catalogue():
    from skywrapped.cards.layouts import _the
    from skywrapped.catalogue import load_catalogue
    from skywrapped.stats import TargetStat
    for o in load_catalogue():
        if not o.common_name:
            continue
        out = _the(TargetStat(o.id, o.id, o.common_name, 1.0, 1, 1, None))
        article = out.startswith("the ") or "'s " in out or "\u2019s " in out
        if o.kind in ("star", "star_field"):
            assert not out.startswith("the "), (o.id, out)
        else:
            assert article, (o.id, out)


def test_journey_dot_cap():
    import re
    from skywrapped.stats import TargetStat
    w = sample()
    w.top_targets = [TargetStat(f"X{i}", f"X {i}", None, 40.0 - i, 10, 1, 1000.0 * 1.3 ** i) for i in range(40)]
    w.targets = 40
    s = card(render_cards(w), "journey")
    circles = re.findall(r'<circle cx="([\d.]+)" cy="[\d.]+" r="(\d+)"', s)
    small = [float(x) for x, r in circles if r == "9"]
    big = [float(x) for x, r in circles if r == "15"]
    assert len(small) == 30 and len(big) == 2
    young_x, old_x = big  # drawn youngest first, then oldest
    assert young_x == min(small + big) and old_x == max(small + big)
    assert 110 <= young_x < old_x <= 970
