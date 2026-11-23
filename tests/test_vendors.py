"""Capture sources beyond ASIAIR and the Origin: detection, local-time and stack rules, per fixture."""
from datetime import date, datetime, timedelta

import pytest

from helpers import cw
from skywrapped import TESTED_VENDORS
from skywrapped._fitsnorm import read_header, to_frame

SENTINEL = (12.3456, -65.4321)


def frame_of(fixture, name, path, **override):
    values, comments = read_header(fixture(name))
    values = {**values, **override}
    return to_frame(values, comments, path)


def test_nina(fixture):
    f = frame_of(fixture, "nina", "2026-10-03/LIGHT/2026-10-03_22-14-09__-9.90_180.00s_0001.fits")
    assert (f.vendor, f.frame_type, f.is_stack) == ("nina", "light", False)
    assert f.exposure_s == f.integration_s == 180.0
    # DATE-OBS is UTC; DATE-LOC (local) is not used as the start
    assert f.start_utc == datetime(2026, 10, 4, 3, 14, 9, 123456) and f.start_local is None
    assert f.camera == "ZWO ASI2600MC Pro" and f.telescope == "Refractor 80mm" and f.focal_mm == 480
    assert f.gain == 100 and f.filter == "L-Ultimate" and f.site == SENTINEL


def test_seestar_sub(fixture):
    f = frame_of(fixture, "seestar_sub", "M 31_sub/Light_M 31_10.0s_IRCUT_20260513-201245.fit")
    assert (f.vendor, f.frame_type, f.is_stack) == ("seestar", "light", False)
    assert f.exposure_s == f.integration_s == 10.0 and f.sub_count == 1
    assert f.start_utc == datetime(2026, 5, 14, 3, 12, 45, 931528) and f.start_local is None
    assert f.camera == f.telescope == "Seestar S50" and f.focal_mm == 250 and f.gain == 80 and f.site == SENTINEL


def test_seestar_stack(fixture):
    f = frame_of(fixture, "seestar_stack", "Stacked_120_M 31_10.0s_IRCUT_20260513-201245.fit")
    assert (f.vendor, f.frame_type, f.is_stack) == ("seestar", "light", True)
    assert f.sub_count == 120 and f.exposure_s == 10.0 and f.integration_s == 1200.0
    assert f.fov_deg is not None and f.ra_deg == pytest.approx(10.68, abs=0.05)


def test_seestar_stack_without_total_keyword(fixture):
    values, comments = read_header(fixture("seestar_stack"))
    del values["TOTALEXP"]
    f = to_frame(values, comments, "x.fit")
    assert f.is_stack and f.integration_s == 1200.0  # STACKCNT x EXPTIME


def test_dwarf_sub(fixture):
    f = frame_of(fixture, "dwarf_sub", "IC 434_60s60_Astro_20260211-213012250_14C.fits")
    assert (f.vendor, f.is_stack) == ("dwarf", False)
    assert f.frame_type == "unknown"  # no IMAGETYP/FRAME: counted, flagged as assumed
    assert f.exposure_s == f.integration_s == 60.0
    # DATE-OBS is the END of the exposure in the device's own clock: start = end - exposure, as local time
    assert f.start_local == datetime(2026, 2, 11, 21, 29, 12, 250000) and f.start_utc is None
    assert f.camera == f.telescope == "Dwarf 3" and f.focal_mm == 150 and f.gain == 60 and f.site is None


def test_dwarf_stack_marked_by_three_planes(fixture):
    f = frame_of(fixture, "dwarf_stack", "IC 434_60s60_Astro_20260212-001540500.fits")
    assert (f.vendor, f.is_stack) == ("dwarf", True)
    assert f.exposure_s == f.integration_s == 1500.0 and f.sub_count == 1
    assert f.start_local == datetime(2026, 2, 12, 0, 15, 40, 500000) - timedelta(seconds=1500)


def test_dwarf_fitsstudio_stack(fixture):
    f = frame_of(fixture, "dwarf_fitsstudio", "fits-studio-sample-m42.fits")
    assert (f.vendor, f.is_stack, f.integration_s) == ("dwarf", True, 9540.0)
    assert f.camera == f.telescope == "Dwarf 3"


def test_dwarf_stack_marked_by_name_or_restack(fixture):
    sub_values, comments = read_header(fixture("dwarf_sub"))
    named = to_frame(sub_values, comments, "stacked-16_IC 434_60s60_Astro_20260211-213012250.fits")
    assert named.is_stack
    mega = to_frame({**sub_values, "RESTACK": 1}, comments, "x.fits")
    assert mega.is_stack


def test_ekos(fixture):
    f = frame_of(fixture, "ekos", "Light/M_47/M_47_Light_LPR_030_secs_2020-02-05T07-43-19.fits")
    assert (f.vendor, f.frame_type, f.is_stack) == ("ekos", "light", False)
    assert f.exposure_s == f.integration_s == 30.0
    assert f.start_utc == datetime(2020, 2, 5, 7, 43, 19, 609000) and f.start_local is None
    assert f.focal_mm == 900 and f.camera == "CCD Simulator" and f.site == SENTINEL


def test_asiair_and_origin_are_not_taken_over(fixture):
    assert frame_of(fixture, "asiair_2600air", "a.fit").vendor == "asiair"
    assert frame_of(fixture, "origin_678c", "a.fit").vendor == "origin"
    assert frame_of(fixture, "asiair_duo_awstack", "a.fit").vendor == "generic"  # AstroWizard stack: no capture app named


def test_tested_vendors_have_fixtures():
    assert set(TESTED_VENDORS) == {"ASIAIR", "Celestron Origin", "N.I.N.A.", "ZWO Seestar", "Dwarf 3", "Ekos/KStars"}


def _stack_on(fixture, night_day, count):
    return frame_of(fixture, "seestar_stack", f"Stacked_{count}_M 31_{night_day}.fit",
                    **{"STACKCNT": count, "TOTALEXP": 10.0 * count, "DATE-OBS": f"2026-05-{night_day}T03:00:00.000000"})


def test_seestar_stack_only_folder(fixture):
    stacks = [_stack_on(fixture, 10, 120), _stack_on(fixture, 12, 60), _stack_on(fixture, 14, 30)]
    w = cw(stacks, today=date(2026, 12, 1))
    assert w.hours == pytest.approx((1200 + 600 + 300) / 3600)
    assert w.frames == 210
    assert w.nights == 3 and w.targets == 1 and w.from_stacks_only


def test_seestar_stack_with_its_subs_is_not_double_counted(fixture):
    subs = [frame_of(fixture, "seestar_sub", f"Light_M 31_{i}.fit",
                     **{"DATE-OBS": f"2026-05-14T03:{i:02d}:00.000000"}) for i in range(10, 20)]
    stack = _stack_on(fixture, 14, 120)
    w = cw(subs + [stack], today=date(2026, 12, 1))
    assert w.frames == 10 and w.hours == pytest.approx(100 / 3600)
    assert w.skipped["stack_with_subs"] == 1 and not w.from_stacks_only


def test_dwarf_calibration_folder_is_not_counted_as_light(fixture):
    f = frame_of(fixture, "dwarf_sub", "DWARF_RAW_CALI_FRAME/x.fits")
    assert f.vendor == "dwarf" and f.frame_type == "calibration"
    w = cw([f, frame_of(fixture, "dwarf_sub", "M42/x.fits")], today=date(2026, 12, 1))
    assert w.skipped["calibration"] == 1 and w.frames == 1


def test_seestar_stacks_on_other_nights_count(fixture):
    """C3: a stack is dropped only when its target has subs from the same camera on the same night."""
    subs = [frame_of(fixture, "seestar_sub", f"Light_M 31_{i}.fit",
                     **{"DATE-OBS": f"2026-05-14T03:{i:02d}:00.000000"}) for i in range(10, 20)]
    same_night = _stack_on(fixture, 14, 120)
    others = [_stack_on(fixture, d, 60) for d in (10, 12, 16, 18, 20)]
    w = cw(subs + [same_night] + others, today=date(2026, 12, 1))
    assert w.skipped["stack_with_subs"] == 1
    assert w.nights == 6 and w.hours == pytest.approx((10 * 10 + 5 * 600) / 3600)
    assert w.frames == 10 + 5 * 60 and w.targets == 1 and not w.from_stacks_only


def test_stack_on_a_night_without_subs_from_that_camera_counts(fixture):
    subs = [frame_of(fixture, "seestar_sub", f"Light_M 31_{i}.fit",
                     **{"DATE-OBS": f"2026-05-14T03:{i:02d}:00.000000", "INSTRUME": "Seestar S30"})
            for i in range(10, 20)]
    stack = _stack_on(fixture, 14, 120)  # the S50's own stack of the same night: not these subs' stack
    w = cw(subs + [stack], today=date(2026, 12, 1))
    assert w.skipped["stack_with_subs"] == 0 and w.frames == 10 + 120


def test_seestar_stack_is_not_a_duplicate_of_its_first_sub(fixture):
    """I1: the stack starts with its first sub and has the sub's EXPTIME; it is no copy of it."""
    t0 = datetime(2026, 5, 14, 3, 12, 45, 931528)
    subs = [frame_of(fixture, "seestar_sub", f"Light_M 31_{i:03d}.fit",
                     **{"DATE-OBS": (t0 + timedelta(seconds=10 * i)).isoformat()}) for i in range(120)]
    stack = frame_of(fixture, "seestar_stack", "Stacked_120_M 31_10.0s_IRCUT_20260513-201245.fit")
    assert stack.start_utc == subs[0].start_utc and stack.exposure_s == subs[0].exposure_s
    for order in (subs + [stack], [stack] + subs):
        w = cw(order, today=date(2026, 12, 1))
        assert w.frames == 120 and w.hours == pytest.approx(1200 / 3600)
        assert w.skipped["duplicate"] == 0 and w.skipped["stack_with_subs"] == 1


def test_seestar_stack_detected_from_telescop_only(fixture):
    f = frame_of(fixture, "seestar_stack", "x/stack.fit", CREATOR=None, INSTRUME=None, TELESCOP="S50_abc123")
    assert f.vendor == "seestar" and f.is_stack
    f = frame_of(fixture, "seestar_stack", "x/stack.fit", CREATOR=None, INSTRUME=None, TELESCOP="S50")
    assert f.vendor == "seestar"


def test_seestar_stack_detected_from_file_name_and_counts(fixture):
    f = frame_of(fixture, "seestar_stack", "x/Stacked_120_M 31_10.0s.fit", CREATOR=None, INSTRUME=None, TELESCOP=None)
    assert f.vendor == "seestar"
    f = frame_of(fixture, "seestar_stack", "x/Stacked_120_M 31_10.0s.fit", CREATOR=None, INSTRUME=None, TELESCOP=None,
                 STACKCNT=None, TOTALEXP=None)
    assert f.vendor == "generic"


def test_dwarf_detected_from_telescop(fixture):
    f = frame_of(fixture, "dwarf_sub", "x/y.fits", ORIGIN=None, INSTRUME=None, TELESCOP="DWARFIII")
    assert f.vendor == "dwarf"


def test_session_rule_applies_to_telescop_only_seestar_stack(fixture):
    subs = [frame_of(fixture, "seestar_sub", f"Light_M 31_{i}.fit",
                     **{"DATE-OBS": f"2026-05-14T03:{i:02d}:00.000000"}) for i in range(10, 20)]
    other_night = frame_of(fixture, "seestar_stack", "Stacked_60_M 31_x.fit", CREATOR=None, INSTRUME=None,
                           TELESCOP="S50", **{"STACKCNT": 60, "TOTALEXP": 600.0, "DATE-OBS": "2026-05-20T03:00:00.000000"})
    w = cw(subs + [other_night], today=date(2026, 12, 1))
    assert other_night.vendor == "seestar"
    assert w.skipped["stack_with_subs"] == 0 and w.frames == 10 + 60  # session rule: another night counts
