from datetime import date, datetime

from skywrapped._fitsnorm import Frame
from skywrapped.nights import assign_nights


def fr(utc=None, local=None, site=None):
    return Frame(
        path="x.fit", vendor="test", frame_type="light", is_stack=False, sub_count=1,
        exposure_s=60.0, integration_s=60.0,
        start_utc=datetime(*utc) if utc else None,
        start_local=datetime(*local) if local else None,
        object_hint=None, ra_deg=None, dec_deg=None, fov_deg=None, focal_mm=None,
        camera=None, telescope=None, filter=None, gain=None, iso=None, sensor_c=None,
        site=site,
    )


def test_night_from_site():  # 21:45 local on the 5th
    ni = assign_nights([fr(utc=(2026, 9, 6, 5, 11), site=(31.96, -111.60))], 0)
    assert ni.nights == [date(2026, 9, 5)]


def test_night_origin_local():
    ni = assign_nights([fr(local=(2026, 11, 11, 1, 41))], -5)
    assert ni.nights == [date(2026, 11, 10)] and ni.utc == [datetime(2026, 11, 11, 6, 41)]


def test_origin_local_with_site():  # R11: night from local; UTC via site longitude
    ni = assign_nights([fr(local=(2026, 11, 11, 1, 41), site=(31.96, -111.60))], -5)
    assert ni.nights == [date(2026, 11, 10)]
    want = datetime(2026, 11, 11, 1, 41) + (datetime(2026, 11, 11, 7, 26, 24) - datetime(2026, 11, 11))
    assert abs((ni.utc[0] - want).total_seconds()) < 60
    assert abs((ni.utc[0] - datetime(2026, 11, 11, 9, 7)).total_seconds()) < 60


def test_daytime_check_reestimates():  # laptop says +8, local 10:00-14:00
    ni = assign_nights([fr(utc=(2026, 3, 10, 2 + i // 5, (i % 5) * 10)) for i in range(20)], 8)
    assert ni.estimated and set(ni.nights) == {date(2026, 3, 9)}


def test_no_reestimate_when_plausible():
    ni = assign_nights([fr(utc=(2026, 3, 10, 4, i)) for i in range(10)], -7)
    assert not ni.estimated and set(ni.nights) == {date(2026, 3, 9)}


def test_year_boundary():
    ni = assign_nights([fr(utc=(2027, 1, 1, 3, 0), site=(31.96, -111.60))], 0)
    assert ni.nights == [date(2026, 12, 31)]


def test_unknown_time_does_not_crash():
    ni = assign_nights([fr(), fr(utc=(2026, 3, 10, 4, 0))], -7)
    assert ni.nights[0] is None and ni.utc[0] is None and ni.nights[1] == date(2026, 3, 9)


def test_empty():
    ni = assign_nights([], 0)
    assert ni.nights == [] and not ni.estimated
