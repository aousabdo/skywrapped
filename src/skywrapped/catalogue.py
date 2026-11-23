"""Bundled deep-sky catalogue: OpenNGC, Sharpless, Lynds, Barnard, van den Bergh and a few hand-made names.

Stdlib only, so it also runs in Pyodide. The data file is built by ``scripts/build_catalogue.py``
and attributed in ``LICENSE-DATA.md``.
"""

from __future__ import annotations

import csv
import gzip
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from importlib.resources import files

_SH2 = re.compile(r"^SH2-?0*(\d+)$")
_PLAIN = re.compile(r"^([A-Z]+)0*(\d+)([A-Z]*)$")


@dataclass(frozen=True)
class CatalogueObject:
    id: str
    aliases: tuple[str, ...]
    ra: float  # degrees, J2000
    dec: float  # degrees, J2000
    size_arcmin: float | None
    mag: float | None
    common_name: str | None
    kind: str


def normalise_id(raw: str) -> str:
    """Canonical form of a catalogue designation: ``NGC0224`` -> ``NGC224``, ``Sh 2-136`` -> ``SH2-136``."""
    s = re.sub(r"[\s_]+", "", raw.strip().upper())
    m = _SH2.match(s)
    if m:
        return f"SH2-{m.group(1)}"
    s = s.replace("-", "")
    m = _PLAIN.match(s)
    if m:
        return f"{m.group(1)}{m.group(2)}{m.group(3)}"
    return s


@lru_cache(maxsize=1)
def load_catalogue() -> list[CatalogueObject]:
    raw = files("skywrapped").joinpath("data/catalogue.json.gz").read_bytes()
    rows = json.loads(gzip.decompress(raw))["objects"]
    return [
        CatalogueObject(
            id=r[0], aliases=tuple(r[1]), ra=r[2], dec=r[3], size_arcmin=r[4], mag=r[5], common_name=r[6], kind=r[7]
        )
        for r in rows
    ]


@lru_cache(maxsize=1)
def _index() -> dict[str, CatalogueObject]:
    idx: dict[str, CatalogueObject] = {}
    for o in load_catalogue():
        for a in o.aliases:
            idx.setdefault(a, o)
    for o in load_catalogue():  # ids win over any alias
        idx[o.id] = o
    return idx


def lookup(id_: str) -> CatalogueObject | None:
    """Find an object by id or alias; the input is normalised first."""
    return _index().get(normalise_id(id_))


def _common_key(name: str) -> str:
    """Casefolded, whitespace-normalised common name with a trailing parenthesis removed."""
    return re.sub(r"\s+", " ", re.sub(r"\s*\(.*\)\s*$", "", name.replace("_", " ")).strip()).casefold()


@lru_cache(maxsize=1)
def _common_index() -> dict[str, tuple[CatalogueObject, ...]]:
    idx: dict[str, list[CatalogueObject]] = {}
    for o in load_catalogue():
        if o.common_name:
            idx.setdefault(_common_key(o.common_name), []).append(o)
    return {k: tuple(v) for k, v in idx.items() if k}


def lookup_common(name: str) -> tuple[CatalogueObject, ...]:
    """Objects whose common name equals ``name`` exactly (casefolded, a trailing parenthesis ignored)."""
    return _common_index().get(_common_key(name), ())


@lru_cache(maxsize=1)
def _distances() -> dict[str, float]:
    text = files("skywrapped").joinpath("data/distances.csv").read_text(encoding="utf-8")
    return {r["id"]: float(r["distance_ly"]) for r in csv.DictReader(text.splitlines())}


def distance_ly(id_: str) -> float | None:
    """Distance in light-years from the bundled table (``scripts/build_distances.py``), or None if unknown."""
    obj = lookup(id_)
    return _distances().get(obj.id) if obj else None
