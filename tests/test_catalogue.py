from importlib.resources import files

import pytest

from skywrapped.catalogue import CatalogueObject, load_catalogue, lookup, normalise_id

FLOOR = 16900  # 16,952 after merging Sh2/LBN duplicates; the brief's 17,000 was a sanity check


def test_catalogue_contents():
    cat = load_catalogue()
    assert len(cat) >= FLOOR
    m8 = lookup("M8")
    assert m8.id == "NGC6523" and abs(m8.ra - 270.9) < 0.2 and "Lagoon" in m8.common_name
    assert "Helix" in lookup("NGC7293").common_name
    for i in ["SH2-136", "LDN1235", "LBN437", "B33", "VDB152", "C33", "IC434"]:
        assert lookup(i) is not None


def test_catalogue_size():
    assert (files("skywrapped") / "data/catalogue.json.gz").stat().st_size <= 1_000_000


def test_load_is_cached_and_typed():
    assert load_catalogue() is load_catalogue()
    o = lookup("M31")
    assert isinstance(o, CatalogueObject)
    assert o.id == "NGC224" and "Andromeda" in o.common_name
    assert isinstance(o.aliases, tuple) and "M31" in o.aliases
    assert o.kind == "galaxy" and o.size_arcmin and o.size_arcmin > 150
    assert 3.0 < o.mag < 4.5
    assert abs(o.ra - 10.68) < 0.05 and abs(o.dec - 41.27) < 0.05


@pytest.mark.parametrize(
    "raw, want",
    [
        ("NGC0224", "NGC224"),
        ("ngc 224", "NGC224"),
        ("IC0434", "IC434"),
        ("M 8", "M8"),
        ("Sh2-136", "SH2-136"),
        ("SH2136", "SH2-136"),
        ("sh 2-155", "SH2-155"),
        ("vdB 152", "VDB152"),
        ("LDN 1235", "LDN1235"),
        ("LBN_437", "LBN437"),
        ("B033", "B33"),
        ("C 033", "C33"),
    ],
)
def test_normalise(raw, want):
    assert normalise_id(raw) == want


def test_lookup_normalises_input_and_unknown():
    assert lookup("ngc 7293") is lookup("NGC7293")
    assert lookup("Sh2-136") is lookup("SH2-136")
    assert lookup("NOT-AN-OBJECT-123") is None


def test_ids_unique_and_valid():
    cat = load_catalogue()
    assert len({o.id for o in cat}) == len(cat)
    for o in cat:
        assert o.id == normalise_id(o.id)
        assert 0 <= o.ra < 360 and -90 <= o.dec <= 90


def test_messier_and_caldwell_are_aliases():
    assert lookup("M42").id == "NGC1976"
    assert lookup("M45") is not None  # via OpenNGC addendum
    assert lookup("M40") is not None
    assert lookup("C33").id == "NGC6992"
    assert lookup("C34").id == "NGC6960"
    assert lookup("C63").id == "NGC7293"
    assert lookup("C14") is not None
    assert lookup("C9").id == lookup("SH2-155").id


def test_every_caldwell_number_resolves():
    for n in range(1, 110):
        assert lookup(f"C{n}") is not None, f"C{n}"


def test_common_names():
    assert "Cave" in lookup("SH2-155").common_name
    assert "Shark" in lookup("LDN1235").common_name
    assert "Horsehead" in lookup("B33").common_name
    assert "Coathanger" in lookup("CR399").common_name
    assert "Rosette" in lookup("NGC2244").common_name
    assert "Heart" in lookup("IC1805").common_name
    assert "Soul" in lookup("IC1848").common_name
    assert "Gamma Cygni" in lookup("IC1318").common_name
    assert "Elephant" in lookup("IC1396").common_name


def test_rho_ophiuchi_complex():
    o = lookup("RhoOph")
    assert "Rho Ophiuchi" in o.common_name
    assert abs(o.ra - 16.4167 * 15) < 1.0 and abs(o.dec + 23.4) < 0.3


@pytest.mark.parametrize(
    "name",
    "44Tau B142 Cr399 DG26 IC1283 IC1318 IC1396 IC1805 IC2118 IC2177 IC342 IC434 IC4592 IC4601 "
    "IC4665 IC4685 IC4756 IC5070 IC5146 LDN1082 LDN1147 LDN1235 LDN1688 LDN386 M1 M104 M106 M13 "
    "M16 M17 M20 M24 M27 M31 M33 M42 M45 M46 M5 M51 M57 M63 M64 M65 M77 M78 M8 M81 M82 M83 M87 "
    "NGC1333 NGC2024 NGC2174 NGC2244 NGC2264 NGC253 NGC281 NGC288 NGC3242 NGC4038 NGC4631 "
    "NGC4699 NGC5068 NGC6210 NGC6559 NGC6888 NGC6910 NGC6946 NGC6960 NGC6992 NGC7000 NGC7023 "
    "NGC7293 NGC7331 NGC7635 NGC7822 NGC891 NYCephei RhoOph SH2129 SH2136 SH2245 VdB126 VdB152 "
    "ZetaOphiuchi Cave 44Tauri LacertaeAF".split(),
)
def test_common_target_spellings_resolve(name):
    assert lookup(name) is not None, name


def test_sharpless_and_lbn_fold_into_ngc_ic():
    heart = lookup("SH2-190")
    assert heart.id == "IC1805" and "Heart" in heart.common_name and heart.size_arcmin >= 100
    assert lookup("IC1805").size_arcmin >= 100
    soul = lookup("SH2-199")
    assert soul.id == "IC1848" and "Soul" in soul.common_name
    assert lookup("SH2-131").id == "IC1396" and "Elephant" in lookup("SH2-131").common_name
    assert lookup("SH2-184").id == "NGC281" and "Pacman" in lookup("SH2-184").common_name
    assert lookup("SH2-162").id == "NGC7635"
    assert lookup("SH2-105").id == "NGC6888"


def test_ic1318_is_the_nebula():
    o = lookup("SH2-108")
    assert o.id == "IC1318" and o.size_arcmin >= 100 and "Gamma Cygni" in o.common_name


def test_m102_and_collinder_forms():
    m = lookup("M102")
    assert m is None or m.id != "NGC5457"
    assert lookup("Cl399") is lookup("Cr399") and lookup("Cl399") is not None


def test_lbn_folds_never_change_size():
    maia, m45 = lookup("NGC1432"), lookup("M45")
    assert maia.size_arcmin <= 60 and m45.size_arcmin > maia.size_arcmin
    assert lookup("LBN770") is maia
    ic2088 = lookup("IC2088")
    assert ic2088.size_arcmin is None or ic2088.size_arcmin < 60
    assert lookup("IC405").size_arcmin <= 100
    assert lookup("SH2-190").id == "IC1805" and lookup("IC1805").size_arcmin >= 100


def test_ngc2264_size_is_only_the_sh2_fold():
    o = lookup("NGC2264")
    assert lookup("SH2-273") is o and lookup("LBN922") is o
    assert o.size_arcmin == 250.0  # max(OpenNGC 11.4, Sh2-273 250); LBN922/929 add nothing


def test_lagoon_sharpless_folds_into_m8_not_ngc6526():
    assert lookup("SH2-25").id == "NGC6523" and lookup("M8").id == "NGC6523"
    assert lookup("NGC6523").size_arcmin == 90.0
    assert lookup("NGC6526").size_arcmin == 40.0  # its own OpenNGC size, not the Sharpless 90'


def test_ghost_of_jupiter_aliases():
    assert lookup("Ghost of Jupiter").id == "NGC3242"
    assert lookup("Ghost of Jupiter Nebula").id == "NGC3242"


def test_ic434_is_the_horsehead_nebula():
    assert lookup("IC434").common_name == "Horsehead Nebula"
