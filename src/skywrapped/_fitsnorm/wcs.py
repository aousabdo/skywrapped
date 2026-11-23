"""Field centre and size from a FITS header's plate solve, else optics. Standard library only."""
import math
import re


def _num(v, key):
    x = v.get(key)
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    return float(x) if math.isfinite(x) else None


def _position(ra, dec):
    """(RA, Dec) when both are finite and on the sky (RA 0-360, wrapped to [0, 360); |Dec| <= 90), else None."""
    if ra is None or dec is None or not (math.isfinite(ra) and math.isfinite(dec)):
        return None
    if not 0.0 <= ra <= 360.0 or abs(dec) > 90.0:
        return None
    return ra % 360.0, dec


def parse_sexagesimal(s, hours):
    """'-05 23 28' / '12:30:00' / '5h35m17s' -> degrees (hours are multiplied by 15). None if unreadable.

    ``hours=True`` reads a right ascension (None outside 0-360 degrees, 24h wraps to 0); ``hours=False`` reads a
    declination (None beyond +-90). Non-finite text ('NaN', 'inf') is None too.
    """
    if not isinstance(s, str):
        return None
    text = s.strip()
    if not text:
        return None
    sign = -1.0 if text.startswith("-") else 1.0
    parts = [p for p in re.split(r"[\s:hdms°'\"′″]+", text.lstrip("+-")) if p]
    if not 1 <= len(parts) <= 3:
        return None
    try:
        nums = [float(p) for p in parts]
    except ValueError:
        return None
    value = sign * sum(n / 60.0 ** i for i, n in enumerate(nums)) * (15.0 if hours else 1.0)
    if not math.isfinite(value):
        return None
    if hours:
        return value % 360.0 if 0.0 <= value <= 360.0 else None
    return value if abs(value) <= 90.0 else None


def _cd_matrix(v):
    """Return the 2x2 CD matrix (deg/pixel) or None if the header has no linear scale."""
    cd = [_num(v, k) for k in ("CD1_1", "CD1_2", "CD2_1", "CD2_2")]
    if any(c is not None for c in cd):
        return [[cd[0] or 0.0, cd[1] or 0.0], [cd[2] or 0.0, cd[3] or 0.0]]
    d1, d2 = _num(v, "CDELT1"), _num(v, "CDELT2")
    if d1 is None or d2 is None:
        return None
    pc = [_num(v, k) for k in ("PC1_1", "PC1_2", "PC2_1", "PC2_2")]
    if any(p is not None for p in pc):
        p11 = 1.0 if pc[0] is None else pc[0]
        p22 = 1.0 if pc[3] is None else pc[3]
        return [[d1 * p11, d1 * (pc[1] or 0.0)], [d2 * (pc[2] or 0.0), d2 * p22]]
    rot = math.radians(_num(v, "CROTA2") or 0.0)
    c, s = math.cos(rot), math.sin(rot)
    return [[d1 * c, -d2 * s], [d1 * s, d2 * c]]


def _wcs_centre(v):
    cd = _cd_matrix(v)
    n1, n2 = _num(v, "NAXIS1"), _num(v, "NAXIS2")
    ra0, dec0 = _num(v, "CRVAL1"), _num(v, "CRVAL2")
    if cd is None or n1 is None or n2 is None or _position(ra0, dec0) is None:
        return None
    crpix1 = _num(v, "CRPIX1")
    crpix2 = _num(v, "CRPIX2")
    if crpix1 is None or crpix2 is None:
        return None
    dx, dy = (n1 + 1) / 2 - crpix1, (n2 + 1) / 2 - crpix2
    x = math.radians(cd[0][0] * dx + cd[0][1] * dy)   # intermediate world coords, radians
    y = math.radians(cd[1][0] * dx + cd[1][1] * dy)
    rho = math.hypot(x, y)
    if rho == 0.0:
        return ra0 % 360.0, dec0
    c = math.atan(rho)                                 # TAN: angular distance from the tangent point
    d0 = math.radians(dec0)
    sin_c, cos_c = math.sin(c), math.cos(c)
    dec = math.asin(max(-1.0, min(1.0, cos_c * math.sin(d0) + y * sin_c * math.cos(d0) / rho)))
    dra = math.atan2(x * sin_c, rho * math.cos(d0) * cos_c - y * math.sin(d0) * sin_c)
    return (ra0 + math.degrees(dra)) % 360.0, math.degrees(dec)


def frame_centre(v):
    """(RA, Dec) in degrees at the frame centre; plate solve first, then RA/DEC, then OBJCTRA/OBJCTDEC."""
    c = _wcs_centre(v)
    if c is not None:
        return _position(*c)
    c = _position(_num(v, "RA"), _num(v, "DEC"))
    if c is not None:
        return c
    return _position(parse_sexagesimal(v.get("OBJCTRA"), hours=True), parse_sexagesimal(v.get("OBJCTDEC"), hours=False))


def _field(w, h):
    """A field no wider than the sky (garbage scales would make the catalogue search endless), else None."""
    ok = all(math.isfinite(x) and 0.0 < x <= 360.0 for x in (w, h))
    return (w, h) if ok else None


def field_of_view(v):
    """(width, height) in degrees from the WCS scale, else from pixel size and focal length."""
    n1, n2 = _num(v, "NAXIS1"), _num(v, "NAXIS2")
    if n1 is None or n2 is None:
        return None
    cd = _cd_matrix(v)
    if cd is not None:
        sx = math.hypot(cd[0][0], cd[1][0])
        sy = math.hypot(cd[0][1], cd[1][1])
        if sx > 0 and sy > 0 and _field(n1 * sx, n2 * sy):
            return n1 * sx, n2 * sy
    focal, pix = _num(v, "FOCALLEN"), _num(v, "XPIXSZ")
    if focal and pix and focal > 0 and pix > 0:
        scale = 206.265 * pix / focal / 3600.0         # degrees per pixel
        return _field(n1 * scale, n2 * scale)
    return None
