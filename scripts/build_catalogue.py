#!/usr/bin/env python
"""Build src/skywrapped/data/catalogue.json.gz from OpenNGC, VizieR and scripts/extra_names.csv.

Build-time only (needs ``astroquery`` from the ``dev`` extra); the runtime never imports this.
Downloads are cached in ``.cache/`` (git-ignored); delete a cache file to refetch it.

    .venv/bin/python scripts/build_catalogue.py

Sources (see LICENSE-DATA.md):
  OpenNGC NGC.csv + addendum.csv  CC-BY-SA 4.0   (github.com/mattiaverga/OpenNGC)
  VizieR VII/20 Sharpless, VII/7A Lynds LDN, VII/9 Lynds LBN, VII/220A Barnard, VII/21 van den Bergh
  SIMBAD, for a few named fields listed in extra_names.csv
"""

from __future__ import annotations

import csv
import gzip
import json
import math
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from skywrapped.catalogue import normalise_id  # noqa: E402

CACHE = ROOT / ".cache"
OUT = ROOT / "src" / "skywrapped" / "data" / "catalogue.json.gz"
EXTRA = ROOT / "scripts" / "extra_names.csv"
OPENNGC_BASE = "https://raw.githubusercontent.com/mattiaverga/OpenNGC/master/database_files/"
VIZIER_MIRROR = "vizier.cfa.harvard.edu"  # the Strasbourg host was unreachable from the build machine
SIMBAD_MIRROR = "simbad.harvard.edu"

KINDS = {
    "G": "galaxy", "GPair": "galaxy_group", "GTrpl": "galaxy_group", "GGroup": "galaxy_group",
    "OCl": "open_cluster", "GCl": "globular_cluster", "*Ass": "asterism", "Cl+N": "cluster_nebula",
    "HII": "emission_nebula", "EmN": "emission_nebula", "Neb": "nebula", "RfN": "reflection_nebula",
    "DrkN": "dark_nebula", "PN": "planetary_nebula", "SNR": "supernova_remnant",
    "*": "star", "**": "star", "Nova": "star", "Other": "other",
}
KEEP_IDENT = re.compile(r"^(C|LBN|SH 2|CL|MEL|CR|UGC|LDN|B|VDB|BARNARD|ARP)[\s-]*\d", re.I)


# ---------------------------------------------------------------- downloads
def fetch_openngc() -> None:
    d = CACHE / "openngc"
    d.mkdir(parents=True, exist_ok=True)
    for name in ("NGC.csv", "addendum.csv"):
        if not (d / name).exists():
            print("downloading", OPENNGC_BASE + name)
            urllib.request.urlretrieve(OPENNGC_BASE + name, d / name)


VIZIER = {  # cache name -> (catalogue asked for, table wanted from it)
    "sh2": ("VII/20/catalog", "VII/20/catalog"), "ldn": ("VII/7A", "VII/7A/ldn"),
    "lbn": ("VII/9", "VII/9/catalog"), "barnard": ("VII/220", "VII/220A/barnard"),
    "vdb": ("VII/21", "VII/21/catalog"),
}


def fetch_vizier() -> None:
    d = CACHE / "vizier"
    d.mkdir(parents=True, exist_ok=True)
    todo = {k: v for k, v in VIZIER.items() if not (d / f"{k}.csv").exists()}
    if not todo:
        return
    from astroquery.vizier import Vizier

    for key, (query_id, table_id) in todo.items():
        print("querying VizieR", table_id)
        v = Vizier(columns=["*", "_RAJ2000", "_DEJ2000"], row_limit=-1, vizier_server=VIZIER_MIRROR)
        tables = v.get_catalogs(query_id)
        t = next(t for t in tables if t.meta.get("name") == table_id)
        keep = [c for c in t.colnames if not c.startswith("_RA.") and not c.startswith("_DE.")]
        t[keep].write(d / f"{key}.csv", format="ascii.csv", overwrite=True)


def simbad_coords(queries: list[str]) -> dict[str, list]:
    path = CACHE / "simbad_extra.json"
    cached = json.loads(path.read_text()) if path.exists() else {}
    missing = [q for q in queries if q not in cached]
    if missing:
        from astroquery.simbad import Simbad

        s = Simbad()
        s.server = SIMBAD_MIRROR
        for q in missing:
            print("querying SIMBAD", q)
            t = s.query_object(q)
            if t is None or len(t) == 0:
                raise SystemExit(f"SIMBAD found nothing for {q!r}")
            cached[q] = [float(t["ra"][0]), float(t["dec"][0]), str(t["main_id"][0])]
        path.write_text(json.dumps(cached, indent=1))
    return cached


# ---------------------------------------------------------------- helpers
def hms(s: str) -> float:
    h, m, sec = (float(x) for x in s.split(":"))
    return (h + m / 60 + sec / 3600) * 15


def dms(s: str) -> float:
    sign = -1 if s.strip().startswith("-") else 1
    d, m, sec = (abs(float(x)) for x in s.replace("+", "").replace("-", "").split(":"))
    return sign * (d + m / 60 + sec / 3600)


def num(s: str | None) -> float | None:
    try:
        v = float(s)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) or v <= 0 else v


def norm_alias(raw: str) -> str:
    n = normalise_id(raw)
    return re.sub(r"^CL(?=\d)", "CR", n)  # OpenNGC writes Collinder as "Cl"


class Obj:
    def __init__(self, id_, ra, dec, size, mag, common, kind):
        self.id, self.ra, self.dec = id_, ra, dec
        self.size, self.mag, self.common, self.kind = size, mag, common, kind
        self.aliases: set[str] = set()
        self.otype = ""  # OpenNGC's own type code, for the merge step

    def row(self):
        return [self.id, sorted(self.aliases - {self.id}), round(self.ra, 5), round(self.dec, 5),
                None if self.size is None else round(self.size, 2),
                None if self.mag is None else round(self.mag, 2), self.common, self.kind]


class Catalogue:
    def __init__(self):
        self.objs: dict[str, Obj] = {}
        self.index: dict[str, Obj] = {}

    def find(self, raw: str) -> Obj | None:
        return self.index.get(norm_alias(raw))

    def add(self, o: Obj, aliases=()) -> Obj:
        self.objs[o.id] = o
        self.index[o.id] = o
        self._cl(o, o.id)
        for a in aliases:
            self.alias(o, a)
        return o

    def alias(self, o: Obj, raw: str) -> None:
        a = norm_alias(raw)
        if a and a != o.id and self.index.get(a) in (None, o):
            o.aliases.add(a)
            self.index[a] = o
        self._cl(o, a)

    def _cl(self, o: Obj, a: str) -> None:
        """Collinder is written Cr or Cl; lookups of either form must resolve."""
        if re.fullmatch(r"CR\d+", a):
            cl = "CL" + a[2:]
            if self.index.get(cl) in (None, o):
                o.aliases.add(cl)
                self.index[cl] = o


# ---------------------------------------------------------------- OpenNGC
def load_openngc(cat: Catalogue) -> int:
    dups: list[tuple[str, dict]] = []
    n = 0
    for fname in ("NGC.csv", "addendum.csv"):
        addendum = fname == "addendum.csv"
        with open(CACHE / "openngc" / fname, newline="") as f:
            for r in csv.DictReader(f, delimiter=";"):
                t = r["Type"]
                if t == "NonEx" or not r["RA"] or not r["Dec"]:
                    continue
                if t == "Dup":
                    dups.append((r["Name"], r))
                    continue
                idents = [i.strip() for i in r["Identifiers"].split(",") if KEEP_IDENT.match(i.strip())]
                id_ = norm_alias(r["Name"])
                if addendum and re.fullmatch(r"C\d+", id_):  # Caldwell rows: prefer the Sharpless designation
                    sh = next((i for i in idents if i.upper().startswith("SH 2")), None)
                    if sh:
                        id_ = norm_alias(sh)
                names = [x.strip() for x in r["Common names"].split(",") if x.strip()]
                o = Obj(id_, hms(r["RA"]), dms(r["Dec"]), num(r["MajAx"]),
                        num(r["V-Mag"]) or num(r["B-Mag"]), names[0] if names else None, KINDS.get(t, "other"))
                if id_ in cat.objs:
                    continue
                o.otype = t
                cat.add(o, [norm_alias(r["Name"])] + idents)
                if r["M"]:
                    cat.alias(o, f"M{int(r['M'])}")
                if r["NGC"]:
                    cat.alias(o, f"NGC{r['NGC']}")
                if r["IC"]:
                    cat.alias(o, f"IC{r['IC']}")
                n += 1
    for name, r in dups:  # a Dup row is another name for the object its M/NGC/IC column points at
        target = (f"M{int(r['M'])}" if r["M"] else f"NGC{r['NGC']}" if r["NGC"] else f"IC{r['IC']}" if r["IC"] else None)
        o = cat.find(target) if target else None
        if o and not re.fullmatch(r"M\d+", norm_alias(name)):  # OpenNGC's M102 = M101 is a dubious identification
            cat.alias(o, name)
    return n


# ---------------------------------------------------------------- VizieR
def read(key: str) -> list[dict]:
    with open(CACHE / "vizier" / f"{key}.csv", newline="") as f:
        return list(csv.DictReader(f))


NEBULA_TYPES = {"HII", "Neb", "EmN", "RfN", "Cl+N", "SNR", "DrkN"}
MERGE_ARCMIN = 3.0
merged: dict[str, int] = {"sh2": 0, "lbn": 0}
MANUAL_FOLDS = {"SH2-25": "NGC6523"}  # Sh2-25 is the Lagoon Nebula, M8


def nearby_nebula(cat: Catalogue, ra: float, dec: float, size: float | None) -> Obj | None:
    """Closest OpenNGC nebula-ish object within MERGE_ARCMIN of a position. Beyond that, an object of similar
    size (within 4x) counts when the centres are less than a quarter of the larger diameter apart: the Soul
    Nebula's Sh2-199 centre is 25' from IC1848's, and a 1200' Sh2-276 must not swallow a 6' IC 420."""
    best, best_d = None, 0.0
    cosd = math.cos(math.radians(dec))
    for o in cat.objs.values():
        if o.otype not in NEBULA_TYPES:
            continue
        dd = (o.dec - dec) * 60
        if abs(dd) > 0.25 * max(size or 0, o.size or 0, MERGE_ARCMIN * 4):
            continue
        dr = ((o.ra - ra + 180) % 360 - 180) * cosd * 60
        d = math.hypot(dr, dd)
        big = max(size or 0, o.size or 0)
        similar = bool(size and o.size) and min(size, o.size) >= 0.25 * big
        if d <= MERGE_ARCMIN or (similar and d <= 0.25 * big):
            if best is None or d < best_d:
                best, best_d = o, d
    return best


def fold(cat: Catalogue, o: Obj, id_: str, ra: float, dec: float, size: float | None, geometry: bool) -> None:
    """Make id_ an alias of o. Only when `geometry` (Sh2 folds): keep the larger size, and use the other position
    if o has no size. LBN folds add the alias only: LBN diameters describe whole clouds and would inflate
    small NGC/IC objects (Maia, IC 405, Cone)."""
    if geometry:
        if o.size is None:
            o.ra, o.dec = ra, dec
        if size is not None:
            o.size = max(o.size or 0, size)
    cat.alias(o, id_)


def load_vizier(cat: Catalogue) -> dict[str, int]:
    counts: dict[str, int] = {}

    def put(key, prefix, num_, r, size, mag, kind):
        id_ = f"{prefix}{int(float(num_))}" if re.fullmatch(r"[\d.]+", str(num_).strip()) else norm_alias(f"{prefix}{num_}")
        counts.setdefault(key, 0)
        if cat.find(id_) is not None:
            return  # OpenNGC already knows it (as id or alias)
        ra, dec = float(r["_RAJ2000"]), float(r["_DEJ2000"])
        if key in ("sh2", "lbn"):
            # Manual corrections: Sh2-25 is the Lagoon (M8), 24' from M8 and 18' from NGC 6526; the geometric
            # rule would pick NGC 6526 and inflate it from 40' to 90'.
            twin = cat.objs.get(MANUAL_FOLDS.get(id_, "")) or nearby_nebula(cat, ra, dec, size)
            if twin is not None:
                if "--verbose" in sys.argv:
                    print(f"  fold {id_} ({size}') into {twin.id} ({twin.size}') {twin.common}")
                fold(cat, twin, id_, ra, dec, size, geometry=(key == "sh2"))
                merged[key] += 1
                return
        cat.add(Obj(id_, float(r["_RAJ2000"]), float(r["_DEJ2000"]), size, mag, None, kind))
        counts[key] += 1

    for r in read("sh2"):
        put("sh2", "SH2-", r["Sh2"], r, num(r["Diam"]), None, "emission_nebula")
    for r in read("ldn"):
        area = num(r["Area"])
        put("ldn", "LDN", r["LDN"], r, None if area is None else math.sqrt(area) * 60, None, "dark_nebula")
    for r in read("lbn"):
        d = max(num(r["Diam1"]) or 0, num(r["Diam2"]) or 0) or None
        put("lbn", "LBN", r["Seq"], r, d, None, "nebula")
    for r in read("barnard"):
        put("barnard", "B", r["Barn"].strip(), r, num(r["Diam"]), None, "dark_nebula")
    for r in read("vdb"):
        put("vdb", "VDB", r["VdB"], r, None, num(r["Vmag"]), "reflection_nebula")
    return counts


# ---------------------------------------------------------------- hand-made names
def apply_extras(cat: Catalogue) -> int:
    rows = list(csv.DictReader(line for line in open(EXTRA) if not line.startswith("#")))
    need = [r["simbad_query"] for r in rows if r["simbad_query"] and not (r["ra_deg"] and r["dec_deg"])]
    sim = simbad_coords(need) if need else {}
    for r in rows:
        o = cat.find(r["id"])
        ra, dec = (float(r["ra_deg"]), float(r["dec_deg"])) if r["ra_deg"] and r["dec_deg"] else (None, None)
        if ra is None and r["simbad_query"]:
            ra, dec = sim[r["simbad_query"]][:2]
        if o is None:
            if ra is None:
                raise SystemExit(f"extra_names: {r['id']} is not in the catalogue and has no coordinates")
            o = cat.add(Obj(normalise_id(r["id"]), ra, dec, None, None, None, r["kind"] or "other"))
        elif ra is not None:
            o.ra, o.dec = ra, dec
        if r["common_name"]:
            o.common = r["common_name"]
        if r["kind"]:
            o.kind = r["kind"]
        if r["size_arcmin"]:
            o.size = float(r["size_arcmin"])
        for a in filter(None, r["aliases"].split("|")):
            cat.alias(o, a)
    return len(rows)


def main() -> None:
    fetch_openngc()
    fetch_vizier()
    cat = Catalogue()
    n_ngc = load_openngc(cat)
    n_viz = load_vizier(cat)
    ic = cat.objs["IC1318"]  # OpenNGC has the star gam Cyg; the nebula is Sh2-108 (180')
    sh108 = cat.objs.pop("SH2-108")
    ic.ra, ic.dec, ic.size = sh108.ra, sh108.dec, sh108.size
    del cat.index["SH2-108"]
    cat.alias(ic, "SH2-108")
    n_extra = apply_extras(cat)
    rows = [o.row() for o in sorted(cat.objs.values(), key=lambda o: o.id)]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"version": 1, "objects": rows}, separators=(",", ":"), ensure_ascii=False)
    OUT.write_bytes(gzip.compress(payload.encode(), 9, mtime=0))
    print(f"OpenNGC objects {n_ngc}; VizieR new objects {n_viz}; extra_names rows {n_extra}")
    print(f"merged into NGC/IC objects: {merged} (+1 manual: SH2-108 into IC1318)")
    print(f"{len(rows)} objects, {OUT.stat().st_size} bytes -> {OUT}")


if __name__ == "__main__":
    main()
