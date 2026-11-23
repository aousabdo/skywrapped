# SkyWrapped - your year in astro, from your light frames' headers.   Siril: Scripts > Python Scripts > <folder> > SkyWrapped.py
# (c) 2026 Aous Abdo - https://github.com/aousabdo/skywrapped (questions and bug reports: the Issues page there)
# SPDX-License-Identifier: MIT
#
# Version history
# 0.1.0 - first version: window (Scripts menu) and typed command, cards drawn by Qt, no extra programs needed
"""SkyWrapped: turn a folder of light frames into "year in astro" cards, from inside Siril.

Picked from Siril's Scripts menu it opens a window: choose the folder, press Run, flip through the six cards and the
poster, press Save PNGs (typed as plain ``pyscript SkyWrapped.py`` it opens the same window). Typed in Siril's command
line with a folder (or run by siril-cli) it needs no window:

    pyscript SkyWrapped.py <folder> [<folder> ...] [--year N | --all] [--theme observatory|nebula] [--tz HOURS]
                           [--out DIR] [--exclude GLOB]... [--default-excludes] [--json-only]

The options are the ones of the skywrapped command line (they make the same summary.json and the same card SVGs);
--default-excludes adds the window's skip list (*/rejected/*, */_rejected/*, */previews/*).

Only the headers of the files are read. Nothing leaves your computer: the one thing that uses the internet is the first
run, when Siril's Python downloads the small `skywrapped` package that does the counting and the drawing (pip).
This file holds the Siril side only; it needs no libraries beyond what Siril brings (PyQt6, which it asks for if missing).
"""
from __future__ import annotations

import argparse
import html
import importlib
import importlib.metadata as _metadata
import os
import re
import sys
import threading
import time
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

VERSION = "0.1.0"
PIP_NAME = "skywrapped"
SKYWRAPPED_MIN = "0.1.0"                      # the oldest skywrapped this script works with (it uses 0.1.0's cli helpers)
MIN_PYTHON = (3, 10)                          # skywrapped's own minimum
THEMES = ("observatory", "nebula")
DEFAULT_EXCLUDES = ("*/rejected/*", "*/_rejected/*", "*/previews/*")
HOME_URL = "https://github.com/aousabdo/skywrapped"
WEB_URL = "https://aousabdo.github.io/skywrapped/"

# exit codes of the typed command: the skywrapped command line's own (2 nothing to count, 3 no PNG drawing, 4 output
# folder refused), plus 5 for "skywrapped could not be installed"
EXIT_OK, EXIT_NOTHING, EXIT_NO_PNG, EXIT_BAD_OUT, EXIT_SETUP = 0, 2, 3, 4, 5


class SetupError(RuntimeError):
    """skywrapped (or PyQt6) could not be installed or imported. The message is written for the user."""


class PngUnavailable(RuntimeError):
    """Qt cannot draw the PNGs. The message is written for the user."""


class Cancelled(Exception):
    """The user pressed Cancel."""


class OutputFolderRefused(RuntimeError):
    """The output folder has other files in it and was not made by skywrapped."""


# ---------------------------------------------------------------------------------------------------------------------
# Small helpers that need neither Siril nor Qt nor skywrapped
# ---------------------------------------------------------------------------------------------------------------------

def version_tuple(v: str) -> tuple:
    """The leading numbers of a version ("0.1.0.dev0" -> (0, 1, 0)); () when there are none."""
    m = re.match(r"\d+(?:\.\d+)*", str(v).strip())
    return tuple(int(x) for x in m.group(0).split(".")) if m else ()


def version_ok(installed: str, minimum: str = SKYWRAPPED_MIN) -> bool:
    a, b = version_tuple(installed), version_tuple(minimum)
    n = max(len(a), len(b))
    return bool(a) and a + (0,) * (n - len(a)) >= b + (0,) * (n - len(b))


def local_offset_hours() -> float:
    """This computer's UTC offset in hours right now (what `skywrapped` itself defaults to)."""
    off = datetime.now().astimezone().utcoffset()
    return off.total_seconds() / 3600.0 if off is not None else 0.0


def documents_dir() -> Path:
    """Where the cards go by default: the user's Documents folder, else the home folder."""
    home = Path.home()
    docs = home / "Documents"
    return docs if docs.is_dir() else home


def output_name(year) -> str:
    return f"skywrapped-{'all' if year is None else int(year)}"


def parse_excludes(text: str) -> list:
    """One glob per line; blank lines and surrounding spaces ignored."""
    return [ln.strip() for ln in str(text).splitlines() if ln.strip()]


def card_title(name: str) -> str:
    return "Poster" if name == "poster" else str(name).capitalize()


def say_default(message: str, level: str = "info") -> None:
    """Where messages go when nothing better is given (tests, running without Siril)."""
    print(message, file=sys.stderr if level == "error" else sys.stdout)


def siril_say(siril):
    """A ``say`` function that writes to Siril's console (and falls back to print when Siril is not there)."""
    try:
        import sirilpy as s
        colors = {"error": s.LogColor.RED, "good": s.LogColor.GREEN, "info": s.LogColor.DEFAULT}
    except Exception:
        return say_default

    def say(message: str, level: str = "info") -> None:
        try:
            for line in str(message).splitlines():
                if line.strip():                              # Siril's console is ASCII: the middle dot would print as "?"
                    siril.log(line.replace(" \u00b7 ", " | "), colors.get(level, s.LogColor.DEFAULT))
        except Exception:
            say_default(message, level)
    return say


# ---------------------------------------------------------------------------------------------------------------------
# skywrapped itself: install it on the first run, then use its own scanning, counting, drawing and folder rules
# ---------------------------------------------------------------------------------------------------------------------

_SW = None


def installed_version():
    """The installed skywrapped's version, or None."""
    try:
        return _metadata.version(PIP_NAME)
    except _metadata.PackageNotFoundError:
        return None


def _pip_install(minimum: str) -> None:
    """Siril's own installer (pip into Siril's Python); raises when it cannot."""
    import sirilpy
    sirilpy.ensure_installed(PIP_NAME, version_constraints=f">={minimum}")


def ensure_skywrapped(say=say_default, installer=None) -> str:
    """Make sure skywrapped >= SKYWRAPPED_MIN is installed and return its version.

    Installed and new enough: used as it is, nothing is downloaded. Missing or older: it is installed (or upgraded)
    from PyPI with Siril's installer, which needs the internet once. Raises SetupError with a plain message.
    """
    have = installed_version()
    if have is not None and version_ok(have):
        return have
    if sys.version_info < MIN_PYTHON:
        raise SetupError(
            f"skywrapped needs Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} or newer, and this Siril runs Python "
            f"{sys.version_info[0]}.{sys.version_info[1]}. Update Siril (its Python comes with it), or run "
            f"skywrapped from a terminal instead: {HOME_URL}")
    say("Installing skywrapped (first run only; this needs the internet)..." if have is None
        else f"Updating skywrapped {have} to {SKYWRAPPED_MIN} or newer...")
    try:
        (installer or _pip_install)(SKYWRAPPED_MIN)
    except (Exception, SystemExit) as e:             # sirilpy's installer raises SirilError, or exits on a restart
        raise SetupError(
            "Could not install skywrapped. The first run downloads it (about 1 MB), so the computer must be online. "
            "Connect to the internet and try again. Siril's console shows what pip said. If it keeps failing, the "
            f"same cards can be made in a web browser at {WEB_URL} (technical detail: {type(e).__name__}: {e}).") from e
    importlib.invalidate_caches()
    have = installed_version()
    if have is None or not version_ok(have):
        raise SetupError(f"skywrapped {SKYWRAPPED_MIN} or newer is still missing after the install. "
                         f"Try again, or see {HOME_URL}")
    return have


def load_skywrapped(say=say_default, install: bool = True) -> SimpleNamespace:
    """Import what this script uses from skywrapped (installing it first when ``install``). Cached."""
    global _SW
    if _SW is not None:
        return _SW
    if install:
        ensure_skywrapped(say)
    try:
        import skywrapped
        from skywrapped import cli, preview, scan, stats
        from skywrapped.cards import font_files, render_cards
    except ImportError as e:
        raise SetupError(f"skywrapped is installed but cannot be loaded ({e}). Try `pip install --upgrade skywrapped`; "
                         f"see {HOME_URL}") from e
    for name in ("MARKER", "_prepare_out", "_clear_own", "_final_line", "_no_lights"):   # the command line's own rules
        if not hasattr(cli, name):
            raise SetupError(f"This skywrapped ({skywrapped.__version__}) is newer than this script knows how to use "
                             f"(missing {name}). Update the script from {HOME_URL}")
    _SW = SimpleNamespace(version=skywrapped.__version__, cli=cli, scan=scan, stats=stats, preview=preview,
                          render_cards=render_cards, font_files=font_files)
    return _SW


def _sw() -> SimpleNamespace:
    if _SW is None:
        raise RuntimeError("load_skywrapped() has not run")
    return _SW


# ---------------------------------------------------------------------------------------------------------------------
# The work: scan, count, draw, write. The window and the typed command both go through these.
# ---------------------------------------------------------------------------------------------------------------------

def output_ok(path) -> bool:
    """skywrapped's rule: a missing or empty folder, or one skywrapped made before; never one with other files."""
    return bool(_sw().cli._prepare_out(str(path)))


def free_output_dir(year, parent=None) -> Path:
    """<parent>/skywrapped-<year> (or -all), or -2, -3 ... when that name is taken by a folder that is not ours."""
    parent = Path(parent).expanduser() if parent else documents_dir()
    base = output_name(year)
    for i in range(1, 1000):
        p = parent / (base if i == 1 else f"{base}-{i}")
        if output_ok(p):
            return p
    raise OutputFolderRefused(f"No free folder name like {base} in {parent}")


def scan_frames(paths, excludes, on_progress=None, cancelled=None):
    """skywrapped's own header scan. ``cancelled()`` is asked after every file; True stops with Cancelled."""
    def tick(done, total):
        if cancelled is not None and cancelled():
            raise Cancelled()
        if on_progress is not None:
            on_progress(done, total)
    return _sw().scan.scan_paths(list(paths), list(excludes), tick)


def count_year(frames, skipped, year, tz_hours):
    """The year's numbers (stats.Wrapped). Raises skywrapped.stats.NoLightsError when there is nothing to count."""
    return _sw().stats.compute_wrapped(frames, year=year, default_offset_h=float(tz_hours), today=date.today(),
                                       skipped=skipped)


def draw_cards(wrapped, theme):
    """[(stem, Card)]: card-1 ... card-6, poster. Stems are the file names skywrapped uses."""
    sw = _sw()
    return [(stem, card) for card, stem in sw.preview.card_stems(sw.render_cards(wrapped, theme=theme))]


def write_summary(out, summary: dict) -> None:
    import json
    target = os.path.join(str(out), "summary.json")
    tmp = target + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
    os.replace(tmp, target)


def write_output(out, wrapped, cards, png_renderer=None, json_only: bool = False) -> dict:
    """Write the marked output folder exactly as the skywrapped command line does; returns the summary dict.

    summary.json first, then card by card: the PNG is drawn (``png_renderer(svg, width) -> bytes``) and then that
    card's SVG and PNG are written; index.html last. This is the command line's own order (cli._write_cards), so a
    failure leaves the same files behind. Raises OutputFolderRefused for a folder with other files in it; whatever
    ``png_renderer`` raises (PngUnavailable) comes out with summary.json (and the cards drawn before it) written.
    """
    sw = _sw()
    out = str(out)
    if not sw.cli._prepare_out(out):
        raise OutputFolderRefused("Choose an empty output folder (or one skywrapped made before).")
    summary = sw.stats.to_summary(wrapped)
    sw.cli._clear_own(out)
    write_summary(out, summary)
    if json_only:
        return summary
    for stem, card in cards:
        png = png_renderer(card.svg, card.width)
        Path(out, f"{stem}.svg").write_text(card.svg, encoding="utf-8")
        Path(out, f"{stem}.png").write_bytes(png)
    sw.preview.write_preview(Path(out), [card for _, card in cards])
    return summary


# ---------------------------------------------------------------------------------------------------------------------
# Qt drawing of the cards (PyQt6's QtSvg), so no PNG library is needed
# ---------------------------------------------------------------------------------------------------------------------

_FONTS_DONE = False


def ensure_pyqt() -> None:
    """Import PyQt6.QtSvg, installing PyQt6 with Siril's installer first when it is missing."""
    try:
        import PyQt6.QtSvg  # noqa: F401
        return
    except ImportError:
        pass
    try:
        import sirilpy
        sirilpy.ensure_installed("PyQt6")
        importlib.invalidate_caches()
        import PyQt6.QtSvg  # noqa: F401
    except (Exception, SystemExit) as e:
        raise PngUnavailable("The cards are drawn with PyQt6, which could not be installed (it needs the internet "
                             "once). Connect to the internet and run the script again, or see "
                             f"{HOME_URL}") from e


_APP = None                                   # the application object must stay referenced, or Qt crashes


def qt_app(widgets: bool = True, headless: bool = False):
    """The one Qt application, made on first use (invisible, "offscreen", when ``headless``)."""
    global _APP
    ensure_pyqt()
    from PyQt6 import QtGui, QtWidgets
    app = QtGui.QGuiApplication.instance()
    if app is None:
        if headless:
            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        app = _APP = QtWidgets.QApplication(["SkyWrapped"]) if widgets else QtGui.QGuiApplication(["SkyWrapped"])
    return app


def register_fonts() -> None:
    """Give Qt skywrapped's three bundled fonts (Qt does not read the @font-face fonts inside the SVGs)."""
    global _FONTS_DONE
    if _FONTS_DONE:
        return
    from PyQt6 import QtGui
    for path in _sw().font_files():
        QtGui.QFontDatabase.addApplicationFont(path)
    _FONTS_DONE = True


_TEXT_RE = re.compile(r"<text\b([^>]*)>(.*?)</text>", re.S)
_ATTR_RE = re.compile(r'([\w:-]+)="([^"]*)"')
_TAG_RE = re.compile(r"<[A-Za-z][^<>]*>")
_OPACITY_OF = {"fill": "fill-opacity", "stroke": "stroke-opacity", "stop-color": "stop-opacity"}


def _rgba_parts(text: str):
    """``"255, 255, 255, 0.08"`` (or with % values) -> ("#ffffff", 0.08); None when it is not four numbers."""
    parts = [p.strip() for p in text.split(",")]
    if len(parts) != 4:
        return None
    try:
        rgb = [float(p[:-1]) * 2.55 if p.endswith("%") else float(p) for p in parts[:3]]
        alpha = float(parts[3][:-1]) / 100.0 if parts[3].endswith("%") else float(parts[3])
    except ValueError:
        return None
    r, g, b = (max(0, min(255, round(v))) for v in rgb)
    return f"#{r:02x}{g:02x}{b:02x}", max(0.0, min(1.0, alpha))


def _qt_tag_colors(tag: str) -> str:
    """One start tag with fill/stroke/stop-color="rgba(...)" written as "#rrggbb" plus the matching *-opacity
    (multiplied into an opacity the tag already has, so the attribute is never doubled)."""
    for prop, op in _OPACITY_OF.items():
        pat = re.compile(rf'(?<![\w-]){prop}="\s*rgba\(([^)"]*)\)\s*"')
        m = pat.search(tag)
        if not m:
            continue
        conv = _rgba_parts(m.group(1))
        if conv is None:
            continue
        colour, alpha = conv
        old = re.search(rf'\s{op}="([^"]*)"', tag)
        if old:
            try:
                alpha *= float(old.group(1))
            except ValueError:
                pass
            tag = tag[:old.start()] + tag[old.end():]
            m = pat.search(tag)
        tag = tag[:m.start()] + f'{prop}="{colour}" {op}="{alpha:.4g}"' + tag[m.end():]
    return tag


def qt_colors(svg: str) -> str:
    """QtSvg follows SVG Tiny 1.2, which has no rgba(): Qt paints such a fill solid black (the Nebula theme's empty
    calendar nights and target-bar tracks). Write every rgba() fill/stroke/stop-color as a colour plus an opacity."""
    if "rgba(" not in svg:
        return svg
    return _TAG_RE.sub(lambda m: _qt_tag_colors(m.group(0)) if "rgba(" in m.group(0) else m.group(0), svg)


def qt_ready_svg(svg: str, advance=None) -> str:
    """The same card, adjusted for QtSvg, which differs from skywrapped's own PNG renderer (resvg) in three ways.

    * rgba() colours: Qt has none and paints them black, so they become a colour plus an opacity (qt_colors).
    * font-family: Qt reads the whole attribute as one name, so ``'Skywrapped EB Garamond', serif`` finds no font and
      the serif headings come out in the default sans. Only the first family is kept.
    * letter-spacing: Qt ignores it, so the tracked capitals and the big numbers would look different. A tracked
      text is split into one <text> per letter, placed with ``advance(family, weight, char)`` (the letter's width as a
      fraction of the font size). Anchors (start, middle, end) are worked out from the full width.
    """
    svg = qt_colors(svg)

    def one(m):
        attrs = dict(_ATTR_RE.findall(m.group(1)))
        body = m.group(2)
        family = attrs.get("font-family", "")
        if family:
            attrs["font-family"] = re.sub(r"^\s*['\"]?([^'\",]+?)['\"]?\s*(,.*)?$", r"\1", family, flags=re.S)
        try:
            spacing = float(attrs.get("letter-spacing") or 0)
        except ValueError:
            spacing = 0.0
        if not spacing or "<" in body or advance is None:
            return "<text " + " ".join(f'{k}="{v}"' for k, v in attrs.items()) + f">{body}</text>"
        text = unescape_xml(body)
        size = float(attrs.get("font-size", 16))
        weight = int(float(attrs.get("font-weight", 400)))
        widths = [advance(attrs.get("font-family", ""), weight, ch) * size + spacing for ch in text]
        total = sum(widths)
        x = float(attrs.get("x", 0))
        anchor = attrs.pop("text-anchor", "start")
        x -= total if anchor == "end" else total / 2 if anchor == "middle" else 0.0
        keep = {k: v for k, v in attrs.items() if k not in ("x", "letter-spacing")}
        tail = " ".join(f'{k}="{v}"' for k, v in keep.items())
        out = []
        for ch, w in zip(text, widths):
            if not ch.isspace():
                out.append(f'<text x="{x:.2f}" {tail}>{escape_xml(ch)}</text>')
            x += w
        return "".join(out)
    return _TEXT_RE.sub(one, svg)


def unescape_xml(s: str) -> str:
    return s.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&apos;", "'").replace("&amp;", "&")


def escape_xml(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


_ADV = {}


def qt_advance(family: str, weight: int, ch: str) -> float:
    """A letter's width as a fraction of the font size, measured by Qt with skywrapped's registered fonts."""
    from PyQt6 import QtGui
    key = (family, weight)
    if key not in _ADV:
        font = QtGui.QFont(family)
        font.setPixelSize(200)
        try:
            font.setWeight(QtGui.QFont.Weight(weight))
        except ValueError:
            pass
        _ADV[key] = QtGui.QFontMetricsF(font)
    return _ADV[key].horizontalAdvance(ch) / 200.0


def qt_renderer(svg: str, parent=None):
    """A QSvgRenderer for one card (adjusted by qt_ready_svg). The Qt application and the fonts must be set up."""
    from PyQt6 import QtCore, QtSvg
    renderer = QtSvg.QSvgRenderer(QtCore.QByteArray(qt_ready_svg(svg, qt_advance).encode("utf-8")), parent)
    if not renderer.isValid():
        raise PngUnavailable("Qt could not read a card's drawing.")
    return renderer


def svg_to_png_qt(svg: str, width: int) -> bytes:
    """One card as PNG bytes, drawn by Qt (the same call as skywrapped's own ``render_png.svg_to_png``)."""
    qt_app(widgets=False, headless=True)
    register_fonts()
    from PyQt6 import QtCore, QtGui
    renderer = qt_renderer(svg)
    size = renderer.defaultSize()
    w = int(width)
    h = max(1, round(w * size.height() / size.width()))
    image = QtGui.QImage(w, h, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    painter = QtGui.QPainter(image)
    painter.setRenderHints(QtGui.QPainter.RenderHint.Antialiasing | QtGui.QPainter.RenderHint.TextAntialiasing
                           | QtGui.QPainter.RenderHint.SmoothPixmapTransform)
    renderer.render(painter)
    painter.end()
    buf = QtCore.QBuffer()
    buf.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buf, "PNG"):
        raise PngUnavailable("Qt could not save a card as PNG.")
    return bytes(buf.data())


# ---------------------------------------------------------------------------------------------------------------------
# The typed command: pyscript SkyWrapped.py <folder> ...
# ---------------------------------------------------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pyscript SkyWrapped.py",
        description="Turn a folder of astrophotography light frames into year-in-astro cards. Reads FITS/XISF headers "
                    "only; nothing leaves this computer.")
    p.add_argument("paths", nargs="*", metavar="FOLDER", help="folders (or files) of light frames")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--year", type=int, default=None, help="calendar year to count (default: this year)")
    g.add_argument("--all", action="store_true", help="count every year")
    p.add_argument("--theme", choices=THEMES, default="observatory")
    p.add_argument("--out", default=None, help="output folder (default: skywrapped-<year> in your Documents folder)")
    p.add_argument("--exclude", action="append", default=[], metavar="GLOB",
                   help="skip files whose path matches this pattern (repeatable)")
    p.add_argument("--default-excludes", action="store_true",
                   help="also skip " + ", ".join(DEFAULT_EXCLUDES) + " (the window's own skip list)")
    p.add_argument("--tz", type=float, default=None, metavar="HOURS",
                   help="your UTC offset in hours, e.g. -5 or 5.5 (default: this computer's)")
    p.add_argument("--json-only", action="store_true", help="write summary.json only")
    return p


def plan_from_args(ns, today: date | None = None) -> SimpleNamespace:
    """The year (None = every year), UTC offset and skip list a typed command asks for."""
    today = today or date.today()
    year = None if ns.all else (ns.year if ns.year is not None else today.year)
    tz = ns.tz if ns.tz is not None else local_offset_hours()
    excludes = (list(DEFAULT_EXCLUDES) if ns.default_excludes else []) + list(ns.exclude)
    return SimpleNamespace(year=year, tz=tz, excludes=excludes)


def run_headless(argv, say=say_default, png_renderer=None, install: bool = True) -> int:
    """The typed command. Same steps, same wording and same exit codes as the skywrapped command line. Returns the code."""
    ns = build_parser().parse_args(argv)
    if not ns.paths:
        say("Give the folder of light frames, e.g.  pyscript SkyWrapped.py /path/to/lights --all\n"
            + build_parser().format_usage(), "error")
        return EXIT_NOTHING
    try:
        sw = load_skywrapped(say, install=install)
    except SetupError as e:
        say(str(e), "error")
        return EXIT_SETUP
    say(f"SkyWrapped {VERSION}, skywrapped {sw.version}")
    plan = plan_from_args(ns)
    paths = [os.path.expanduser(p) for p in ns.paths]       # a shell expands ~ for the CLI; Siril's command line does not
    if ns.out:
        out = os.path.expanduser(ns.out)
        if not output_ok(out):
            say("Choose an empty output folder (or one skywrapped made before).", "error")
            return EXIT_BAD_OUT
    else:
        out = str(free_output_dir(plan.year))
    missing = [p for p in paths if not os.path.exists(p)]
    if missing:
        n = len(missing)
        say(f"{n} of the given paths {'does' if n == 1 else 'do'} not exist.", "error")
        return EXIT_NOTHING

    def progress(done, total):
        if done % sw.cli.PROGRESS_EVERY == 0 or done == total:
            say(f"Read {done:,} of {total:,} files")

    frames, skipped = scan_frames(paths, plan.excludes, progress)
    try:
        wrapped = count_year(frames, skipped, plan.year, plan.tz)
    except sw.stats.NoLightsError as e:
        say(sw.cli._no_lights(plan.year, e.years), "error")
        return EXIT_NOTHING
    cards = [] if ns.json_only else draw_cards(wrapped, ns.theme)
    if png_renderer is None:
        png_renderer = svg_to_png_qt
    try:
        summary = write_output(out, wrapped, cards, png_renderer, json_only=ns.json_only)
    except PngUnavailable as e:
        say(str(e), "error")
        return EXIT_NO_PNG
    except OutputFolderRefused as e:
        say(str(e), "error")
        return EXIT_BAD_OUT
    say(sw.cli._final_line(summary), "good")
    say(f"Saved to {out}")
    return EXIT_OK


# ---------------------------------------------------------------------------------------------------------------------
# The window (Scripts menu)
# ---------------------------------------------------------------------------------------------------------------------

_GUI = None


def _build_gui():
    """Define the window's classes (PyQt6 is imported only here, so the helpers above work without it)."""
    global _GUI
    if _GUI is not None:
        return _GUI
    from PyQt6 import QtCore, QtGui, QtWidgets
    from PyQt6.QtCore import Qt, pyqtSignal

    ACCENT, OK_C, BAD_C, DIM = "#4a8fe7", "#62c370", "#e0605c", "#9aa1aa"
    QSS = f"""
    QWidget {{ font-size: 13px; }}
    QLabel#Title {{ font-size: 26px; font-weight: 600; }}
    QLabel#Sub, QLabel#Hint {{ color: {DIM}; font-size: 12px; }}
    QLabel#Foot {{ color: #7f8690; font-size: 11px; }}
    QLabel#Status {{ color: #d5d9df; }}
    QLabel#Placeholder {{ color: #7f8690; font-size: 15px; }}
    QFrame#Preview {{ background: #1c1e21; border: 1px solid #3a3e45; border-radius: 6px; }}
    QGroupBox {{ border: 1px solid #3a3e45; border-radius: 6px; margin-top: 12px; padding: 12px 8px 8px 8px; }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #b9c0ca; }}
    QPushButton {{ padding: 5px 14px; }}
    QPushButton#Run {{ background: {ACCENT}; color: white; font-weight: 600; padding: 6px 26px; border-radius: 4px;
                      border: none; }}
    QPushButton#Run:disabled {{ background: #3a3e45; color: #7a7f87; }}
    QProgressBar {{ border: 1px solid #3a3e45; border-radius: 4px; background: #222528; max-height: 9px; }}
    QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}
    QPlainTextEdit {{ font-family: Menlo, Consolas, monospace; font-size: 12px; }}
    QListWidget {{ background: #1c1e21; border: none; }}
    QListWidget::item {{ color: #b9c0ca; padding: 2px; }}
    QListWidget::item:selected {{ background: #2f3f58; color: white; border-radius: 4px; }}
    QScrollArea {{ border: none; }}
    QRadioButton::indicator {{ width: 13px; height: 13px; border-radius: 7px; border: 1px solid #7f8690;
                              background: #23262a; }}
    QRadioButton::indicator:checked {{ border-color: {ACCENT}; background: qradialgradient(cx:0.5, cy:0.5, radius:0.5,
        fx:0.5, fy:0.5, stop:0 {ACCENT}, stop:0.5 {ACCENT}, stop:0.55 #23262a, stop:1 #23262a); }}
    QFrame#Rule {{ background: #3a3e45; max-height: 1px; border: none; }}
    """

    def dark_theme(app):
        """A dark Fusion look like Siril's own script windows, the same on any system appearance."""
        app.setStyle("Fusion")
        pal, C, R = QtGui.QPalette(), QtGui.QColor, QtGui.QPalette.ColorRole
        for role, col in ((R.Window, "#2e3135"), (R.WindowText, "#e4e7eb"), (R.Base, "#23262a"),
                          (R.AlternateBase, "#292c30"), (R.Text, "#e4e7eb"), (R.Button, "#3a3e45"),
                          (R.ButtonText, "#e4e7eb"), (R.Highlight, ACCENT), (R.HighlightedText, "#ffffff"),
                          (R.ToolTipBase, "#23262a"), (R.ToolTipText, "#e4e7eb"), (R.PlaceholderText, "#7f8690")):
            pal.setColor(role, C(col))
        for role in (R.Text, R.WindowText, R.ButtonText):
            pal.setColor(QtGui.QPalette.ColorGroup.Disabled, role, C("#6c727a"))
        app.setPalette(pal)
        app.setStyleSheet(QSS)

    class SetupWorker(QtCore.QThread):
        """Install (first run) and import skywrapped without freezing the window."""
        ready = pyqtSignal(str)
        failed = pyqtSignal(str)

        def __init__(self, say):
            super().__init__()
            self.say = say

        def run(self):
            try:
                sw = load_skywrapped(self.say)
                self.ready.emit(sw.version)
            except SetupError as e:
                self.failed.emit(str(e))
            except Exception as e:                              # never leave the window waiting
                self.failed.emit(f"{type(e).__name__}: {e}")

    class ScanWorker(QtCore.QThread):
        """Read the headers, count the year and draw the cards, off the window's thread."""
        progress = pyqtSignal(int, int)
        done = pyqtSignal(object)                              # dict: wrapped, summary, cards, year, theme
        failed = pyqtSignal(str, object)                       # "cancelled" | "no_lights" | "error", extra

        def __init__(self, paths, excludes, year, tz, theme):
            super().__init__()
            self.paths, self.excludes, self.year, self.tz, self.theme = paths, excludes, year, tz, theme
            self._stop = threading.Event()
            self._last = 0.0

        def cancel(self):
            self._stop.set()

        def _tick(self, done, total):
            now = time.monotonic()
            if done == total or now - self._last > 0.05:      # 38,000 files: the window needs a dozen updates a second
                self._last = now
                self.progress.emit(done, total)

        def _check(self):
            """Cancel is honoured between the steps too, not only while files are read."""
            if self._stop.is_set():
                raise Cancelled()

        def run(self):
            sw = _sw()
            skipped = {}
            try:
                frames, skipped = scan_frames(self.paths, self.excludes, self._tick, self._stop.is_set)
                self._check()
                wrapped = count_year(frames, skipped, self.year, self.tz)
                self._check()
                result = dict(wrapped=wrapped, summary=sw.stats.to_summary(wrapped), year=self.year,
                              cards=draw_cards(wrapped, self.theme), theme=self.theme)
                self._check()
                self.done.emit(result)
            except Cancelled:
                self.failed.emit("cancelled", None)
            except sw.stats.NoLightsError as e:
                self.failed.emit("no_lights", dict(years=e.years, year=self.year, skipped=skipped))
            except Exception as e:                              # never leave the window waiting
                self.failed.emit("error", f"{type(e).__name__}: {e}")

    class BigLabel(QtWidgets.QLabel):
        """The large card; tells the viewer when it was resized so the card is drawn again at the new size."""
        resized = pyqtSignal()

        def resizeEvent(self, e):
            super().resizeEvent(e)
            self.resized.emit()

    class Viewer(QtWidgets.QWidget):
        """The cards: one large, the others as a strip of thumbnails underneath (QSvgRenderer draws both)."""

        THUMB_H = 92

        def __init__(self):
            super().__init__()
            self.renderers, self.names = [], []
            self.stack = QtWidgets.QStackedLayout(self)
            self.placeholder = QtWidgets.QLabel("Your cards will appear here.\nChoose a folder and press Run.")
            self.placeholder.setObjectName("Placeholder")
            self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            page = QtWidgets.QWidget()
            lay = QtWidgets.QVBoxLayout(page)
            lay.setContentsMargins(0, 0, 0, 0)
            self.big = BigLabel()
            self.big.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.big.setMinimumSize(300, 300)
            self.big.setSizePolicy(QtWidgets.QSizePolicy.Policy.Ignored, QtWidgets.QSizePolicy.Policy.Ignored)
            self.big.resized.connect(lambda: self._paint(self.strip.currentRow()))
            self.strip = QtWidgets.QListWidget()
            self.strip.setViewMode(QtWidgets.QListView.ViewMode.IconMode)
            self.strip.setFlow(QtWidgets.QListView.Flow.LeftToRight)
            self.strip.setWrapping(False)
            self.strip.setMovement(QtWidgets.QListView.Movement.Static)
            self.strip.setIconSize(QtCore.QSize(int(self.THUMB_H * 1.2), self.THUMB_H))   # a portrait card or the poster
            self.strip.setFixedHeight(self.THUMB_H + 46)
            self.strip.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self.strip.currentRowChanged.connect(self._paint)
            lay.addWidget(self.big, 1)
            lay.addWidget(self.strip)
            self.stack.addWidget(self.placeholder)
            self.stack.addWidget(page)

        def clear(self):
            self.renderers, self.names = [], []
            self.strip.clear()
            self.stack.setCurrentIndex(0)

        def set_cards(self, cards, keep_row=0):
            """``cards``: [(stem, Card)]."""
            self.renderers, self.names = [], []
            self.strip.blockSignals(True)
            self.strip.clear()
            for stem, card in cards:
                r = qt_renderer(card.svg, self)
                self.renderers.append(r)
                self.names.append(card_title(card.name))
                item = QtWidgets.QListWidgetItem(QtGui.QIcon(self._pixmap(r, self.THUMB_H * 2, self.THUMB_H * 2)),
                                                 self.names[-1])
                item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
                self.strip.addItem(item)
            self.strip.blockSignals(False)
            self.stack.setCurrentIndex(1)
            self.strip.setCurrentRow(min(max(keep_row, 0), len(cards) - 1) if cards else -1)
            self._paint(self.strip.currentRow())

        def _pixmap(self, renderer, max_w, max_h, dpr: float = 1.0):
            """The card scaled to fit max_w x max_h (device pixels at ``dpr``)."""
            ds = renderer.defaultSize()
            scale = min(max_w / ds.width(), max_h / ds.height())
            w, h = max(1, int(ds.width() * scale)), max(1, int(ds.height() * scale))
            image = QtGui.QImage(int(w * dpr), int(h * dpr), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(0)
            painter = QtGui.QPainter(image)
            painter.setRenderHints(QtGui.QPainter.RenderHint.Antialiasing | QtGui.QPainter.RenderHint.TextAntialiasing
                                   | QtGui.QPainter.RenderHint.SmoothPixmapTransform)
            renderer.render(painter)
            painter.end()
            image.setDevicePixelRatio(dpr)
            return QtGui.QPixmap.fromImage(image)

        def _paint(self, row):
            if not 0 <= row < len(self.renderers):
                return
            dpr = self.devicePixelRatioF()
            self.big.setPixmap(self._pixmap(self.renderers[row], self.big.width() - 4, self.big.height() - 4, dpr))

    class Window(QtWidgets.QWidget):
        """SkyWrapped's window. ``siril`` may be None (the window then works the same, without Siril's console)."""
        finished = pyqtSignal(str)                             # the end state of a run: "ok", "cancelled", ... (tests)

        def __init__(self, siril=None, folder: str = "", say=None, start_setup: bool = True):
            super().__init__()
            self.siril = siril
            self.say = say or say_default
            self.worker = self.setup = None
            self.end = None
            self.result = None                                 # the last run: wrapped, summary, cards, year, theme
            self.ready = False
            self.saved_to = None
            self.save_parent = str(documents_dir())
            self.this_year = date.today().year
            self.setWindowTitle("SkyWrapped - your year in astro")
            self._build(folder)
            self._set_state()
            if start_setup:
                self.start_setup()

        # ---- layout
        def _build(self, folder):
            left = QtWidgets.QWidget()
            left.setFixedWidth(430)
            col = QtWidgets.QVBoxLayout(left)
            col.setContentsMargins(14, 12, 14, 12)
            col.setSpacing(8)

            title = QtWidgets.QLabel("SkyWrapped")
            title.setObjectName("Title")
            sub = QtWidgets.QLabel("Your year in astro, from the headers of your light frames. "
                                   "Only headers are read; nothing is uploaded.")
            sub.setObjectName("Sub")
            sub.setWordWrap(True)
            self.banner = QtWidgets.QLabel()
            self.banner.setWordWrap(True)
            self.retry = QtWidgets.QPushButton("Try again")
            self.retry.clicked.connect(self.start_setup)
            col.addWidget(title)
            col.addWidget(sub)
            col.addWidget(self.banner)
            col.addWidget(self.retry, 0, Qt.AlignmentFlag.AlignLeft)

            box = QtWidgets.QGroupBox("Lights folder")
            g = QtWidgets.QVBoxLayout(box)
            row = QtWidgets.QHBoxLayout()
            self.folder = QtWidgets.QLineEdit(folder)
            self.folder.setPlaceholderText("The folder with your light frames")
            self.folder.setToolTip("Subfolders are searched. FITS (.fit .fits .fts .fz) and XISF files are read, "
                                   "headers only.")
            self.folder.textChanged.connect(lambda _t: self._set_state())
            self.choose_btn = QtWidgets.QPushButton("Choose...")
            self.choose_btn.clicked.connect(self.choose_folder)
            row.addWidget(self.folder, 1)
            row.addWidget(self.choose_btn)
            g.addLayout(row)
            row2 = QtWidgets.QHBoxLayout()
            self.parent_btn = QtWidgets.QPushButton("Use the parent folder")
            self.parent_btn.setToolTip("Siril's working folder is usually one session or one target. "
                                       "The folder above it holds more of your year.")
            self.parent_btn.clicked.connect(self.use_parent)
            hint = QtWidgets.QLabel("Siril's working folder is often a single session. "
                                    "For the whole year, use the folder above.")
            hint.setObjectName("Hint")
            hint.setWordWrap(True)
            row2.addWidget(self.parent_btn)
            row2.addWidget(hint, 1)
            g.addLayout(row2)
            col.addWidget(box)

            box = QtWidgets.QGroupBox("What to count")
            g = QtWidgets.QGridLayout(box)
            g.setHorizontalSpacing(10)
            self.r_this = QtWidgets.QRadioButton(f"This year ({self.this_year})")
            self.r_year = QtWidgets.QRadioButton("A year:")
            self.r_all = QtWidgets.QRadioButton("All years")
            self.r_this.setChecked(True)
            self.year_spin = QtWidgets.QSpinBox()
            self.year_spin.setRange(1990, self.this_year)
            self.year_spin.setValue(self.this_year - 1)
            self.year_spin.setButtonSymbols(QtWidgets.QAbstractSpinBox.ButtonSymbols.NoButtons)
            self.year_spin.setFixedWidth(70)
            self.year_spin.setGroupSeparatorShown(False)
            self.year_spin.valueChanged.connect(lambda _v: self.r_year.setChecked(True))
            yrow = QtWidgets.QHBoxLayout()
            yrow.addWidget(self.r_this)
            yrow.addWidget(self.r_year)
            yrow.addWidget(self.year_spin)
            yrow.addWidget(self.r_all)
            yrow.addStretch(1)
            g.addLayout(yrow, 0, 0, 1, 2)
            for r in (self.r_this, self.r_year, self.r_all):
                r.toggled.connect(self._refresh_out)
            self.theme = QtWidgets.QComboBox()
            self.theme.addItem("Observatory", "observatory")
            self.theme.addItem("Nebula", "nebula")
            self.theme.currentIndexChanged.connect(self.theme_changed)
            self.tz = QtWidgets.QDoubleSpinBox()
            self.tz.setRange(-14.0, 14.0)
            self.tz.setDecimals(2)
            self.tz.setSingleStep(0.5)
            self.tz.setSuffix(" h")
            self.tz.setValue(local_offset_hours())
            self.tz.setToolTip("Your time zone, as hours from UTC (for example -5, or 5.5). It decides which evening a "
                               "frame belongs to, so a night that runs past midnight counts once. "
                               "Starts at this computer's setting.")
            g.addWidget(QtWidgets.QLabel("Theme"), 1, 0)
            g.addWidget(self.theme, 1, 1)
            g.addWidget(QtWidgets.QLabel("UTC offset"), 2, 0)
            g.addWidget(self.tz, 2, 1)
            g.setColumnStretch(1, 1)
            col.addWidget(box)

            box = QtWidgets.QGroupBox("Skip files whose path matches")
            g = QtWidgets.QVBoxLayout(box)
            self.excludes = QtWidgets.QPlainTextEdit("\n".join(DEFAULT_EXCLUDES))
            self.excludes.setFixedHeight(64)
            self.excludes.setToolTip("One pattern per line; * matches anything. Rejected subs and preview pictures "
                                     "are left out by default.")
            self.reset_btn = QtWidgets.QPushButton("Reset the list")
            self.reset_btn.clicked.connect(lambda: self.excludes.setPlainText("\n".join(DEFAULT_EXCLUDES)))
            g.addWidget(self.excludes)
            g.addWidget(self.reset_btn, 0, Qt.AlignmentFlag.AlignLeft)
            col.addWidget(box)

            row = QtWidgets.QHBoxLayout()
            self.run_btn = QtWidgets.QPushButton("Run")
            self.run_btn.setObjectName("Run")
            self.run_btn.setDefault(True)
            self.run_btn.clicked.connect(self.run)
            self.cancel_btn = QtWidgets.QPushButton("Cancel")
            self.cancel_btn.clicked.connect(self.cancel)
            row.addWidget(self.run_btn)
            row.addWidget(self.cancel_btn)
            row.addStretch(1)
            col.addLayout(row)
            self.bar = QtWidgets.QProgressBar()
            self.bar.setTextVisible(False)
            self.bar.setRange(0, 1)
            self.bar.setValue(0)
            col.addWidget(self.bar)
            self.status = QtWidgets.QLabel("")
            self.status.setObjectName("Status")
            self.status.setWordWrap(True)
            self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            col.addWidget(self.status)

            self.foot = QtWidgets.QLabel(f'skywrapped - <a href="{HOME_URL}" style="color:{ACCENT}">'
                                         f'github.com/aousabdo/skywrapped</a>')
            self.foot.setObjectName("Foot")
            self.foot.setOpenExternalLinks(True)
            col.addWidget(self.foot)
            col.addStretch(1)

            scroll = QtWidgets.QScrollArea()                   # a Qt top-level squeezes wrapped labels; a scroll area does not
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroll.setWidget(left)
            scroll.setFixedWidth(430 + 18)
            self.left_scroll = scroll

            frame = QtWidgets.QFrame()
            frame.setObjectName("Preview")
            fl = QtWidgets.QVBoxLayout(frame)
            fl.setContentsMargins(10, 10, 10, 10)
            self.result_label = QtWidgets.QLabel("")
            self.result_label.setObjectName("Status")
            self.result_label.setTextFormat(Qt.TextFormat.PlainText)
            self.result_label.setWordWrap(True)
            self.result_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.viewer = Viewer()
            fl.addWidget(self.result_label)
            fl.addWidget(self.viewer, 1)
            self.save_panel = QtWidgets.QWidget()
            sp = QtWidgets.QVBoxLayout(self.save_panel)
            sp.setContentsMargins(0, 4, 0, 0)
            sp.setSpacing(6)
            rule = QtWidgets.QFrame()
            rule.setObjectName("Rule")
            sp.addWidget(rule)
            row = QtWidgets.QHBoxLayout()
            self.save_parent_edit = QtWidgets.QLineEdit(self.save_parent)
            self.save_parent_edit.setReadOnly(True)
            self.change_btn = QtWidgets.QPushButton("Change...")
            self.change_btn.clicked.connect(self.change_save_parent)
            row.addWidget(QtWidgets.QLabel("Save in"))
            row.addWidget(self.save_parent_edit, 1)
            row.addWidget(self.change_btn)
            sp.addLayout(row)
            self.out_label = QtWidgets.QLabel("")
            self.out_label.setObjectName("Hint")
            self.out_label.setTextFormat(Qt.TextFormat.PlainText)
            self.out_label.setWordWrap(True)
            sp.addWidget(self.out_label)
            row = QtWidgets.QHBoxLayout()
            self.save_btn = QtWidgets.QPushButton("Save PNGs")
            self.save_btn.setObjectName("Run")
            self.save_btn.setToolTip("Saves the PNG cards and poster, their SVG files, summary.json and a small "
                                     "index.html into a new folder.")
            self.save_btn.clicked.connect(self.save)
            self.open_btn = QtWidgets.QPushButton("Open output folder")
            self.open_btn.clicked.connect(self.open_output)
            row.addWidget(self.save_btn)
            row.addWidget(self.open_btn)
            row.addStretch(1)
            sp.addLayout(row)
            fl.addWidget(self.save_panel)

            outer = QtWidgets.QHBoxLayout(self)
            outer.setContentsMargins(0, 0, 12, 12)
            outer.addWidget(scroll)
            outer.addWidget(frame, 1)
            self.setMinimumSize(940, 600)
            self.resize(1060, 720)
            self._refresh_out()

        # ---- state
        def _year(self):
            """The year to count: None means every year."""
            if self.r_all.isChecked():
                return None
            return self.year_spin.value() if self.r_year.isChecked() else self.this_year

        def _running(self):
            return self.worker is not None and self.worker.isRunning()

        def _set_state(self):
            running = self._running()
            self.run_btn.setEnabled(self.ready and not running)
            self.cancel_btn.setEnabled(running)
            self.save_panel.setVisible(self.result is not None)
            self.save_btn.setEnabled(self.result is not None and not running)
            self.open_btn.setEnabled(self.saved_to is not None and Path(self.saved_to).is_dir())
            self.parent_btn.setEnabled(bool(self.folder.text().strip()) and not running)
            for w in (self.folder, self.choose_btn, self.excludes, self.reset_btn, self.year_spin, self.tz,
                      self.r_this, self.r_year, self.r_all, self.theme, self.change_btn):
                w.setEnabled(not running)              # what is on screen always matches the run being made

        def _banner(self, text, color=DIM, retry=False):
            self.banner.setText(f'<span style="color:{color}">{html.escape(text)}</span>')    # labels read HTML: a path may hold < or &
            self.retry.setVisible(retry)

        def _status(self, text, color=None):
            text = html.escape(text)
            self.status.setText(text if color is None else f'<span style="color:{color}">{text}</span>')

        # ---- setup (the first run installs skywrapped)
        def start_setup(self):
            if self.setup is not None and self.setup.isRunning():
                return
            self.ready = False
            self._banner("Getting ready. The first run downloads the small skywrapped package, so it needs the "
                         "internet once.")
            self._set_state()
            self.setup = SetupWorker(say_default)             # a thread: print, never Siril's socket
            self.setup.ready.connect(self._setup_ready)
            self.setup.failed.connect(self._setup_failed)
            self.setup.start()

        def _setup_ready(self, version):
            register_fonts()
            self.ready = True
            self._banner(f"skywrapped {version} is ready.", OK_C)
            self.foot.setText(f'skywrapped {version} - <a href="{HOME_URL}" style="color:{ACCENT}">'
                              f'github.com/aousabdo/skywrapped</a>')
            self._set_state()
            self._refresh_out()

        def _setup_failed(self, message):
            self.ready = False
            self._banner(message, BAD_C, retry=True)
            self._set_state()

        # ---- folders
        def choose_folder(self):
            start = self.folder.text().strip() or str(Path.home())
            d = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose the folder with your light frames", start)
            if d:
                self.folder.setText(d)
                self._set_state()

        def use_parent(self):
            p = Path(self.folder.text().strip()).expanduser()
            self.folder.setText(str(p.parent))
            self._set_state()

        def change_save_parent(self):
            d = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose where to save the cards", self.save_parent)
            if d:
                self.save_parent = d
                self.save_parent_edit.setText(d)
                self._refresh_out()

        def _out_year(self):
            return self.result["year"] if self.result is not None else self._year()

        def _out_dir(self):
            """The folder Save would write: skywrapped-<year> in the chosen place, or -2, -3 ... if that name is taken."""
            return free_output_dir(self._out_year(), self.save_parent)

        def _refresh_out(self, *_):
            if not self.ready:
                self.out_label.setText("")
                return
            try:
                self.out_label.setText(f"The cards go into  {self._out_dir()}")
            except OutputFolderRefused as e:
                self.out_label.setText(str(e))

        # ---- run
        def run(self):
            if not self.ready or self._running():
                return
            folder = Path(self.folder.text().strip()).expanduser()
            if not self.folder.text().strip() or not folder.is_dir():
                self._status("That folder does not exist. Choose the folder with your light frames.", BAD_C)
                return
            year, theme = self._year(), self.theme.currentData()
            self.result, self.saved_to = None, None
            self.result_label.setText("")
            self.viewer.clear()
            self.bar.setRange(0, 0)                           # busy: the folder is being listed
            self._status("Looking for light frames...")
            self.worker = ScanWorker([str(folder)], parse_excludes(self.excludes.toPlainText()), year,
                                     self.tz.value(), theme)
            self.worker.progress.connect(self._progress)
            self.worker.done.connect(self._done)
            self.worker.failed.connect(self._failed)
            self.worker.finished.connect(self._worker_finished)
            self.end = None
            self.worker.start()
            self._set_state()

        def cancel(self):
            if self._running() and self.end is None:           # not once the result has arrived (the thread may still be ending)
                self.worker.cancel()
                self.cancel_btn.setEnabled(False)
                self._status("Cancelling...")

        def _progress(self, done, total):
            if self.bar.maximum() != total:
                self.bar.setRange(0, max(total, 1))
            self.bar.setValue(done)
            self._status(f"Reading headers: {done:,} of {total:,} files")

        def _done(self, result):
            if self.worker is not None and self.worker._stop.is_set():   # Cancel pressed as the result was on its way
                self._failed("cancelled", None)
                return
            self.result, self.end = result, "ok"
            line = _sw().cli._final_line(result["summary"])
            self.bar.setRange(0, 1)
            self.bar.setValue(1)
            self._status("Done. Press Save PNGs to keep the cards.", OK_C)
            self.result_label.setText(f"{'All years' if result['year'] is None else result['year']}:  {line}")
            self.viewer.set_cards(result["cards"])
            self._refresh_out()
            self.cancel_btn.setEnabled(False)                  # nothing left to cancel; the thread is only ending
            self.say(f"SkyWrapped: {line}", "good")

        def _failed(self, kind, extra):
            self.end = kind
            self.bar.setRange(0, 1)
            self.bar.setValue(0)
            if kind == "cancelled":
                self._status("Cancelled. Nothing was saved.")
            elif kind == "no_lights":
                self._status(self._no_lights_text(extra), BAD_C)
            else:
                self._status(f"Something went wrong: {extra}", BAD_C)

        def _worker_finished(self):
            """The run's thread has ended (a moment after its result arrived): buttons settle, tests are told."""
            self._set_state()
            self.finished.emit(self.end or "error")

        @staticmethod
        def _no_lights_text(info):
            years = sorted(info["years"])
            if info["year"] is not None and years:
                text = (f"No light frames from {info['year']}. This folder has lights from "
                        f"{', '.join(map(str, years))}: pick one of those, or All years.")
            else:
                text = ("No light frames found. Check the folder (Siril's working folder is often just one session: try "
                        "the parent folder) and the skip list.")
            n = info["skipped"].get("excluded", 0) if info.get("skipped") else 0
            if n:
                text += f" {n:,} file{'s' if n != 1 else ''} matched the skip list."
            return text

        # ---- results
        def theme_changed(self, _i):
            """Another theme re-draws the cards already counted; nothing is read again."""
            if self.result is None or self._running():
                return
            theme = self.theme.currentData()
            self.result["cards"] = draw_cards(self.result["wrapped"], theme)
            self.result["theme"] = theme
            self.viewer.set_cards(self.result["cards"], keep_row=self.viewer.strip.currentRow())

        def save(self):
            if self.result is None:
                return
            # No busy cursor here: Qt's wait cursor on macOS (Siril 1.4.5's PyQt6 6.11) crashes Python with signal 11,
            # either when it is set or when it is freed as the script ends ("Python quit unexpectedly"). Reproduced
            # 3 times out of 4 with setOverrideCursor(WaitCursor) alone, 2026-11-23; never without it.
            self.save_btn.setEnabled(False)
            self._status("Saving the cards...")
            QtWidgets.QApplication.processEvents()
            try:
                out = self._out_dir()
                write_output(out, self.result["wrapped"], self.result["cards"], svg_to_png_qt)
            except (OutputFolderRefused, PngUnavailable, OSError) as e:
                self._status(f"Could not save: {e}", BAD_C)
                self.say(f"SkyWrapped: could not save: {e}", "error")
                self._set_state()
                return
            self.saved_to = str(out)
            n = len(self.result["cards"])
            self._status(f"Saved {n} cards, summary.json and index.html to {out}", OK_C)
            self.say(f"SkyWrapped: saved {n} cards to {out}", "good")
            self._set_state()

        def open_output(self):
            if self.saved_to:
                QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(self.saved_to))

        def closeEvent(self, e):
            if self.setup is not None and self.setup.isRunning():
                e.ignore()                                    # never abandon a half-finished pip install
                self._banner("Still installing skywrapped. Please wait a moment, then close the window.")
                return
            if self._running():
                self.worker.cancel()
                if not self.worker.wait(15000):               # it stops at the next file; listing a huge folder cannot
                    e.ignore()                                # be interrupted, and a thread still running at exit crashes
                    self._status("Still stopping: the folder is still being listed. Close the window again in a "
                                 "moment.")
                    return
            super().closeEvent(e)

    _GUI = SimpleNamespace(Window=Window, dark_theme=dark_theme)
    return _GUI


def run_window(siril) -> None:
    """Open the window and wait for it to close."""
    say = siril_say(siril) if siril is not None else say_default
    app = qt_app(widgets=True)
    gui = _build_gui()
    gui.dark_theme(app)
    folder = ""
    if siril is not None:
        try:
            folder = siril.get_siril_wd() or ""
        except Exception:
            folder = ""
    win = gui.Window(siril, folder, say)

    def on_error(kind, value, tb):
        """An error inside a button's code would make PyQt6 abort the whole script: show it instead."""
        say(f"SkyWrapped: {kind.__name__}: {value}", "error")
        try:
            win._status(f"Something went wrong: {kind.__name__}: {value}", "#e0605c")
        except Exception:
            pass
    sys.excepthook = on_error
    win.show()
    win.raise_()
    win.activateWindow()
    app.exec()


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    siril = None
    try:
        import sirilpy as s
        siril = s.SirilInterface()
        if not siril.connect():
            siril = None
    except Exception:
        siril = None
    say = siril_say(siril) if siril is not None else say_default
    # A folder given means the typed command. No folder opens the window, from the Scripts menu or typed in Siril's
    # own command line (as other Siril scripts do), except where there is no screen (siril-cli, headless Siril).
    typed = bool(argv)
    if siril is not None:
        try:
            typed = typed or siril.is_headless()
        except Exception:
            pass
    try:
        if typed:
            code = run_headless(argv, say)
        else:
            run_window(siril)
            code = EXIT_OK
    except PngUnavailable as e:
        say(str(e), "error")
        code = EXIT_NO_PNG
    finally:
        if siril is not None:
            try:
                siril.disconnect()
            except Exception:
                pass
    return code


if __name__ == "__main__":
    sys.exit(main())
