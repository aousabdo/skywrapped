from datetime import datetime

import pytest

from skywrapped.astro import moon_altitude, moon_illumination

# Truth from astropy; site Kitt Peak (public observatory)


@pytest.mark.parametrize(
    "t,k",
    [((2026, 11, 24, 4, 0), 0.995), ((2026, 11, 9, 6, 0), 0.002), ((2026, 9, 6, 5, 11, 25), 0.288)],
)
def test_moon_illumination(t, k):
    assert moon_illumination(datetime(*t)) == pytest.approx(k, abs=0.02)


@pytest.mark.parametrize(
    "t,alt",
    [((2026, 11, 24, 4, 0), 53.1), ((2026, 1, 3, 5, 0), 59.0), ((2026, 11, 9, 6, 0), -72.9)],
)
def test_moon_altitude(t, alt):
    assert moon_altitude(datetime(*t), 31.9583, -111.5967) == pytest.approx(alt, abs=1.0)
