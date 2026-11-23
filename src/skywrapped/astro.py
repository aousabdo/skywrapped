"""Low-precision Sun and Moon (Meeus, Astronomical Algorithms ch. 25 and 47). Stdlib only."""
import math
from datetime import datetime

_AU_KM = 149597870.7
_R_EARTH_KM = 6378.14

# (D, M, M', F, sum_l [1e-6 deg], sum_r [1e-3 km])
_LR = [
    (0, 0, 1, 0, 6288774, -20905355), (2, 0, -1, 0, 1274027, -3699111),
    (2, 0, 0, 0, 658314, -2955968), (0, 0, 2, 0, 213618, -569925),
    (0, 1, 0, 0, -185116, 48888), (0, 0, 0, 2, -114332, -3149),
    (2, 0, -2, 0, 58793, 246158), (2, -1, -1, 0, 57066, -152138),
    (2, 0, 1, 0, 53322, -170733), (2, -1, 0, 0, 45758, -204586),
    (0, 1, -1, 0, -40923, -129620), (1, 0, 0, 0, -34720, 108743),
    (0, 1, 1, 0, -30383, 104755), (2, 0, 0, -2, 15327, 0),
    (0, 0, 1, 2, -12528, 0), (0, 0, 1, -2, 10980, 0),
]
# (D, M, M', F, sum_b [1e-6 deg])
_B = [
    (0, 0, 0, 1, 5128122), (0, 0, 1, 1, 280602), (0, 0, 1, -1, 277693),
    (2, 0, 0, -1, 173237), (2, 0, -1, 1, 55413), (2, 0, -1, -1, 46271),
    (2, 0, 0, 1, 32573), (0, 0, 2, 1, 17198), (2, 0, 1, -1, 9266), (0, 0, 2, -1, 8822),
]


def _jd(t: datetime) -> float:
    y, m = t.year, t.month
    if m <= 2:
        y, m = y - 1, m + 12
    a = y // 100
    b = 2 - a + a // 4
    day = t.day + (t.hour + (t.minute + (t.second + t.microsecond / 1e6) / 60) / 60) / 24
    return int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + day + b - 1524.5


def _sin(deg: float) -> float:
    return math.sin(math.radians(deg))


def _cos(deg: float) -> float:
    return math.cos(math.radians(deg))


def _moon_ecliptic(T: float):
    """Geocentric ecliptic longitude, latitude (deg) and distance (km)."""
    Lp = 218.3164477 + 481267.88123421 * T
    D = 297.8501921 + 445267.1114034 * T
    M = 357.5291092 + 35999.0502909 * T
    Mp = 134.9633964 + 477198.8675055 * T
    F = 93.2720950 + 483202.0175233 * T
    E = 1 - 0.002516 * T
    A1 = 119.75 + 131.849 * T
    A2 = 53.09 + 479264.290 * T
    A3 = 313.45 + 481266.484 * T
    sl = sr = sb = 0.0
    for d, m, mp, f, cl, cr in _LR:
        e = E ** abs(m)
        arg = d * D + m * M + mp * Mp + f * F
        sl += cl * e * _sin(arg)
        sr += cr * e * _cos(arg)
    for d, m, mp, f, cb in _B:
        sb += cb * (E ** abs(m)) * _sin(d * D + m * M + mp * Mp + f * F)
    sl += 3958 * _sin(A1) + 1962 * _sin(Lp - F) + 318 * _sin(A2)
    sb += (-2235 * _sin(Lp) + 382 * _sin(A3) + 175 * _sin(A1 - F) + 175 * _sin(A1 + F)
           + 127 * _sin(Lp - Mp) - 115 * _sin(Lp + Mp))
    lon = (Lp + sl / 1e6) % 360
    return lon, sb / 1e6, 385000.56 + sr / 1000


def _sun_ecliptic(T: float):
    """Apparent longitude (deg) and distance (km), Meeus ch. 25."""
    L0 = 280.46646 + 36000.76983 * T
    M = 357.52911 + 35999.05029 * T
    e = 0.016708634 - 0.000042037 * T
    C = ((1.914602 - 0.004817 * T) * _sin(M) + 0.019993 * _sin(2 * M) + 0.000289 * _sin(3 * M))
    true_lon = L0 + C
    nu = M + C
    R = 1.000001018 * (1 - e * e) / (1 + e * _cos(nu))
    omega = 125.04 - 1934.136 * T
    return (true_lon - 0.00569 - 0.00478 * _sin(omega)) % 360, R * _AU_KM


def moon_illumination(t_utc: datetime) -> float:
    """Illuminated fraction of the Moon's disc, 0-1."""
    T = (_jd(t_utc) - 2451545.0) / 36525
    lam, beta, dist = _moon_ecliptic(T)
    slon, sdist = _sun_ecliptic(T)
    cos_psi = _cos(beta) * _cos(lam - slon)
    psi = math.acos(max(-1.0, min(1.0, cos_psi)))
    i = math.atan2(sdist * math.sin(psi), dist - sdist * math.cos(psi))
    return (1 + math.cos(i)) / 2


def moon_altitude(t_utc: datetime, lat: float, lon: float) -> float:
    """Topocentric altitude of the Moon in degrees (no refraction)."""
    jd = _jd(t_utc)
    T = (jd - 2451545.0) / 36525
    lam, beta, dist = _moon_ecliptic(T)
    eps = 23.439291 - 0.0130042 * T
    ra = math.atan2(_sin(lam) * _cos(eps) - math.tan(math.radians(beta)) * _sin(eps), _cos(lam))
    dec = math.asin(_sin(beta) * _cos(eps) + _cos(beta) * _sin(eps) * _sin(lam))
    gmst = (280.46061837 + 360.98564736629 * (jd - 2451545.0) + 0.000387933 * T * T) % 360
    ha = math.radians(gmst + lon) - ra
    phi = math.radians(lat)
    sin_alt = math.sin(phi) * math.sin(dec) + math.cos(phi) * math.cos(dec) * math.cos(ha)
    alt = math.degrees(math.asin(max(-1.0, min(1.0, sin_alt))))
    hp = math.degrees(math.asin(_R_EARTH_KM / dist))  # ~0.95 deg
    return alt - hp * _cos(alt)
