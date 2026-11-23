"""Read FITS, FITS-compressed (.fz) and XISF headers from raw bytes. Standard library only."""
import re
import struct
import xml.etree.ElementTree as ET

BLOCK = 2880
CARD = 80
XISF_MAGIC = b"XISF0100"
FITS_MAGIC = b"SIMPLE"


class HeaderError(ValueError):
    """The bytes are not a readable FITS or XISF header."""


# a binary table's own structure, which must never stand in for the image's (NAXIS1 = 8 bytes per row, ...)
_TABLE_KEY = re.compile(r"^(XTENSION|BITPIX|NAXIS\d*|PCOUNT|GCOUNT|TFIELDS|THEAP|(TTYPE|TFORM|TUNIT|TDIM)\d+)$")
_ZNAXIS = re.compile(r"^ZNAXIS(\d+)$")


def _parse_value(text):
    """Split the value field of a card into (value, comment)."""
    text = text.strip()
    if text.startswith("'"):
        out, i = [], 1
        while i < len(text):
            if text[i] == "'":
                if text[i + 1:i + 2] == "'":
                    out.append("'")
                    i += 2
                    continue
                break
            out.append(text[i])
            i += 1
        rest = text[i + 1:]
        comment = rest.split("/", 1)[1].strip() if "/" in rest else ""
        return "".join(out).rstrip(), comment
    raw, _, comment = text.partition("/")
    return _typed(raw.strip()), comment.strip()


def _typed(token):
    if token == "T":
        return True
    if token == "F":
        return False
    try:
        return int(token)
    except ValueError:
        pass
    try:
        return float(token.replace("D", "E").replace("d", "e"))
    except ValueError:
        return token


def _parse_fits(data, offset):
    """Parse one FITS header starting at offset.

    Returns (values, comments, next_offset), or None when no END card is in data.
    """
    values, comments = {}, {}
    last_key = None
    pos = offset
    while pos + CARD <= len(data):
        card = data[pos:pos + CARD].decode("ascii", "replace")
        pos += CARD
        key = card[:8].strip().upper()
        if key == "END":
            end = offset + -(-(pos - offset) // BLOCK) * BLOCK
            return values, comments, end
        if key == "CONTINUE":
            prev = values.get(last_key)
            rest = card[8:].strip()
            # a continued string is marked by a trailing '&'
            if isinstance(prev, str) and prev.endswith("&") and rest.startswith("'"):
                values[last_key] = prev[:-1] + _parse_value(rest)[0]
            continue
        if not key or key in ("COMMENT", "HISTORY") or card[8:10] != "= ":
            continue
        value, comment = _parse_value(card[10:])
        if key not in values:
            values[key] = value
            if comment:
                comments[key] = comment
            last_key = key
        else:
            last_key = None
    return None


def _merge_extension(values, comments, ext_values, ext_comments):
    """The primary header with the first extension's keys over it.

    An IMAGE extension is the image, so all of its keys apply. A binary table (an fpacked .fz image is one) never
    lends its own structure keys; when it holds a compressed image (ZIMAGE = T), ZBITPIX/ZNAXIS/ZNAXISn are the
    image's BITPIX/NAXIS/NAXISn.
    """
    if str(ext_values.get("XTENSION", "")).strip().upper() == "IMAGE":
        return {**values, **ext_values}, {**comments, **ext_comments}
    out, out_c = dict(values), dict(comments)
    for k, x in ext_values.items():
        if _TABLE_KEY.match(k):
            continue
        out[k] = x
        if k in ext_comments:
            out_c[k] = ext_comments[k]
    if ext_values.get("ZIMAGE") is True:
        for k, x in ext_values.items():
            m = _ZNAXIS.match(k)
            if m:
                out[f"NAXIS{m.group(1)}"] = x
        for z, k in (("ZBITPIX", "BITPIX"), ("ZNAXIS", "NAXIS")):
            if z in ext_values:
                out[k] = ext_values[z]
    return out, out_c


def _fits_headers_complete(data):
    """Walk the primary header (and the first extension's, for .fz). None means more bytes are needed."""
    first = _parse_fits(data, 0)
    if first is None:
        return None
    values, comments, end = first
    if values.get("NAXIS") == 0 and values.get("EXTEND") is True:
        second = _parse_fits(data, end)
        if second is None:
            return None
        ext_values, ext_comments, end = second
        values, comments = _merge_extension(values, comments, ext_values, ext_comments)
    return values, comments, end


def _next_size(have):
    return (have // BLOCK + 1) * BLOCK


def header_bytes_needed(prefix: bytes) -> int:
    """0 when every needed header in prefix is complete, else the total bytes to read next."""
    if not prefix:
        return BLOCK
    if prefix.startswith(XISF_MAGIC):
        if len(prefix) < 16:
            return 16
        total = 16 + struct.unpack_from("<I", prefix, 8)[0]
        return 0 if len(prefix) >= total else total
    if prefix.startswith(FITS_MAGIC):
        if _fits_headers_complete(prefix) is not None:
            return 0
        return _next_size(len(prefix))
    if len(prefix) < len(XISF_MAGIC) and (XISF_MAGIC.startswith(prefix) or FITS_MAGIC.startswith(prefix)):
        return BLOCK
    raise HeaderError("not a FITS or XISF header")


def read_header(data: bytes):
    """Return (values, comments) with upper-case keys."""
    if data.startswith(XISF_MAGIC):
        return _read_xisf(data)
    # anything else is tried as FITS cards: it must still yield an END card
    result = _fits_headers_complete(data)
    if result is None:
        raise HeaderError("not a FITS or XISF header (no END card in the bytes given)")
    return result[0], result[1]


def _read_xisf(data):
    if len(data) < 16:
        raise HeaderError("truncated XISF header")
    length = struct.unpack_from("<I", data, 8)[0]
    if len(data) < 16 + length:
        raise HeaderError("truncated XISF header")
    try:
        root = ET.fromstring(data[16:16 + length])
    except ET.ParseError as exc:
        raise HeaderError(f"bad XISF XML: {exc}") from exc
    values, comments = {}, {}
    for el in root.iter():
        if el.tag.rsplit("}", 1)[-1] != "FITSKeyword":
            continue
        key = el.get("name", "").strip().upper()
        if not key or key in ("COMMENT", "HISTORY") or key in values:
            continue
        values[key], _ = _parse_value(el.get("value", ""))
        if el.get("comment"):
            comments[key] = el.get("comment")
    return values, comments
