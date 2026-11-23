"""Command line: skywrapped PATH... — headers only, nothing leaves this computer. Standard library only."""
import argparse
import json
import os
import sys
from datetime import date, datetime

from . import __version__
from .scan import scan_paths
from .stats import NoLightsError, compute_wrapped, to_summary

PROGRESS_EVERY = 1000


def _local_offset_h() -> float:
    off = datetime.now().astimezone().utcoffset()
    return off.total_seconds() / 3600.0 if off is not None else 0.0


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="skywrapped", description="Turn a folder of astrophotography light frames into year-in-astro cards. "
        "Reads FITS/XISF headers only; nothing leaves this computer.")
    p.add_argument("paths", nargs="+", metavar="PATH", help="folders (or files) of light frames")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--year", type=int, default=None, help="calendar year to count (default: this year)")
    g.add_argument("--all", action="store_true", help="count every year")
    p.add_argument("--theme", choices=("observatory", "nebula"), default="observatory")
    p.add_argument("--out", default=None, help="output folder (default ./skywrapped-<year>)")
    p.add_argument("--exclude", action="append", default=[], metavar="GLOB",
                   help="skip files whose path matches this pattern (repeatable)")
    p.add_argument("--tz", type=float, default=None, metavar="HOURS",
                   help="your UTC offset in hours, e.g. -5 or 5.5 (default: this computer's)")
    p.add_argument("--json-only", action="store_true", help="write summary.json only")
    p.add_argument("--version", action="version", version=f"skywrapped {__version__}")
    return p


def _count(n: int, one: str, many: str) -> str:
    return f"{n:,} {one if n == 1 else many}"


_SKIP_WORDS = {  # summary.json skipped key -> (one, many)
    "calibration": ("calibration frame", "calibration frames"),
    "not_light": ("not a light", "not lights"),
    "duplicate": ("duplicate", "duplicates"),
    "stack_with_subs": ("stack whose subs are counted", "stacks whose subs are counted"),
    "outside_year": ("from another year", "from other years"),
    "excluded": ("excluded", "excluded"),
    "unreadable": ("unreadable", "unreadable"),
    "metadata_file": ("metadata file", "metadata files"),
    "no_time": ("without a time", "without a time"),
}


def _final_line(s: dict) -> str:
    line = (f"{s['hours']:.1f} h · {_count(s['nights'], 'night', 'nights')} · "
            f"{_count(s['frames'], 'frame', 'frames')} · {_count(s['targets'], 'target', 'targets')}")
    sk = s["skipped"]
    extra = [_count(n, *_SKIP_WORDS.get(k, (k.replace("_", " "),) * 2))
             for k, n in sk.items() if n and k != "type_assumed"]
    if extra:
        line += " · skipped: " + ", ".join(extra)
    if sk.get("type_assumed"):
        line += f" · {sk['type_assumed']:,} type assumed (counted)"
    return line


def _no_lights(year: int | None, years: tuple) -> str:
    """Counts and years only. When the year filter left nothing, name the years that have lights."""
    if year is None or not years:
        return "No light frames found in the given folders."
    near = min(years, key=lambda y: (abs(y - year), -y))
    return (f"No light frames from {year}. Found lights from: {', '.join(map(str, years))}. "
            f"Try --year {near} or --all.")


MARKER = ".skywrapped-output"
OWN_PATTERNS = ("card-*.png", "card-*.svg", "poster.png", "poster.svg", "index.html", "summary.json")


def _prepare_out(out: str) -> bool:
    """False if ``out`` is non-empty and not ours. Otherwise clear only our own file names and mark it."""
    from pathlib import Path
    d = Path(out)
    if d.exists():
        if not d.is_dir() or (any(d.iterdir()) and not (d / MARKER).exists()):
            return False
    return True


def _clear_own(out: str) -> None:
    from pathlib import Path
    d = Path(out)
    d.mkdir(parents=True, exist_ok=True)
    if (d / MARKER).exists():
        for pat in OWN_PATTERNS:
            for f in d.glob(pat):
                if f.is_file():
                    f.unlink()
    (d / MARKER).write_text("Made by skywrapped. Its own card files here are replaced on each run.\n", encoding="utf-8")


def _write_cards(wrapped, theme: str, out: str) -> None:
    from pathlib import Path

    from .cards import render_cards
    from .preview import card_stems, write_preview
    from .render_png import svg_to_png

    cards = render_cards(wrapped, theme=theme)
    for c, stem in card_stems(cards):
        png = svg_to_png(c.svg, c.width)
        (Path(out) / f"{stem}.svg").write_text(c.svg, encoding="utf-8")
        (Path(out) / f"{stem}.png").write_bytes(png)
    write_preview(Path(out), cards)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    today = date.today()
    year = None if args.all else (args.year if args.year is not None else today.year)
    tz = args.tz if args.tz is not None else _local_offset_h()
    out = args.out or f"./skywrapped-{'all' if year is None else year}"

    if not _prepare_out(out):
        print("Choose an empty output folder (or one skywrapped made before).", file=sys.stderr)
        return 4

    missing = [p for p in args.paths if not os.path.exists(p)]
    if missing:
        n = len(missing)
        print(f"{n} of the given paths {'does' if n == 1 else 'do'} not exist.", file=sys.stderr)
        return 2

    def progress(done: int, total: int) -> None:
        if done % PROGRESS_EVERY == 0 or done == total:
            print(f"Read {done:,} of {total:,} files", file=sys.stderr)

    frames, skipped = scan_paths(args.paths, args.exclude, progress)
    try:
        wrapped = compute_wrapped(frames, year=year, default_offset_h=tz, today=today, skipped=skipped)
    except NoLightsError as e:
        print(_no_lights(year, e.years), file=sys.stderr)
        return 2

    summary = to_summary(wrapped)
    _clear_own(out)
    target = os.path.join(out, "summary.json")
    tmp = target + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
    os.replace(tmp, target)
    if not args.json_only:
        from .render_png import MissingPngDependency
        try:
            _write_cards(wrapped, args.theme, out)
        except MissingPngDependency as e:
            print(str(e), file=sys.stderr)
            return 3
    print(_final_line(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
