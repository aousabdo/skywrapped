import warnings

import pytest

from skywrapped._fitsnorm.header import read_header
from skywrapped._fitsnorm.wcs import field_of_view, frame_centre, parse_sexagesimal


def astropy_fov(data: bytes):
    """Test-only truth: field size in degrees from astropy's WCS."""
    from astropy.io import fits
    from astropy.wcs import WCS
    from astropy.wcs.utils import proj_plane_pixel_scales
    from astropy.wcs import FITSFixedWarning

    h = fits.Header.fromstring(data.decode("latin1"))
    with warnings.catch_warnings():
        # astropy's datfix notice (MJD-OBS set from DATE-OBS) is expected for these headers.
        warnings.simplefilter("ignore", FITSFixedWarning)
        wcs = WCS(h)
    sx, sy = proj_plane_pixel_scales(wcs)
    return (h["NAXIS1"] * sx, h["NAXIS2"] * sy)


def test_centre_uses_wcs_not_commanded(fixture):   # truth from astropy pixel_to_world, 2026-11-22
    ra, dec = frame_centre(read_header(fixture("asiair_2600air"))[0])
    assert abs(ra - 60.5738) < 0.02 and abs(dec - 4.1241) < 0.02   # header RA/DEC say 60.93/4.20, CRVAL 60.92/4.75


def test_centre_origin_cdelt(fixture):
    ra, dec = frame_centre(read_header(fixture("origin_678c"))[0])
    assert abs(ra - 61.2756) < 0.01 and abs(dec - 26.3776) < 0.01


def test_falls_back_to_ra_dec_then_objctra():
    assert frame_centre({"RA": 10.68, "DEC": 41.27}) == (10.68, 41.27)
    ra, dec = frame_centre({"OBJCTRA": "00 42 44.3", "OBJCTDEC": "+41 16 09"})
    assert abs(ra - 10.6846) < 1e-3 and abs(dec - 41.2692) < 1e-3
    assert parse_sexagesimal("-05 23 28", hours=False) < 0


def test_no_position_at_all():
    assert frame_centre({}) is None
    assert field_of_view({}) is None


def test_pc_cdelt_matches_cd():
    base = {"NAXIS1": 1000, "NAXIS2": 800, "CRVAL1": 30.0, "CRVAL2": 50.0,
            "CRPIX1": 100.0, "CRPIX2": 200.0}
    cd = dict(base, CD1_1=-0.001, CD1_2=0.0001, CD2_1=0.0002, CD2_2=0.001)
    pc = dict(base, CDELT1=-0.001, CDELT2=0.001, PC1_1=1.0, PC1_2=-0.1, PC2_1=0.2, PC2_2=1.0)
    a, b = frame_centre(cd), frame_centre(pc)
    assert a == pytest.approx(b, abs=1e-9)
    assert field_of_view(cd) == pytest.approx(field_of_view(pc), rel=1e-9)


def test_ra_wraps_into_0_360():
    ra, _ = frame_centre({"NAXIS1": 100, "NAXIS2": 100, "CRVAL1": 0.0, "CRVAL2": 0.0,
                          "CRPIX1": 0.0, "CRPIX2": 50.5, "CDELT1": -0.01, "CDELT2": 0.01})
    assert 0 <= ra < 360 and ra > 359


@pytest.mark.parametrize("s,hours,expected", [
    ("00 42 44.3", True, 10.6846), ("12:30:00", True, 187.5), ("-00 30 00", False, -0.5),
    ("+41 16 09", False, 41.2692), ("5h35m17s", True, 83.8208),
])
def test_parse_sexagesimal(s, hours, expected):
    assert parse_sexagesimal(s, hours) == pytest.approx(expected, abs=1e-3)


def test_parse_sexagesimal_garbage():
    assert parse_sexagesimal("nonsense", True) is None
    assert parse_sexagesimal("", False) is None


@pytest.mark.parametrize("name", ["asiair_2600air", "asiair_4400", "asiair_6200mm", "origin_678c"])
def test_fov_matches_astropy(fixture, name):  # astropy is test-only truth
    v = read_header(fixture(name))[0]
    assert field_of_view(v) == pytest.approx(astropy_fov(fixture(name)), rel=0.01)


def test_fov_from_focal_length():
    w, h = field_of_view({"FOCALLEN": 264, "XPIXSZ": 3.76, "NAXIS1": 6248, "NAXIS2": 4176})
    assert w == pytest.approx(5.099, abs=0.01)


def test_unreadable_or_off_sky_positions_are_none():
    """I3: NaN, infinities and positions off the sky are no position at all."""
    for text in ("NaN", "nan", "inf", "-inf", "+91 00 00", "-90 00 01", "1e400"):
        assert parse_sexagesimal(text, hours=False) is None, text
    for text in ("NaN", "-01 00 00", "24 00 01", "25:00:00"):
        assert parse_sexagesimal(text, hours=True) is None, text
    assert parse_sexagesimal("24 00 00", hours=True) == 0.0 and parse_sexagesimal("90", hours=False) == 90.0
    assert frame_centre({"OBJCTRA": "00 42 44", "OBJCTDEC": "NaN"}) is None
    assert frame_centre({"RA": 361.0, "DEC": 10.0}) is None and frame_centre({"RA": 10.0, "DEC": -95.0}) is None
    assert frame_centre({"RA": 360.0, "DEC": 10.0}) == (0.0, 10.0)
    bad_crval = {"NAXIS1": 100, "NAXIS2": 100, "CRVAL1": 10.0, "CRVAL2": 120.0, "CRPIX1": 50.5, "CRPIX2": 50.5,
                 "CDELT1": -0.01, "CDELT2": 0.01, "RA": 10.0, "DEC": 41.0}
    assert frame_centre(bad_crval) == (10.0, 41.0)  # an impossible plate solve falls back to RA/DEC


def test_absurd_field_size_is_no_field():
    assert field_of_view({"NAXIS1": 1000, "NAXIS2": 800, "CDELT1": 1e6, "CDELT2": 1e6}) is None
    assert field_of_view({"NAXIS1": 1000, "NAXIS2": 800, "FOCALLEN": 1e-9, "XPIXSZ": 3.76}) is None
