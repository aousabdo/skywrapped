"""The web page's Python side. worker.js runs it in Pyodide; standard library only.

The page hands over header slices, never whole files, and gets back JSON with the computed numbers and the card
SVGs. The files' paths are used only to recognise files (as on the command line), never returned: nothing here
gives back a path, a site coordinate or raw OBJECT text. File rules and the 1 MiB header cap are scan.py's.

The flow: ``reset()``, ``select(paths)``, then ``parse_batch`` until nothing is pending, then ``finish(...)``;
``finish`` can run again with another year or time zone, and ``rerender`` switches the theme.
"""
from __future__ import annotations

import json
from datetime import date

from ._fitsnorm import Frame
from .cards import render_cards
from .preview import card_stems
from .scan import FIRST_READ, classify, frame_from_header, is_hidden, next_read, skip_counts
from .stats import NoLightsError, Wrapped, compute_wrapped, to_summary

__all__ = ["FIRST_READ", "finish", "parse_batch", "rerender", "reset", "select"]

_frames: list[Frame] = []
_skipped: dict[str, int] = skip_counts()
_asked: dict[str, int] = {}          # path -> total bytes last asked for
_wrapped: Wrapped | None = None


def reset() -> None:
    """Forget every frame and count (a new folder)."""
    global _skipped, _wrapped
    _frames.clear()
    _asked.clear()
    _skipped = skip_counts()
    _wrapped = None


def select(paths: list[str]) -> list[int]:
    """The indices of the files to read, in order.

    ``paths`` are browser relative paths ("picked folder/sub/name.fit"). As on the command line, the picked folder
    may itself be hidden but no hidden folder under it is entered, ``._`` twins are counted as metadata files, and
    other file types and hidden files are ignored.
    """
    keep = []
    for i, path in enumerate(paths):
        parts = str(path).replace("\\", "/").split("/")
        if any(is_hidden(d) for d in parts[1:-1]):
            continue
        kind = classify(parts[-1])
        if kind == "read":
            keep.append(i)
        elif kind == "metadata_file":
            _skipped["metadata_file"] += 1
    return keep


def parse_batch(items: list[tuple[str, bytes]]) -> list[tuple[str, int]]:
    """Read the headers in ``items`` (path, the file's first bytes). Finished frames stay here.

    Returns (path, total bytes needed) for each header that is not complete yet; send that file's first N bytes
    next. A file that is not a header, needs more than the cap, or ends before its header does, is counted as
    unreadable and never asked for again.
    """
    still = []
    for path, data in items:
        data = bytes(data)
        need = next_read(data)
        asked = _asked.pop(path, 0)
        if need == 0:
            frame = frame_from_header(data, path)
            if frame is None:
                _skipped["unreadable"] += 1
            else:
                _frames.append(frame)
        elif need is None or need <= len(data) or len(data) < asked:
            # junk, over the cap, a header that asks for no more than it has (the re-slice loop must end), or
            # the file is shorter than its header
            _skipped["unreadable"] += 1
        else:
            _asked[path] = need
            still.append((path, need))
    return still


def _cards(theme: str) -> list[dict]:
    return [{"name": c.name, "stem": stem, "width": c.width, "height": c.height, "svg": c.svg}
            for c, stem in card_stems(render_cards(_wrapped, theme=theme))]


def finish(year: int | None, default_offset_h: float, today_iso: str, theme: str) -> str:
    """JSON ``{"summary": {...}, "cards": [{"name", "stem", "width", "height", "svg"}]}`` for the frames read.

    ``year=None`` counts every year. With no light frame left to count it is
    ``{"error": "no_lights", "headers": n, "skipped": {...}, "years": [years that have lights]}``: counts only.
    """
    global _wrapped
    today = date.fromisoformat(today_iso)
    offset = float(default_offset_h)
    year = None if year is None else int(year)
    try:
        _wrapped = compute_wrapped(list(_frames), year=year, default_offset_h=offset, today=today,
                                   skipped=dict(_skipped))
    except NoLightsError as e:  # only that: any other error is a bug and surfaces as one
        _wrapped = None
        return json.dumps({"error": "no_lights", "headers": len(_frames), "skipped": dict(_skipped),
                           "years": list(e.years) if year is not None else []})
    return rerender(theme)


def rerender(theme: str) -> str:
    """The last ``finish`` result drawn in another theme (same JSON shape); ValueError before a good finish."""
    if _wrapped is None:
        raise ValueError("nothing to draw yet: call finish() first")
    return json.dumps({"summary": to_summary(_wrapped), "cards": _cards(theme)})
