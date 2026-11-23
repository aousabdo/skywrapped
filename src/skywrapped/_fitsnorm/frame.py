"""Normalise a FITS/XISF header into a Frame record. Standard library only."""
import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from .header import HeaderError
from .labels import clean_label
from .wcs import field_of_view, frame_centre

MAX_EXPOSURE_S = 86_400.0  # one sub longer than a day is not a real value
MAX_SUBS = 100_000         # nor is a stack of more subs than this

_MOUNT = re.compile(r"AM\d|EQ-?\d|HEQ\d|CEM\d|GEM\d|CGX|CGEM|EQM|iOptron|GTi|AZ-?GTi|Simulator|Telescope Driver"
                    r"|^\s*$|Mount", re.I)
_ASIAIR = re.compile(r"ASIAIR|ZWO \d+AIR", re.I)
_STACK_WORDS = {"stack", "stacked", "master", "integration", "drizzle", "drizzled"}
_NAME_TYPES = (("darkflat", "darkflat"), ("dark", "dark"), ("flat", "flat"), ("bias", "bias"), ("light", "light"))
_SITE_KEYS = (("SITELAT", "SITELONG"), ("LAT-OBS", "LONG-OBS"), ("OBSGEO-B", "OBSGEO-L"), ("LATITUDE", "LONGITUD"))
_DT = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.(\d+))?)?)?\s*(Z|[+-]\d{2}:?\d{2})?$")


@dataclass(frozen=True)
class Frame:
    path: str
    vendor: str
    frame_type: str
    is_stack: bool
    sub_count: int
    exposure_s: float
    integration_s: float
    start_utc: datetime | None
    start_local: datetime | None
    object_hint: str | None
    ra_deg: float | None
    dec_deg: float | None
    fov_deg: tuple[float, float] | None
    focal_mm: float | None
    camera: str | None
    telescope: str | None
    filter: str | None
    gain: float | None
    iso: int | None
    sensor_c: float | None
    site: tuple[float, float] | None


def _num(v, key):
    x = v.get(key)
    if isinstance(x, bool):
        return None
    if isinstance(x, str):
        try:
            x = float(x)
        except ValueError:
            return None
    if not isinstance(x, (int, float)) or not math.isfinite(x):
        return None
    return float(x)


def _text(v, key):
    x = v.get(key)
    if x is None or isinstance(x, bool):
        return None
    s = str(x).strip()
    return s or None


def _parse_dt(date, time):
    """Return a naive datetime (UTC if the string carries an offset) or None."""
    if not isinstance(date, str):
        return None
    m = _DT.match(date.strip())
    if not m:
        return None
    y, mo, d, hh, mm, ss, frac, tz = m.groups()
    try:
        if hh is None:
            t = _text({"t": time}, "t")
            tm = re.match(r"^(\d{1,2}):(\d{2})(?::(\d{2})(?:\.(\d+))?)?$", t) if t else None
            if not tm:
                return None  # no time of day: never invent a midnight start
            hh, mm, ss, frac = tm.groups()
        ss = ss or "0"
        us = int((frac or "0")[:6].ljust(6, "0"))
        dt = datetime(int(y), int(mo), int(d), int(hh), int(mm), int(ss), us)
    except ValueError:
        return None
    if tz and tz != "Z":
        sign = 1 if tz[0] == "+" else -1
        digits = tz[1:].replace(":", "")
        dt -= sign * timedelta(hours=int(digits[:2]), minutes=int(digits[2:]))
    return dt


def _file_name(path):
    return path.replace("\\", "/").rsplit("/", 1)[-1]


_SEESTAR_SCOPE = re.compile(r"^S\s?(30|50)(?:_.*)?$", re.I)
_SEESTAR_STACK_NAME = re.compile(r"^Stacked_\d+_", re.I)


def _str(v, key):
    """A header value only when it is a string (a numeric FRAME is a counter, not a type)."""
    return _text(v, key) if isinstance(v.get(key), str) else None


def _vendor(v, name=""):
    creator = _text(v, "CREATOR") or ""
    if creator.startswith("Origin "):
        return "origin"
    if _ASIAIR.search(creator):
        return "asiair"
    if "N.I.N.A." in (_text(v, "SWCREATE") or ""):
        return "nina"
    if "seestar" in creator.lower() or (_text(v, "INSTRUME") or "").lower().startswith("seestar"):
        return "seestar"
    scope = _text(v, "TELESCOP") or ""
    if _SEESTAR_SCOPE.match(scope) or (
            _SEESTAR_STACK_NAME.match(name) and (_num(v, "STACKCNT") is not None or _num(v, "TOTALEXP") is not None)):
        return "seestar"
    if scope.upper().startswith("DWARF"):
        return "dwarf"
    if (_text(v, "ORIGIN") or "").upper() == "DWARFLAB" or (_text(v, "INSTRUME") or "").upper().startswith("DWARF"):
        return "dwarf"
    # INDI drivers (Ekos/KStars) write FRAME and PIXSIZE1 together; no other capture app does
    if _str(v, "FRAME") and _num(v, "PIXSIZE1") is not None:
        return "ekos"
    return "generic"


def _type_from_keyword(raw):
    s = raw.lower().replace("frame", "")
    s = re.sub(r"[\s_-]+", " ", s).strip()
    if "dark flat" in s or "darkflat" in s or "flatdark" in s or "flat dark" in s:
        return "darkflat"
    for word in ("bias", "offset", "zero"):
        if word in s:
            return "bias"
    if "dark" in s:
        return "dark"
    if "flat" in s:
        return "flat"
    for word in ("light", "object", "science"):
        if word in s:
            return "light"
    return None


_CAL_WORDS = {
    "darkflat": "darkflat", "darkflats": "darkflat", "flatdark": "darkflat", "flatdarks": "darkflat",
    "dark": "dark", "darks": "dark", "flat": "flat", "flats": "flat",
    "bias": "bias", "biases": "bias", "offset": "bias", "offsets": "bias",
    "cali": "calibration", "calibration": "calibration", "master": "calibration", "masters": "calibration",
}
_CAL_ORDER = ("darkflat", "dark", "flat", "bias", "calibration")
_NEUTRAL_WORDS = {"raw", "frame", "frames", "dwarf", "library", "lib", "tele", "wide"}
_NEUTRAL_PATTERN = re.compile(r"^(\d+|\d+(\.\d+)?(s|ms|sec)|-?\d+c|gain\d+|bin\d+|iso\d+)$")


def _folder_type(path):
    """Type from the two nearest folders, only when a folder is clearly calibration: every token of its name is a
    calibration or neutral word (or number/exposure/temperature/gain/bin/iso) and at least one is calibration."""
    dirs = path.replace("\\", "/").split("/")[:-1]
    for d in reversed(dirs[-2:]):
        tokens = [t for t in re.split(r"[^a-z0-9]+", d.lower()) if t]
        cal = {_CAL_WORDS[t] for t in tokens if t in _CAL_WORDS}
        if cal and all(t in _CAL_WORDS or t in _NEUTRAL_WORDS or _NEUTRAL_PATTERN.match(t) for t in tokens):
            return next(c for c in _CAL_ORDER if c in cal)
    return None


_COORD_FRAMES = {"icrs", "fk4", "fk5", "galactic", "ecliptic"}  # a FRAME card naming a coordinate system


def _frame_type(v, name, path=""):
    """light/dark/flat/bias/darkflat/calibration from IMAGETYP or FRAME; "other" when a type keyword is present but
    names no known type (SNAPSHOT, FOCUS, TEST...: never counted); otherwise from the file name, then the folders,
    and "unknown" (counted as a light, flagged) only when no type keyword exists at all."""
    present = False
    for key in ("IMAGETYP", "FRAME"):
        # only a string is a type keyword: a numeric FRAME = 12 is a frame counter
        raw = _text(v, key) if isinstance(v.get(key), str) else None
        if not raw or (key == "FRAME" and raw.lower() in _COORD_FRAMES):
            continue
        present = True
        t = _type_from_keyword(raw)
        if t:
            return t
    if present:
        return "other"
    low = name.lower()
    for prefix, t in _NAME_TYPES:
        if low.startswith(prefix + "_"):
            return t
    return _folder_type(path) or "unknown"


def _stack_by_name(lname):
    if lname.startswith("light_"):
        return False
    return any(t in _STACK_WORDS or t.endswith("stack") for t in re.split(r"[^a-z0-9]+", lname))


def _gear(vendor, v):
    """(camera, telescope) names fit to print (labels.clean_label); smart scopes get their product name."""
    cam_raw, scope_raw = _text(v, "INSTRUME"), _text(v, "TELESCOP")
    both = f"{cam_raw or ''} {scope_raw or ''}"
    if vendor == "seestar":  # TELESCOP is "S50_<device id>"
        name = "Seestar S30" if re.search(r"S\s*30", both, re.I) else "Seestar S50"
        return name, name
    if vendor == "dwarf":  # "DWARFIII" in both cards
        name = "Dwarf 2" if re.search(r"DWARF\s*(II|2)(?![I\d])", both, re.I) else "Dwarf 3"
        return name, name
    telescope = None if scope_raw is None or _MOUNT.search(scope_raw) else clean_label(scope_raw)
    camera = clean_label(cam_raw) or ("Camera" if cam_raw else None)
    return camera, telescope


def _site(v):
    for la, lo in _SITE_KEYS:
        lat, lon = _num(v, la), _num(v, lo)
        if lat is not None and lon is not None:
            if lat == 0.0 and lon == 0.0:
                continue
            return (lat, lon)
    return None


def to_frame(values: dict, comments: dict, path: str) -> Frame:
    """Normalise one header. A stack flagged only by its file name (no NCOMBINE/STACKCNT/LIVETIME/
    TOTALEXP/EXPTOT) keeps sub_count=1 and integration_s=exposure_s: err low, never N-fold high."""
    v = values
    name = _file_name(path)
    vendor = _vendor(v, name)

    # an implausible count is unknown (ignored); see the exposure below
    counts = [c for c in (_num(v, "NCOMBINE"), _num(v, "STACKCNT")) if c is not None and c <= MAX_SUBS]
    count = max(counts, default=0.0)
    kinds = ((_str(v, "IMAGETYP") or "") + " " + (_str(v, "FRAME") or "")).lower()
    is_stack = count > 1 or "master" in kinds or _stack_by_name(name.lower())
    sub_count = int(count) if count > 1 else 1
    if vendor == "dwarf":
        # a Dwarf stack is a 3-plane image (raw subs are one Bayer plane) or says so by name or RESTACK;
        # its EXPTIME is already the total integration and no keyword gives the sub count
        is_stack = is_stack or (_num(v, "NAXIS3") or 0) >= 3 or bool(_num(v, "RESTACK"))

    exposure, implausible = 0.0, False
    for key in ("EXPTIME", "EXPOSURE"):
        x = _num(v, key)
        if x is None or x <= 0:
            continue
        if x > MAX_EXPOSURE_S and not (vendor == "dwarf" and is_stack):  # a Dwarf stack's EXPTIME is its total
            implausible = True
            continue
        exposure = x
        break
    if implausible and not exposure:
        # an exposure that cannot be true is unknown, and a light of unknown length is not counted at all:
        # the scan reports it as unreadable
        raise HeaderError("implausible exposure")

    integration = None
    for key in ("LIVETIME", "TOTALEXP", "EXPTOT"):
        integration = _num(v, key)
        if integration is not None and integration > 0:
            break
        integration = None
    if integration is None:
        integration = sub_count * exposure

    dt = _parse_dt(v.get("DATE-OBS"), v.get("TIME-OBS"))
    local = vendor == "origin" or "local" in str(comments.get("DATE-OBS", "")).lower()
    if vendor == "dwarf":
        local = True  # no UTC claim in the header; the date matches the device's own clock in the file name
        if dt is not None:
            dt -= timedelta(seconds=exposure)  # DATE-OBS is the END of the exposure
    start_utc = None if local else dt
    start_local = dt if local else None

    ra_dec = frame_centre(v)
    camera, telescope = _gear(vendor, v)
    iso = _num(v, "ISOSPEED")
    if iso is None:
        iso = _num(v, "ISO")

    return Frame(
        path=path,
        vendor=vendor,
        frame_type=_frame_type(v, name, path),
        is_stack=is_stack,
        sub_count=sub_count,
        exposure_s=exposure,
        integration_s=integration,
        start_utc=start_utc,
        start_local=start_local,
        object_hint=_text(v, "OBJECT"),
        ra_deg=ra_dec[0] if ra_dec else None,
        dec_deg=ra_dec[1] if ra_dec else None,
        fov_deg=field_of_view(v),
        focal_mm=_num(v, "FOCALLEN"),
        camera=camera,
        telescope=telescope,
        filter=_text(v, "FILTER"),
        gain=_num(v, "GAIN"),
        iso=int(iso) if iso is not None else None,
        sensor_c=_num(v, "CCD-TEMP"),
        site=_site(v),
    )
