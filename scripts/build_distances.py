#!/usr/bin/env python
"""Build src/skywrapped/data/distances.csv: one sourced distance per catalogue object.

Build-time only (needs ``astroquery`` from the ``dev`` extra); the runtime never imports this.

    .venv/bin/python scripts/build_distances.py

Value rule: the median of every SIMBAD ``mesDistance`` measurement for the object, converted to
light-years (pc x 3.26156, kpc x 3261.56, Mpc x 3.26156e6). Raw SIMBAD rows are cached in
``.cache/simbad_distances.json`` (git-ignored; delete it to refetch). Objects SIMBAD has no
measurement for are fixed by hand in HAND_FIXES, each with a citation, or left out of the table:
nothing is guessed. Outliers are listed in scripts/distances_review.md.
"""

from __future__ import annotations

import csv
import json
import re
import statistics
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from skywrapped.catalogue import load_catalogue, lookup, normalise_id  # noqa: E402

CACHE = ROOT / ".cache" / "simbad_distances.json"
OUT = ROOT / "src" / "skywrapped" / "data" / "distances.csv"
EXTRA = ROOT / "scripts" / "extra_names.csv"
SIMBAD_MIRROR = "simbad.harvard.edu"  # the Strasbourg host times out from the build machine at times
LY_PER_PC = 3.26156
UNIT_PC = {"pc": 1.0, "kpc": 1e3, "mpc": 1e6}

# commonly photographed objects beyond Messier and Caldwell, so they get a distance too
EXTRA_IDS = """B142 IC1283 IC1318 IC1396 IC1805 IC2118 IC2177 IC342 IC434 IC4592 IC4601 IC4665 IC4685 IC4756
IC5070 IC5146 LDN1082 LDN1147 LDN1235 LDN1688 LDN386 NGC1333 NGC2024 NGC2174 NGC2244 NGC2264 NGC253 NGC281 NGC288
NGC3242 NGC4038 NGC4631 NGC4699 NGC5068 NGC6210 NGC6559 NGC6888 NGC6910 NGC6946 NGC6960 NGC6992 NGC7000 NGC7023
NGC7293 NGC7331 NGC7635 NGC7822 NGC891 SH2-129 SH2-136 SH2-245 VDB126 VDB152 CR399""".split()

# Objects SIMBAD has no mesDistance for, measured through a named parent: id -> (SIMBAD names, why).
# The value is still the SIMBAD median (pooled over the names), so it has a bibcode behind it.
PROXIES: dict[str, tuple[list[str], str]] = {
    "NGC1982": (["NGC 1976"], "M43 is part of the Orion Nebula (M42)"),
    "NGC7023": (["HD 200775"], "illuminating star of the Iris Nebula"),
    "C14": (["NGC 869", "NGC 884"], "the two clusters of the Double Cluster, pooled"),
    "IC405": (["HD 34078"], "AE Aurigae, the star that lights the Flaming Star Nebula"),
    "C41": (["NAME Hyades"], "the Hyades cluster"),
    "NGC2070": (["NAME Large Magellanic Cloud"], "the Tarantula Nebula sits in the LMC"),
    "NGC2237": (["NGC 2244"], "the cluster that lights the Rosette Nebula"),
    "NGC2238": (["NGC 2244"], "the cluster that lights the Rosette Nebula"),
    "NGC2174": (["NGC 2175"], "the cluster in the Monkey Head Nebula"),
    "IC4601": (["HD 147889"], "the star that lights IC 4601 in the Rho Ophiuchi region"),
    "RHOOPH": (["NAME Rho Oph Cloud"], "the Rho Ophiuchi cloud"),
    "44TAU": (["* 44 Tau"], "the star itself"),
    "SH2-136": (["vdB 141"], "Sh2-136 (the Ghost Nebula) is vdB 141"),
    "IC434": (["NAME Sigma Orionis Cluster"], "sigma Ori lights the Horsehead region; same Orion OB1b"),
    "B33": (["NAME Sigma Orionis Cluster"], "the Horsehead lies beside sigma Ori; same Orion OB1b"),
}
# Literature values for objects SIMBAD has no mesDistance for: id -> (light-years, citation).
HAND_FIXES: dict[str, tuple[float, str]] = {
    "NGC6992": (725 * LY_PER_PC, "Fesen et al. 2021, MNRAS (doi:10.1093/mnras/stab2066): Cygnus Loop 725 +/- 15 pc, Gaia EDR3"),
    "NGC6960": (725 * LY_PER_PC, "Fesen et al. 2021, MNRAS (doi:10.1093/mnras/stab2066): Cygnus Loop 725 +/- 15 pc, Gaia EDR3"),
}
_GAIA = "Gaia DR2 + EDR3 distances via SIMBAD mesDistance (2018yCat.1345....0G 201 pc, 2020yCat.1350....0G 199.5 pc)"
HAND_FIXES["NGC7293"] = (200.25 * LY_PER_PC, f"{_GAIA}; the plain SIMBAD median (about 520 ly) is pulled down by older 152-159 pc values")
# SIMBAD has one value that disagrees with the literature, so the object is left out: id -> why.
DROP = {
    "NGC40": "modern Gaia values 1.8-2.0 kpc against 1.1-1.2 kpc in the older papers; the sources disagree by a factor 1.7",
    "NGC6905": "the only modern value (Gaia, 2.7 kpc) is 50% above the older 1.75 kpc values; sources disagree",
    "NGC4303": "the only post-2016 value (24.2 Mpc, 2018ApJ...861...49H) is 40% above every other measurement (10.6-19.8 Mpc)",
    "NGC6994": "M73 is an asterism of four stars, not a cluster, so it has no single distance",
    "ZETOPH": "a star's distance for a nebula field (R19)",
    "AFLAC": "a star's distance for a nebula field; single value (R19)",
    "NYCEP": "a star's distance for a nebula field; single value (R19)",
    "IC4592": "only a single nu Sco value, which contradicts IC4601 in the same complex (R19)",
    "LDN1235": "proxy LDN 1228 has a single value (R19)",
    "LDN1147": "proxy LDN 1228 has a single value (R19)",
    "C99": "proxy Coalsack has a single value (R19)",
    "NGC6729": "proxy R CrA cloud has a single value (R19)",
    "NGC2246": "single SIMBAD value 2.4 kpc (2006ApJ...653.1226Q) disagrees with the Rosette's ~1.5 kpc",
    "NGC6537": "single SIMBAD value 3.8 kpc (2010ApJ...714.1096S); published Red Spider distances range 1-4 kpc",
}
GC_URL = "https://people.smp.uq.edu.au/HolgerBaumgardt/globular/parameter.html"
GC_CITE = "Baumgardt & Vasiliev 2021, MNRAS 505, 5957 (2021MNRAS.505.5957B), distance from Sun"
REVIEW = ROOT / "scripts" / "distances_review.md"


def wanted_ids() -> list[str]:
    """Primary catalogue ids of every Messier, Caldwell, extra_names and EXTRA_IDS object."""
    queries = [f"M{n}" for n in range(1, 111)] + [f"C{n}" for n in range(1, 110)] + EXTRA_IDS
    with EXTRA.open(encoding="utf-8") as f:
        rows = [ln for ln in f if not ln.startswith("#")]
    queries += [r["id"] for r in csv.DictReader(rows)]
    # the named NGC/IC objects too (the table is for any photographed target); unmeasured ones simply drop out
    queries += [o.id for o in load_catalogue() if o.common_name and re.fullmatch(r"(NGC|IC)\d+", o.id)]
    out: list[str] = []
    for q in queries:
        o = lookup(q)
        if o and o.id not in out:
            out.append(o.id)
    return out


def simbad_names(id_: str) -> list[str]:
    """Candidate SIMBAD identifiers for one catalogue object (primary id plus Messier alias)."""
    o = lookup(id_)
    names: list[str] = []
    for raw in [o.id, *[a for a in o.aliases if re.fullmatch(r"M\d+", a)]]:
        m = re.fullmatch(r"(NGC|IC|M|LDN|LBN|B)(\d+)([A-Z]?)", raw)
        if m:
            names.append(f"{m.group(1)} {m.group(2)}{m.group(3)}")
        elif (m := re.fullmatch(r"SH2-(\d+)", raw)):
            names.append(f"Sh 2-{m.group(1)}")
        elif (m := re.fullmatch(r"VDB(\d+)", raw)):
            names.append(f"vdB {m.group(1)}")
        elif (m := re.fullmatch(r"CR(\d+)", raw)):
            names.append(f"Cl Collinder {m.group(1)}")
        elif (m := re.fullmatch(r"MEL(\d+)", raw)):
            names.append(f"Cl Melotte {m.group(1)}")
        else:
            names.append(raw)
    return names


def _adql_names(names: list[str]) -> str:
    return ", ".join("'" + n.replace("'", "''") + "'" for n in names)


def fetch(queries: dict[str, list[str]]) -> dict[str, list[list]]:
    """{key: [[distance, unit, bibcode, simbad name], ...]} from SIMBAD mesDistance for each key's names, cached."""
    cache: dict[str, list[list]] = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    todo = [k for k in queries if k not in cache]
    if not todo:
        return cache
    from astroquery.simbad import Simbad

    s = Simbad()
    s.server = SIMBAD_MIRROR
    for k0 in range(0, len(todo), 40):
        chunk = todo[k0 : k0 + 40]
        back: dict[str, list[str]] = {}
        for k in chunk:
            for n in queries[k]:
                back.setdefault(n.upper().replace(" ", ""), []).append(k)
        adql = (
            "SELECT i.id AS name, d.dist AS dist, d.unit AS unit, d.bibcode AS bibcode FROM ident AS i "
            "JOIN mesDistance AS d ON d.oidref = i.oidref "
            f"WHERE i.id IN ({_adql_names([n for k in chunk for n in queries[k]])})"
        )
        print(f"querying SIMBAD {k0 + 1}-{k0 + len(chunk)} of {len(todo)}")
        res = s.query_tap(adql)
        got: dict[str, list[list]] = {k: [] for k in chunk}
        for r in res:
            unit = str(r["unit"]).strip().lower()
            if unit not in UNIT_PC or r["dist"] is None or str(r["dist"]) == "--":
                continue
            row = [float(r["dist"]), unit, str(r["bibcode"]).strip(), str(r["name"]).strip()]
            for k in back.get(str(r["name"]).upper().replace(" ", ""), []):
                got[k].append(row)
        cache.update(got)
        CACHE.parent.mkdir(exist_ok=True)
        CACHE.write_text(json.dumps(cache, indent=0))
        time.sleep(2)  # be polite
    return cache


def globular_distances() -> dict[str, float]:
    """{normalised designation: distance in light-years} from Baumgardt's table; cached HTML in .cache/gc."""
    path = ROOT / ".cache" / "gc" / "params.html"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(GC_URL, timeout=60) as r:
            path.write_bytes(r.read())
    out: dict[str, float] = {}
    for row in re.findall(r"<tr.*?</tr>", path.read_text(errors="replace"), re.S):
        cells = [re.sub(r"<[^>]*>", " ", c) for c in re.findall(r"<t[dh].*?</t[dh]>", row, re.S)]
        if len(cells) > 4 and (m := re.match(r"\s*([\d.]+)\s*&plusmn;", cells[3])):
            for des in re.findall(r"(?:NGC|IC|M|Pal|Terzan|Ter)\s*\d+", cells[0].replace("&nbsp;", " ")):
                out[normalise_id(des)] = float(m.group(1)) * 1000 * LY_PER_PC
    return out


def to_ly(value: float, unit: str) -> float:
    return value * UNIT_PC[unit.lower()] * LY_PER_PC


MODERN = 2016  # R19: Gaia-era and modern TRGB/Cepheid values; older ones drag medians (Helix, M27, NGC 6302, ...)


def median_ly(raw: list[list]) -> tuple[float, int, float, float, list[str]] | None:
    """Median of the measurements published in MODERN or later when any exist, else of all.

    One vote per (bibcode, value): SIMBAD lists the same paper's value under several names.
    Returns (median, n used, min, max, sorted bibcodes used).
    """
    seen = {(m[2], m[0], m[1]) for m in raw}
    if any(to_ly(v, u) > 1e6 for _, v, u in seen):  # a galaxy: Gaia matched a foreground star, drop kpc-scale rows
        seen = {t for t in seen if to_ly(t[1], t[2]) > 1e5}
    modern = {t for t in seen if t[0][:4].isdigit() and int(t[0][:4]) >= MODERN}
    use = modern or seen
    vals = sorted(to_ly(v, u) for _, v, u in use)
    if not vals:
        return None
    return statistics.median(vals), len(vals), vals[0], vals[-1], sorted({t[0] for t in use})


def source_text(m, prefix: str = "SIMBAD mesDistance") -> str:
    era = "since 2016" if all(b[:4] >= str(MODERN) for b in m[4]) else "all years"
    text = f"{prefix} median (n={m[1]}, {era})"
    return text + (f" [{' '.join(m[4])}]" if m[1] <= 2 else "")


def build() -> list[dict]:
    ids = wanted_ids()
    queries = {i: simbad_names(i) for i in ids}
    queries.update({f"proxy:{i}": names for i, (names, _) in PROXIES.items()})
    raw = fetch(queries)
    gc = globular_distances()
    rows, missing, notes, spread, dropped = [], [], [], [], []
    for i in ids:
        if i in DROP:
            dropped.append(f"{i}: {DROP[i]}")
            continue
        if i in HAND_FIXES:
            ly, src = HAND_FIXES[i]
            n = 2 if i == "NGC7293" else 1
            rows.append({"id": i, "distance_ly": round(ly), "source": src, "n": n})
            notes.append(f"| {i} | {round(ly)} | {n} | literature | {src} |")
            continue
        m = median_ly(raw.get(i, []))
        gkey = next((a for a in [lookup(i).id, *lookup(i).aliases] if a in gc), None) if m else None
        if m and gkey and lookup(i).kind == "globular_cluster" and abs(m[0] / gc[gkey] - 1) > 0.15:
            # old single-paper SIMBAD value more than 15% off the modern Gaia-based table: use the table
            rows.append({"id": i, "distance_ly": round(gc[gkey]), "source": GC_CITE, "n": 1})
            notes.append(f"| {i} | {round(gc[gkey])} | 1 | {gkey} | globular; SIMBAD median {round(m[0])} ly is >15% off Baumgardt |")
            continue
        if m:
            rows.append({"id": i, "distance_ly": round(m[0]), "source": source_text(m), "n": m[1]})
            spread.append((i, m))
            continue
        obj = lookup(i)
        if i in PROXIES:
            names, why = PROXIES[i]
            m = median_ly(raw.get(f"proxy:{i}", []))
            if m and m[1] < 2:
                dropped.append(f"{i}: proxy {' + '.join(names)} has only n={m[1]} modern value (R19 needs n>=2)")
                continue
            if m:
                src = f"{source_text(m)} of {' + '.join(names)}: {why}"
                rows.append({"id": i, "distance_ly": round(m[0]), "source": src, "n": m[1]})
                notes.append(f"| {i} | {round(m[0])} | {m[1]} | {' + '.join(names)} | {why} |")
                continue
        key = next((a for a in [obj.id, *obj.aliases] if a in gc), None)
        if key and obj.kind == "globular_cluster":
            rows.append({"id": i, "distance_ly": round(gc[key]), "source": GC_CITE, "n": 1})
            notes.append(f"| {i} | {round(gc[key])} | 1 | {key} | globular cluster; SIMBAD has no mesDistance |")
            continue
        missing.append(i)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, ["id", "distance_ly", "source", "n"], lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    write_review(rows, spread, notes, missing, dropped, gc)
    print(f"{len(rows)} rows written; no measurement for {len(missing)}: {' '.join(missing)}")
    return rows


def write_review(rows, spread, notes, missing, dropped, gc) -> None:
    """Machine-made part of scripts/distances_review.md; the '## Hand-check notes' section at the end is kept across rebuilds."""
    flag = [(i, m) for i, m in spread if m[1] == 1 or m[3] / m[2] > 2.5]
    lines = ["# Distance table review (generated by build_distances.py)", "",
             f"{len(rows)} rows. Distances in light-years; `n` = distinct (paper, value) pairs in SIMBAD mesDistance.", "",
             "## Not measured directly: filled through a parent or a globular-cluster table", "",
             "| id | ly | n | via | why |", "|---|---|---|---|---|", *notes, "",
             "## Left out of the table (no source we can cite)", "", " ".join(missing) or "none", "",
             "## Dropped after hand-checking (a source disagrees; better absent than wrong)", "",
             *[f"- {d}" for d in dropped], "",
             "## Flagged SIMBAD medians (n=1, or max/min spread above 2.5)", "",
             "| id | median ly | n | min | max |", "|---|---|---|---|---|",
             *[f"| {i} | {round(m[0])} | {m[1]} | {round(m[2])} | {round(m[3])} |" for i, m in flag], ""]
    marker = "## Hand-check notes"
    old = REVIEW.read_text(encoding="utf-8") if REVIEW.exists() else ""
    keep = old[old.index(marker):] if marker in old else ""
    REVIEW.write_text("\n".join(lines) + ("\n" + keep if keep else ""), encoding="utf-8")


if __name__ == "__main__":
    build()
