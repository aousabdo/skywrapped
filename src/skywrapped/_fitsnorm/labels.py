"""Telescope and camera names fit to print: no device ids, serial numbers or long free text. Standard library only.

Every TELESCOP/INSTRUME string that can reach a card or summary.json passes through ``clean_label`` (frame.py).
"""
import re
import unicodedata

MAX_LEN = 32
_HEX_SUFFIX = re.compile(r"[_-][0-9A-Fa-f]{6,}$")   # "S50_4a8b9c2d" -> "S50"
_DIGIT_RUN = re.compile(r"\d{6,}")                   # serial numbers, dates
_NOT_ALLOWED = re.compile(r"[^A-Za-z0-9 .,+/'\"()#&-]")
_EMPTY_PARENS = re.compile(r"\(\s*\)")
_EDGE = " .,+/&#-"


def clean_label(raw) -> str | None:
    """A short printable name from a header string, or None when nothing is left.

    Strips a trailing device id (``_``/``-`` then 6+ hex digits) and any run of 6+ digits, keeps only
    ``[A-Za-z0-9 .,+/'"()#&-]`` (accents are folded first, underscores become spaces) and cuts at 32 characters on a
    word boundary.
    """
    if raw is None or isinstance(raw, bool):
        return None
    s = str(raw).strip()
    prev = None
    while s != prev:
        prev = s
        s = _HEX_SUFFIX.sub("", s).strip()
    s = _DIGIT_RUN.sub(" ", s)
    s = unicodedata.normalize("NFKD", s).replace("_", " ")
    s = _NOT_ALLOWED.sub("", s)
    s = _EMPTY_PARENS.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip(_EDGE)
    if len(s) > MAX_LEN:
        head = s[:MAX_LEN + 1]
        s = head.rsplit(" ", 1)[0] if " " in head else s[:MAX_LEN]
        s = s.strip(_EDGE)
    return s or None
