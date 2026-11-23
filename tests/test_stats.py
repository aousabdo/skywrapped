from dataclasses import replace
from datetime import date

import pytest

from helpers import cw, fr
from skywrapped.stats import to_summary


def nights_series(start, n, **kw):
    from datetime import timedelta
    d0 = date(*start)
    out = []
    for i in range(n):
        d = d0 + timedelta(days=i)
        out.append(fr(night=(d.year, d.month, d.day), **kw))
    return out


def busy_night(night, focals):
    return [fr(night=night, focal_mm=f, exposure_s=600.0) for f in focals for _ in range(2)]


def test_counts_lights_only():
    w = cw([fr(exposure_s=300) for _ in range(3)] + [fr(frame_type="dark", exposure_s=300) for _ in range(2)]
           + [fr(frame_type="flat", exposure_s=1)])
    assert (w.hours, w.frames, w.skipped["calibration"]) == (0.25, 3, 3)


def test_other_types_are_never_counted():
    w = cw([fr(), fr(frame_type="other"), fr(frame_type="other")])
    assert (w.frames, w.skipped["not_light"], w.skipped["type_assumed"]) == (1, 2, 0)
    from skywrapped.stats import NoLightsError
    with pytest.raises(NoLightsError):
        cw([fr(frame_type="other")])


def test_duplicates_once():
    a = fr(path="x/a.fit")
    b = replace(a, path="backup/a.fit")
    w = cw([a, b])
    assert w.frames == 1 and w.skipped["duplicate"] == 1


def test_duplicate_key_ignores_subsecond_but_not_camera():
    a = fr(camera="A")
    b = replace(a, start_utc=a.start_utc.replace(microsecond=a.start_utc.microsecond ^ 1))
    c = replace(a, camera="B")
    w = cw([a, b, c])
    assert w.frames == 2 and w.skipped["duplicate"] == 1


def test_duplicate_key_separates_stack_focal_group_and_filter():
    a = fr(camera="A", filter="Ha")
    w = cw([a, replace(a, path="copy.fit"), replace(a, is_stack=True, sub_count=2, integration_s=600.0),
            replace(a, filter="OIII"), replace(a, focal_mm=1000.0), replace(a, focal_mm=264.0 * 1.01)])
    assert w.skipped["duplicate"] == 2  # the copy, and the same focal group 1% longer


def test_stack_ignored_when_subs_present():
    subs = [fr(ra=83.8, dec=-2.4, t=i) for i in range(40)]
    st = fr(ra=83.8, dec=-2.4, stack=40)
    w = cw(subs + [st])
    assert w.hours == pytest.approx(40 * 300 / 3600) and w.skipped["stack_with_subs"] == 1
    assert not w.from_stacks_only


def test_stacks_only():
    w = cw([fr(exposure_s=10, stack=120, ra=83.8, dec=-5.4, t=i * 5000) for i in range(2)])
    assert w.hours == pytest.approx(2 * 120 * 10 / 3600) and w.frames == 240 and w.from_stacks_only


def test_unknown_counts_and_is_flagged():
    w = cw([fr(frame_type="unknown"), fr()])
    assert w.frames == 2 and w.skipped["type_assumed"] == 1


def test_no_time_skipped():
    w = cw([fr(), replace(fr(), start_utc=None, start_local=None)])
    assert w.frames == 1 and w.skipped["no_time"] == 1


def test_year_filter_and_partial():
    w = cw([fr(night=(2025, 12, 31)), fr(night=(2026, 1, 1))], year=2026)
    assert w.frames == 1 and w.skipped["outside_year"] == 1 and w.partial
    assert not cw([fr(night=(2025, 12, 31))], year=2025).partial


def test_streak_busiest_best_month():
    w = cw(nights_series((2026, 5, 28), 13) + busy_night((2026, 11, 3), [264, 541, 783, 783 * 0.985]))
    assert w.longest_streak == (13, date(2026, 5, 28), date(2026, 6, 9))
    assert w.busiest_night.date == date(2026, 11, 3) and w.busiest_night.telescopes == 3
    assert w.nights == 14 and w.first_night == date(2026, 5, 28) and w.last_night == date(2026, 11, 3)
    assert w.best_month[0] == 11


def test_setups_merge_focal_group_and_strip_zwo():
    fs = [fr(focal_mm=771, camera="ZWO ASI2600MC Air"), fr(focal_mm=783, camera="ZWO ASI2600MC Air"),
          fr(focal_mm=264, camera="ZWO ASI2600MC Air", telescope="Esprit 100")]
    w = cw(fs)
    assert sorted((s.label, s.frames) for s in w.setups) == [("777 mm \u00b7 ASI2600MC Air", 2), ("Esprit 100 \u00b7 ASI2600MC Air", 1)]


def test_unnamed_clusters_counted_separately():
    fs = [fr(ra=10.0, dec=-80.0), fr(ra=200.0, dec=-80.0)]
    w = cw(fs)
    assert w.targets == len(w.top_targets) == 2


def test_target_stats():
    fs = [fr(ra=83.8, dec=-5.4, night=(2026, 1, 1)) for _ in range(4)] + [fr(ra=83.8, dec=-5.4, night=(2026, 1, 2))]
    w = cw(fs)
    t = w.top_targets[0]
    assert (t.frames, t.nights) == (5, 2) and t.hours == pytest.approx(5 * 300 / 3600)


def test_moon_share_flag():
    assert cw([fr(site=(31.96, -111.60))]).moon_uses_altitude and not cw([fr(site=None)]).moon_uses_altitude


def test_moon_fields_sane():
    w = cw(nights_series((2026, 11, 1), 10))
    assert 0 <= w.bright_moon_share <= 1 and 0 <= w.full_moon_nights <= 10
    assert all(0 <= n.moon <= 1 for n in w.per_night)


def test_coldest_sensor():
    assert cw([fr(sensor_c=-10.0), fr(sensor_c=-20.0), fr()]).coldest_sensor_c == -20.0
    assert cw([fr()]).coldest_sensor_c is None


def test_passed_skipped_merged_and_empty_raises():
    from skywrapped.stats import NoLightsError
    w = cw([fr()], skipped={"unreadable": 4})
    assert w.skipped["unreadable"] == 4 and w.skipped["calibration"] == 0
    with pytest.raises(NoLightsError) as e:
        cw([fr(frame_type="dark")])
    assert isinstance(e.value, ValueError) and e.value.years == ()
    with pytest.raises(NoLightsError) as e:
        cw([fr(night=(2025, 3, 3)), fr(night=(2023, 3, 3))], year=2026)
    assert e.value.years == (2023, 2025)


def test_summary_json_safe():
    import json
    w = cw(nights_series((2026, 5, 28), 3))
    s = to_summary(w)
    json.dumps(s)
    assert s["frames"] == 3 and s["first_night"] == "2026-05-28"


def test_no_focal_is_not_a_telescope():
    w = cw([fr(night=(2026, 3, 3), focal_mm=264), fr(night=(2026, 3, 3), focal_mm=541),
            fr(night=(2026, 3, 3), focal_mm=None)])
    assert w.busiest_night.telescopes == 2 and w.per_night[0].telescopes == 2


def test_bright_moon_below_horizon_not_counted():
    from datetime import datetime, timedelta
    from skywrapped.astro import moon_altitude, moon_illumination
    site = (31.96, -111.60)
    t = datetime(2026, 11, 1, 0, 0)
    below = up = None
    for i in range(24 * 30):
        x = t + timedelta(hours=i)
        if moon_illumination(x) > 0.55:
            alt = moon_altitude(x, *site)
            if alt < -10 and below is None:
                below = x
            if alt > 10 and up is None:
                up = x
    assert below and up
    def one(x):
        return fr(start=x - timedelta(seconds=150), site=site)
    assert cw([one(below)]).bright_moon_share == 0
    assert cw([one(up)]).bright_moon_share == 1


def test_desktop_stack_is_dropped_when_its_target_has_subs_on_other_nights():
    """A desktop stacker (generic/AstroWizard/Siril) combines many nights: dropped whenever subs exist."""
    subs = [fr(ra=83.8, dec=-2.4, night=(2026, 9, d)) for d in (1, 2, 3) for _ in range(4)]
    st = fr(ra=83.8, dec=-2.4, stack=12, night=(2026, 9, 10))  # dated a night with no subs
    w = cw(subs + [st])
    assert w.skipped["stack_with_subs"] == 1
    assert w.frames == 12 and w.hours == pytest.approx(12 * 300 / 3600)


def test_session_stack_without_camera_is_dropped_by_same_night_subs():
    subs = [fr(ra=83.8, dec=-2.4, night=(2026, 9, 1), vendor="seestar", camera="S50") for _ in range(4)]
    st = fr(ra=83.8, dec=-2.4, stack=4, night=(2026, 9, 1), vendor="seestar", camera=None)
    w = cw(subs + [st])
    assert w.skipped["stack_with_subs"] == 1 and w.frames == 4


def test_session_stack_on_another_night_still_counts():
    subs = [fr(ra=83.8, dec=-2.4, night=(2026, 9, 1), vendor="seestar", camera="S50") for _ in range(4)]
    st = fr(ra=83.8, dec=-2.4, stack=4, night=(2026, 9, 5), vendor="seestar", camera="S50")
    w = cw(subs + [st])
    assert w.skipped["stack_with_subs"] == 0 and w.frames == 8


def test_top_targets_keeps_every_target_and_journey_sees_the_farthest():
    from skywrapped.cards import render_cards
    from skywrapped.catalogue import distance_ly
    names = ["M42", "M31", "M45", "M81", "M13", "M51", "M101", "M33", "M27", "M57", "M8", "M104"]
    fs = []
    for i, n in enumerate(names):
        fs += [fr(hint=n, night=(2026, 1, 1 + i)) for _ in range(len(names) - i)]  # M104 gets the fewest hours
    w = cw(fs)
    assert w.targets == len(w.top_targets) == 12
    assert [t.hours for t in w.top_targets] == sorted((t.hours for t in w.top_targets), reverse=True)
    far = max(w.top_targets, key=lambda t: t.distance_ly or 0)
    assert far is w.top_targets[-1] and far.distance_ly == distance_ly("M104")
    cards = {c.name: c.svg for c in render_cards(w)}
    assert "M 104" in cards["journey"]
    assert len(to_summary(w)["top_targets"]) == 12
    import re
    assert len(re.findall(r"<text", cards["targets"])) < 30  # the targets card still shows five
