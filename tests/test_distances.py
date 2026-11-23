import csv
from importlib.resources import files

import pytest

from skywrapped.catalogue import distance_ly


def read_rows():
    text = files("skywrapped").joinpath("data/distances.csv").read_text(encoding="utf-8")
    return list(csv.DictReader(text.splitlines()))


@pytest.mark.parametrize("i,ly,tol", [("M45", 444, .15), ("M31", 2.5e6, .15), ("NGC7293", 650, .2), ("M8", 4100, .3)])
def test_known_distances(i, ly, tol):
    assert distance_ly(i) == pytest.approx(ly, rel=tol)


def test_table_complete():
    rows = read_rows()
    assert len(rows) >= 265 and all(r["source"] for r in rows)
    assert 3.5e7 <= distance_ly("NGC7331") <= 5e7


def test_aliases_resolve_to_primary_id():
    assert distance_ly("M8") == distance_ly("NGC6523") == distance_ly("ngc 6523")


def test_unknown_is_none():
    assert distance_ly("NOT-A-THING") is None


def test_ids_round_trip_and_unique():
    from skywrapped.catalogue import lookup

    ids = [r["id"] for r in read_rows()]
    assert len(ids) == len(set(ids))
    assert all(lookup(i).id == i for i in ids)


def test_modern_medians():
    assert 1000 <= distance_ly("M27") <= 1600
    assert 26e6 <= distance_ly("M104") <= 34e6


@pytest.mark.parametrize("i", ["ZETOPH", "AFLAC", "NYCEP", "M73", "IC4592"])
def test_weak_rows_absent(i):
    assert distance_ly(i) is None


def test_few_measurements_name_their_paper():
    import re

    for r in read_rows():
        if int(r["n"]) <= 2:
            assert re.search(r"\d{4}[A-Za-z&.]{3,}\d*\.|doi:", r["source"]), r
