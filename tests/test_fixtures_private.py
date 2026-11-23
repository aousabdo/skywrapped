import re
from pathlib import Path

import pytest

FIXTURES = sorted((Path(__file__).parent / "fixtures" / "headers").glob("*.hdr"))

LAT = ("SITELAT", "LATITUDE", "LAT-OBS", "OBSGEO-B")
LON = ("SITELONG", "LONGITUD", "LONG-OBS", "OBSGEO-L")
ELEV = ("SITEELEV", "OBSGEO-H", "ELEVATIO")
IDENT = ("OBSERVER", "SERIALNO", "CAMSN", "SITENAME")
# with the time and the pointing these place the site: neutralised (AIRMASS, TIMEZONE) or absent (the rest)
SKY_POSITION = ("ALT", "AZ", "ALTITUDE", "AZIMUTH", "OBJCTALT", "OBJCTAZ", "OBJCTHA", "CENTALT", "CENTAZ", "LST", "HA")
# Optional, git-ignored: one real value per line that must not appear in any fixture.
PRIVATE_VALUES = Path(__file__).parent / ".private_values"


def _cards(path):
    text = path.read_bytes().decode("ascii")
    for i in range(0, len(text), 80):
        card = text[i:i + 80]
        if card[8:10] == "= ":
            yield card[:8].strip(), card[10:].split("/")[0].strip()


def test_fixtures_exist():
    assert len(FIXTURES) == 15


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
def test_fixture_is_scrubbed(path):
    for key, value in _cards(path):
        if key in LAT:
            assert float(value) == 12.3456, key
        elif key in LON:
            assert float(value) == -65.4321, key
        elif key in ELEV:
            assert float(value) == 0, key
        elif key in IDENT:
            assert value == "'scrubbed'", key
        elif key == "CAMERA":
            assert not re.search(r"-[0-9a-fA-F]{6,}", value), value
        elif key == "AIRMASS":
            assert float(value) == 1.0, key
        elif key == "TIMEZONE":
            assert value == "'+0000'", key


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
def test_fixture_cannot_place_the_site(path):
    """I8: no altitude/azimuth/hour-angle/sidereal-time card in any form (blanked by scripts/make_fixture.py)."""
    text = path.read_bytes().decode("ascii")
    keys = {text[i:i + 8].strip() for i in range(0, len(text), 80)}
    assert not keys & set(SKY_POSITION), sorted(keys & set(SKY_POSITION))


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.stem)
def test_fixture_has_no_listed_private_value(path):
    if not PRIVATE_VALUES.exists():
        pytest.skip("tests/.private_values not present (optional local check)")
    raw = path.read_bytes().decode("ascii")
    for real in PRIVATE_VALUES.read_text().split():
        assert real not in raw, "a listed private value appears in the fixture"
