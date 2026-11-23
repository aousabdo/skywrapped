"""Find light-frame files under folders and read their headers (never pixels). Standard library only."""
import fnmatch
import os
from collections.abc import Callable
from pathlib import Path

from ._fitsnorm import Frame, header_bytes_needed, read_header, to_frame

EXTENSIONS = {".fit", ".fits", ".fts", ".fz", ".xisf"}
FIRST_READ = 8640  # three FITS blocks: most headers fit
MAX_HEADER = 1_048_576  # a header needing more than this is not a camera file (or is hostile)
_BAD_HEADER = (ValueError, KeyError, IndexError, OverflowError, TypeError)

# The rules below are shared with web_api, so the web page reads exactly the files the command line reads.


def skip_counts() -> dict[str, int]:
    """The scan's own skipped counts, all zero."""
    return {"excluded": 0, "unreadable": 0, "metadata_file": 0}


def is_hidden(name: str) -> bool:
    """Hidden files and folders (a leading dot) are never read."""
    return name.startswith(".")


def classify(name: str) -> str | None:
    """What to do with a file, by its base name: "read", "metadata_file" (an AppleDouble ``._`` twin, counted),
    or None (another file type, or a hidden file: ignored without a count)."""
    if os.path.splitext(name)[1].lower() not in EXTENSIONS:
        return None
    if name.startswith("._"):
        return "metadata_file"
    if is_hidden(name):
        return None
    return "read"


def next_read(data: bytes) -> int | None:
    """0 when the header in ``data`` is complete, else the total bytes to read next; None when the bytes cannot
    start a header worth reading (not FITS/XISF, or a header over MAX_HEADER)."""
    try:
        need = header_bytes_needed(data)
    except _BAD_HEADER:
        return None
    return None if need > MAX_HEADER else need


def frame_from_header(data: bytes, path: str) -> Frame | None:
    """The Frame for a complete header, or None when it does not parse."""
    try:
        values, comments = read_header(data)
        return to_frame(values, comments, path)
    except _BAD_HEADER:
        return None


def _read_frame(path: str) -> Frame | None:
    """Read just the header of one file; None when it is not a readable FITS/XISF header."""
    try:
        with open(path, "rb") as fh:
            data = fh.read(FIRST_READ)
            while (need := next_read(data)) != 0:
                if need is None or need <= len(data):  # the loop must end: a need must ask for more bytes
                    return None
                more = fh.read(need - len(data))
                if not more:
                    return None
                data += more
    except OSError:
        return None
    return frame_from_header(data, path)


def _candidates(paths: list[str], errors: list[str]):
    """Yield every file under the given files/folders, in a stable order (a file reached twice comes twice).

    Folders os.walk cannot read are appended to ``errors``.
    """
    for p in paths:
        if os.path.isfile(p):
            walk = [(os.path.dirname(p), [], [os.path.basename(p)])]
        else:
            walk = os.walk(p, onerror=lambda e: errors.append(str(e.filename)))
        for dirpath, dirnames, filenames in walk:
            dirnames[:] = sorted(d for d in dirnames if not is_hidden(d))
            for fn in sorted(filenames):
                yield os.path.join(dirpath, fn)


def scan_paths(paths: list[str], excludes: list[str],
               on_progress: Callable[[int, int], None] | None = None) -> tuple[list[Frame], dict[str, int]]:
    """Read every FITS/XISF header under ``paths``. Returns (frames, skipped-counts).

    Names starting ``._`` are counted as metadata files; other hidden files are ignored; files matching an
    ``excludes`` glob (matched against the posix path) are counted as excluded; unreadable files are counted.
    """
    skipped = skip_counts()
    todo: list[str] = []
    walk_errors: list[str] = []
    seen: set[str] = set()
    for path in _candidates(paths, walk_errors):
        kind = classify(os.path.basename(path))
        if kind is None:
            continue
        real = os.path.realpath(path)  # overlapping paths: each file once (resolved only for the files that count)
        if real in seen:
            continue
        seen.add(real)
        if kind == "metadata_file":
            skipped["metadata_file"] += 1
            continue
        posix = Path(os.path.abspath(path)).as_posix()
        if any(fnmatch.fnmatch(posix, pat) for pat in excludes):
            skipped["excluded"] += 1
            continue
        todo.append(path)

    skipped["unreadable"] += len(walk_errors)
    frames: list[Frame] = []
    total = len(todo)
    for i, path in enumerate(todo, 1):
        f = _read_frame(path)
        if f is None:
            skipped["unreadable"] += 1
        else:
            frames.append(f)
        if on_progress:
            on_progress(i, total)
    return frames, skipped
