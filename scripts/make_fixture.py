"""Copy only the header blocks of a FITS file, scrubbing private values.

Usage: make_fixture.py SRC OUT.hdr

Every location card becomes a sentinel (latitude 12.3456, longitude -65.4321,
elevation 0); OBSERVER, SERIALNO, CAMSN and SITENAME become 'scrubbed'; CAMERA
keeps its model but loses any device-id suffix. The cards that could place the
site from the time and the pointing are neutralised too: AIRMASS becomes 1.0,
TIMEZONE '+0000', and altitude/azimuth/hour-angle/sidereal-time cards are blanked.
Cards stay 80 characters.
"""
import re
import sys

BLOCK = 2880
CARD = 80
NUMBERS = {k: "12.3456" for k in ("SITELAT", "LATITUDE", "LAT-OBS", "OBSGEO-B")}
NUMBERS.update({k: "-65.4321" for k in ("SITELONG", "LONGITUD", "LONG-OBS", "OBSGEO-L")})
NUMBERS.update({k: "0" for k in ("SITEELEV", "OBSGEO-H", "ELEVATIO")})
NUMBERS["AIRMASS"] = "1.0"
STRINGS = ("OBSERVER", "SERIALNO", "CAMSN", "SITENAME")
FIXED_STRINGS = {"TIMEZONE": "'+0000'"}
# blanked (a blank card is valid anywhere in a header and is read as nothing)
DROP = ("ALT", "AZ", "ALTITUDE", "AZIMUTH", "OBJCTALT", "OBJCTAZ", "OBJCTHA", "CENTALT", "CENTAZ", "LST", "HA")


def _replace(card: str, value: str) -> str:
    key = card[:8]
    rest = card[10:]
    comment = ""
    if " / " in rest:
        # a '/' outside quotes starts the comment; scrubbed cards are simple enough
        # that the first ' / ' after the value is the separator
        comment = " /" + rest.split(" / ", 1)[1].rstrip()
    new = f"{key}= {value:>20}{comment}"
    return new[:CARD].ljust(CARD)


def scrub(card: str) -> str:
    key = card[:8].strip()
    if key in DROP:
        return " " * CARD
    if card[8:10] != "= ":
        return card
    if key in NUMBERS:
        return _replace(card, NUMBERS[key])
    if key in STRINGS:
        return _replace(card, "'scrubbed'")
    if key in FIXED_STRINGS:
        return _replace(card, FIXED_STRINGS[key])
    if key == "CAMERA":
        m = re.match(r"\s*'([^']*)'", card[10:])
        if m:
            clean = re.sub(r"-[0-9a-fA-F]{6,}$", "", m.group(1))
            return _replace(card, f"'{clean}'")
    return card


def make(src: str, out: str) -> None:
    blocks = []
    with open(src, "rb") as f:
        while True:
            block = f.read(BLOCK)
            if len(block) < BLOCK:
                raise SystemExit(f"{src}: no END card found")
            text = block.decode("ascii", "replace")
            cards = [scrub(text[i:i + CARD]) for i in range(0, BLOCK, CARD)]
            blocks.append("".join(cards).encode("ascii"))
            if any(c[:8].rstrip() == "END" for c in cards):
                break
    with open(out, "wb") as f:
        f.write(b"".join(blocks))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    make(sys.argv[1], sys.argv[2])
