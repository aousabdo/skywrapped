"""Cluster light frames into targets and name them from the bundled catalogue. Stdlib only.

Frames are grouped by where the camera pointed (in time order, into running-mean clusters), each cluster is
named from the catalogue, and clusters that resolve to the same object merge (mosaic panels), as do objects that
share a common name (the Rosette is NGC 2237, 2238 and 2239; the Eastern Veil NGC 6992 and 6995). Raw OBJECT text
never reaches a label: it is only ever used to pick between catalogue objects or to look one up.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache

from ._fitsnorm import Frame
from .catalogue import CatalogueObject, load_catalogue, lookup, lookup_common

UNNAMED = "Unnamed target"
DEFAULT_FOV = (1.0, 1.0)  # degrees, when a frame has coordinates but no usable field of view
JOIN_FRACTION = 0.4
_BAND = 1.0  # degrees of declination per spatial-index band

_DESIGNATION = re.compile(
    r"^(?:(?P<sh>SHARPLESS|SH)[\s_]*2[\s_-]*(?P<shn>\d+)"
    r"|(?P<pre>MESSIER|BARNARD|VAN[\s_-]*DEN[\s_-]*BERGH|MEL|NGC|IC|SH2|LDN|LBN|VDB|CR|M|B|C)[\s_-]*(?P<n>\d+))"
    r"(?![A-Z0-9])",
    re.I,
)
_DISPLAY = re.compile(r"^([A-Z]+?)-?(\d+)$")
_DISPLAY_PREFIX = {"SH2": "Sh2-", "VDB": "vdB ", "CR": "Cr ", "MEL": "Mel "}
_MESSIER = re.compile(r"^M\d+$")


def normalise_id(text: str) -> str | None:
    """A catalogue designation at the start of ``text`` in canonical form, else None.

    "SH2-245_LExt" -> "SH2-245", "Messier 31" -> "M31", "IC_434_LUlt" -> "IC434", "Lagoon Nebula" -> None.
    """
    if not text:
        return None
    m = _DESIGNATION.match(text.strip().upper())
    if not m:
        return None
    if m.group("sh"):
        return f"SH2-{int(m.group('shn'))}"
    pre = m.group("pre")
    n = int(m.group("n"))
    if pre == "MESSIER":
        pre = "M"
    elif pre == "BARNARD":
        pre = "B"
    elif pre.startswith("VAN"):
        pre = "VDB"
    return f"SH2-{n}" if pre == "SH2" else f"{pre}{n}"


def display_name(id_: str) -> str:
    """"M8" -> "M 8", "SH2-136" -> "Sh2-136", "VDB152" -> "vdB 152"."""
    if id_.startswith("SH2-"):
        return "Sh2-" + id_[4:]
    m = _DISPLAY.match(id_)
    if not m:
        return id_
    pre, n = m.groups()
    return _DISPLAY_PREFIX.get(pre, pre + " ") + n


@dataclass
class Target:
    key: str
    label: str
    common_name: str | None
    frame_idx: list[int]
    ra: float | None
    dec: float | None


# ---------------------------------------------------------------- catalogue spatial index

@lru_cache(maxsize=1)
def _dec_bands() -> dict[int, list[CatalogueObject]]:
    bands: dict[int, list[CatalogueObject]] = {}
    for o in load_catalogue():
        bands.setdefault(math.floor(o.dec / _BAND), []).append(o)
    return bands


def _sep_deg(ra1, dec1, ra2, dec2) -> float:
    p1, p2 = math.radians(dec1), math.radians(dec2)
    d = math.radians(ra1 - ra2)
    c = math.sin(p1) * math.sin(p2) + math.cos(p1) * math.cos(p2) * math.cos(d)
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def _candidates(ra, dec, radius):
    lo, hi = math.floor((dec - radius) / _BAND), math.floor((dec + radius) / _BAND)
    bands = _dec_bands()
    for b in range(lo, hi + 1):
        for o in bands.get(b, ()):
            s = _sep_deg(ra, dec, o.ra, o.dec)
            if s <= radius:
                yield o, s


def _hint_variants(hint: str):
    """The hint, then the hint with trailing ``_filter`` / ``_Tile03`` style tokens dropped one at a time."""
    parts = hint.strip().split("_")
    for n in range(len(parts), 0, -1):
        v = "_".join(parts[:n]).strip()
        if v:
            yield v


def _hint_objects(hint: str) -> list[CatalogueObject]:
    """Catalogue objects an OBJECT hint can mean, best reading first: a designation (any spelling), then a
    catalogue id or alias (with a trailing suffix stripped), then an exact common name. Raw text is only used
    to select catalogue objects, it never reaches a label."""
    nid = normalise_id(hint)
    o = lookup(nid) if nid else None
    if o is not None:
        return [o]
    variants = list(_hint_variants(hint))
    for v in variants:
        o = lookup(v)
        if o is not None:
            return [o]
    for v in variants:
        found = lookup_common(v)
        if found:
            return list(found)
    return []


def _name_cluster(ra, dec, fov, hint):
    """The catalogue object a pointing shows, or None."""
    w, h = fov
    cands = list(_candidates(ra, dec, 0.5 * math.hypot(w, h)))
    if not cands:
        return None
    if hint:
        ids = {o.id for o in _hint_objects(hint)}
        hit = [(o, s) for o, s in cands if o.id in ids]
        if hit:
            return min(hit, key=lambda c: c[1])[0]
    # R17 guard: an object far smaller than the field (< 5% of its smaller side) is not the subject
    floor_arcmin = 0.05 * min(w, h) * 60.0
    cands = [(o, s) for o, s in cands if (o.size_arcmin or 0.0) >= floor_arcmin]
    if not cands:
        return None
    # Prominent objects whose extent holds the field centre. Of those, the one the frame is most centred on
    # relative to its own size: a plain "largest wins" picks a surrounding dust cloud (LDN1373 over the Heart)
    # or a bigger neighbour (NGC6526 over the Lagoon), neither of which is what was photographed.
    reach = 0.15 * max(w, h)
    inside = [(o, s) for o, s in cands if s <= max((o.size_arcmin or 0.0) / 120.0, reach)]
    if inside:
        return min(inside, key=lambda c: (c[1] * 60.0 / max(c[0].size_arcmin or 0.0, 1.0), -(c[0].size_arcmin or 0.0)))[0]
    return min(cands, key=lambda c: c[1])[0]


def _key_of(o: CatalogueObject) -> str:
    for a in o.aliases:
        if _MESSIER.match(a):
            return a
    return o.id


def _merge_key(key: str, common: str | None) -> str:
    """Targets with this key are one: the same object, or objects with the same common name (a trailing
    parenthesis aside: "Rosette Nebula (NGC 2244 cluster)" is the Rosette)."""
    if not common:
        return key
    name = re.sub(r"\s*\(.*\)\s*$", "", common).strip().casefold()
    return "\0name:" + name if name else key


def _coord_label(ra, dec) -> str:
    total_min = int(round((ra % 360.0) / 15.0 * 60.0)) % (24 * 60)
    d = int(round(dec))
    sign = "−" if d < 0 else "+" if d > 0 else ""
    return f"RA {total_min // 60:02d}h{total_min % 60:02d}m, Dec {sign}{abs(d):02d}°"


# ---------------------------------------------------------------- clustering

class _Cluster:
    __slots__ = ("x", "y", "z", "n", "side", "idx", "hints", "band")

    def __init__(self, side):
        self.x = self.y = self.z = 0.0
        self.n = 0
        self.side = side
        self.idx: list[int] = []
        self.hints: dict[str, int] = {}
        self.band = 0

    def centre_vec(self):
        r = math.sqrt(self.x ** 2 + self.y ** 2 + self.z ** 2) or 1.0
        return self.x / r, self.y / r, self.z / r

    def centre(self):
        x, y, z = self.centre_vec()
        return math.degrees(math.atan2(y, x)) % 360.0, math.degrees(math.asin(max(-1.0, min(1.0, z))))


def _unit(ra, dec):
    r, d = math.radians(ra), math.radians(dec)
    return math.cos(d) * math.cos(r), math.cos(d) * math.sin(r), math.sin(d)


def _side(f: Frame) -> float:
    fov = f.fov_deg
    if fov and fov[0] > 0 and fov[1] > 0:
        return min(fov)
    return min(DEFAULT_FOV)


def _fov(f: Frame):
    fov = f.fov_deg
    if fov and fov[0] > 0 and fov[1] > 0:
        return fov
    return DEFAULT_FOV


def _order_key(item):
    i, f = item
    t = f.start_utc or f.start_local
    return (t is None, t or datetime.min, i)


def _best_hint(hints: dict[str, int]) -> str | None:
    """The most common hint that is a catalogue designation; failing that, the most common hint that names a
    catalogue object some other way (an alias or a common name). Hints are never shown."""
    for ok in (lambda h: bool(normalise_id(h)), lambda h: bool(_hint_objects(h))):
        best, best_n = None, 0
        for h, n in hints.items():
            if n > best_n and ok(h):
                best, best_n = h, n
        if best is not None:
            return best
    return None


def group_targets(frames: list[Frame]) -> list[Target]:
    lights = [(i, f) for i, f in enumerate(frames) if f.frame_type == "light"]
    placed = sorted((p for p in lights if p[1].ra_deg is not None and p[1].dec_deg is not None), key=_order_key)

    clusters: list[_Cluster] = []
    bands: dict[int, set[int]] = {}
    for i, f in placed:
        side = _side(f)
        thr = JOIN_FRACTION * side
        v = _unit(f.ra_deg, f.dec_deg)
        lo, hi = math.floor((f.dec_deg - thr) / _BAND) - 1, math.floor((f.dec_deg + thr) / _BAND) + 1
        near: set[int] = set()
        for b in range(lo, hi + 1):
            near |= bands.get(b, set())
        home = None
        for ci in sorted(near):
            c = clusters[ci]
            cx, cy, cz = c.centre_vec()
            dot = cx * v[0] + cy * v[1] + cz * v[2]
            if dot >= math.cos(math.radians(JOIN_FRACTION * min(side, c.side))):
                home = ci
                break
        if home is None:
            c = _Cluster(side)
            clusters.append(c)
            home = len(clusters) - 1
        else:
            c = clusters[home]
            c.side = min(c.side, side)
            bands[c.band].discard(home)
        c.x += v[0]
        c.y += v[1]
        c.z += v[2]
        c.n += 1
        c.idx.append(i)
        if f.object_hint:
            c.hints[f.object_hint] = c.hints.get(f.object_hint, 0) + 1
        c.band = math.floor(c.centre()[1] / _BAND)
        bands.setdefault(c.band, set()).add(home)

    # name every cluster, then merge clusters with the same key or common name
    merged: dict[str, dict] = {}

    def add(o: CatalogueObject | None, unnamed: tuple[str, str] | None):
        if o is not None:
            key = _key_of(o)
            m = merged.setdefault(_merge_key(key, o.common_name), dict(names={}, idx=[], vec=[0.0, 0.0, 0.0], n=0))
            m["names"].setdefault(key, (display_name(key), o.common_name, o.size_arcmin or 0.0))
        else:
            key, label = unnamed
            m = merged.setdefault(key, dict(names={}, idx=[], vec=[0.0, 0.0, 0.0], n=0))
            m["names"].setdefault(key, (label, None, 0.0))
        return m

    for c in clusters:
        ra, dec = c.centre()
        fovs = [_fov(frames[i]) for i in c.idx]
        fov = (max(w for w, _ in fovs), max(h for _, h in fovs)) if len(set(fovs)) > 1 else fovs[0]
        o = _name_cluster(ra, dec, fov, _best_hint(c.hints))
        # unnamed clusters never merge, even when their labels coincide
        m = add(o, None if o is not None else (f"\0unnamed{len(merged)}", _coord_label(ra, dec)))
        m["idx"] += c.idx
        m["vec"][0] += c.x
        m["vec"][1] += c.y
        m["vec"][2] += c.z
        m["n"] += c.n

    # frames without coordinates: by hint only
    for i, f in lights:
        if f.ra_deg is not None and f.dec_deg is not None:
            continue
        objs = _hint_objects(f.object_hint) if f.object_hint else []
        o = objs[0] if objs else None
        add(o, None if o is not None else (UNNAMED, UNNAMED))["idx"].append(i)

    targets = []
    for m in merged.values():
        x, y, z = m["vec"]
        if m["n"]:
            ra = math.degrees(math.atan2(y, x)) % 360.0
            dec = math.degrees(math.asin(max(-1.0, min(1.0, z / (math.sqrt(x * x + y * y + z * z) or 1.0)))))
        else:
            ra = dec = None
        # of objects merged by common name, the largest names the target (first seen on a tie)
        key = max(m["names"], key=lambda k: m["names"][k][2])
        label, common, _ = m["names"][key]
        targets.append(Target(label if key.startswith("\0") else key, label, common, sorted(m["idx"]), ra, dec))
    targets.sort(key=lambda t: t.frame_idx[0])
    return targets
