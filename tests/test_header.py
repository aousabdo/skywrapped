import struct

import pytest

from skywrapped._fitsnorm.header import HeaderError, header_bytes_needed, read_header

BLOCK = 2880


def block(cards, end=True):
    cards = list(cards) + (["END"] if end and "END" not in cards else [])
    raw = "".join(c.ljust(80) for c in cards).encode("ascii")
    return raw + b" " * (-len(raw) % BLOCK)


def block_without_end():
    return block(["SIMPLE  =                    T", "NAXIS   =                    2"], end=False)


def fz_like():
    primary = block(["SIMPLE  =                    T", "NAXIS   =                    0",
                     "EXTEND  =                    T"])
    ext = block(["XTENSION= 'BINTABLE'", "ZIMAGE  =                    T", "EXPTIME =                  60."])
    return primary + ext


def xisf_like(*keywords):
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<xisf version="1.0" xmlns="http://www.pixinsight.com/xisf"><Image>'
           + "".join(keywords) + "</Image></xisf>").encode("utf-8")
    return b"XISF0100" + struct.pack("<II", len(xml), 0) + xml


def test_reads_asiair_header(fixture):
    v, c = read_header(fixture("asiair_2600air"))
    assert v["EXPTIME"] == 300.0 and v["GAIN"] == 100
    assert v["INSTRUME"] == "ZWO ASI2600MC Air"
    assert v["DATE-OBS"] == "2026-09-06T05:11:25.157930"
    assert v["SITELAT"] == 12.3456 and "exposure start" in c["DATE-OBS"].lower()


def test_quotes_continue_and_types():
    v, _ = read_header(block(["OBJECT  = 'O''Brien'", "LONG    = 'abc&'", "CONTINUE  'def'",
                              "FLAG    = T", "X       = 1.5D2", "N       = 42", "END"]))
    assert v["OBJECT"] == "O'Brien" and v["LONG"] == "abcdef"
    assert v["FLAG"] is True and v["X"] == 150.0 and v["N"] == 42


def test_bytes_needed(fixture):
    assert header_bytes_needed(b"") == 2880
    assert header_bytes_needed(block_without_end()) == 5760
    assert header_bytes_needed(fixture("asiair_2600air")) == 0


def test_fz_merges_first_extension():
    data = fz_like()
    assert header_bytes_needed(data[:2880]) > 2880
    assert read_header(data)[0]["EXPTIME"] == 60.0


def test_xisf_fits_keywords():
    data = xisf_like('<FITSKeyword name="EXPTIME" value="120." comment="s"/>')
    assert header_bytes_needed(data[:16]) == len(data)
    assert read_header(data)[0]["EXPTIME"] == 120.0


def test_not_a_header():
    for junk in (b"", b"GIF89a" + b"\0" * 3000, b"SIMPLE  = T" + b" " * 100):
        with pytest.raises(HeaderError):
            read_header(junk)


def test_first_occurrence_wins_and_comments_ignored():
    v, c = read_header(block(["A       = 1 / first", "COMMENT hello", "HISTORY x", "A       = 2",
                              "B       = 'x   ' / note", "        = 5", "END"]))
    assert v["A"] == 1 and c["A"] == "first"
    assert v["B"] == "x" and "COMMENT" not in v and "HISTORY" not in v


def test_scrubbed_fixtures_carry_sentinels(fixture):
    for name in ("asiair_2600air", "asiair_4400", "asiair_6200mm", "asiair_duo_awstack"):
        v, _ = read_header(fixture(name))
        assert v["SITELAT"] == 12.3456 and v["SITELONG"] == -65.4321


def test_every_fixture_parses(fixture):
    for name in ("asiair_2600air", "asiair_duo_awstack", "asiair_4400", "asiair_6200mm",
                 "origin_678c", "origin_178", "asiair_dark", "asiair_flat"):
        data = fixture(name)
        assert header_bytes_needed(data) == 0
        assert "EXPTIME" in read_header(data)[0] or "EXPOSURE" in read_header(data)[0]


def fpacked(fixture_bytes: bytes) -> bytes:
    """An fpack-style .fz header for an uncompressed fixture: an empty primary, then a BINTABLE holding the
    compressed image (ZIMAGE = T) with the image's own keywords and its size in ZBITPIX/ZNAXIS/ZNAXISn."""
    text = fixture_bytes.decode("ascii")
    cards = [text[i:i + 80] for i in range(0, len(text), 80)]
    v, _ = read_header(fixture_bytes)
    keep = [c for c in cards if c[:8].strip() not in ("SIMPLE", "BITPIX", "NAXIS", "NAXIS1", "NAXIS2", "NAXIS3",
                                                      "EXTEND", "END", "")]
    primary = block(["SIMPLE  =                    T", "BITPIX  =                   16",
                     "NAXIS   =                    0", "EXTEND  =                    T"])
    table = ["XTENSION= 'BINTABLE'", "BITPIX  =                    8", "NAXIS   =                    2",
             "NAXIS1  =                    8", f"NAXIS2  = {v['NAXIS2']:>20}", "PCOUNT  =             12345678",
             "GCOUNT  =                    1", "TFIELDS =                    1", "TTYPE1  = 'COMPRESSED_DATA'",
             "TFORM1  = '1PB(9999)'", "ZIMAGE  =                    T", "ZTILE1  =                 6248",
             "ZTILE2  =                    1", "ZCMPTYPE= 'RICE_1  '", f"ZBITPIX = {v['BITPIX']:>20}",
             "ZNAXIS  =                    2", f"ZNAXIS1 = {v['NAXIS1']:>20}", f"ZNAXIS2 = {v['NAXIS2']:>20}"]
    return primary + block(table + keep)


def test_fpacked_header_keeps_the_image_size(fixture):
    """I2: the table's NAXIS1 (8 bytes per row) and BITPIX never replace the image's; centre and FOV match."""
    from skywrapped._fitsnorm import to_frame
    plain = fixture("asiair_2600air")
    fz = fpacked(plain)
    assert header_bytes_needed(fz[:2880]) > 2880 and header_bytes_needed(fz) == 0
    v, _ = read_header(fz)
    p, _ = read_header(plain)
    assert (v["NAXIS"], v["NAXIS1"], v["NAXIS2"], v["BITPIX"]) == (p["NAXIS"], p["NAXIS1"], p["NAXIS2"], p["BITPIX"])
    for k in ("XTENSION", "PCOUNT", "GCOUNT", "TFIELDS", "TTYPE1", "TFORM1"):
        assert k not in v, k
    a, b = to_frame(v, {}, "Light_x.fit.fz"), to_frame(p, {}, "Light_x.fit")
    assert a.ra_deg == pytest.approx(b.ra_deg, abs=1e-9) and a.dec_deg == pytest.approx(b.dec_deg, abs=1e-9)
    assert a.fov_deg == pytest.approx(b.fov_deg, rel=1e-9) and a.exposure_s == b.exposure_s == 300.0


def test_image_extension_keys_apply():
    primary = block(["SIMPLE  =                    T", "NAXIS   =                    0", "EXTEND  =                    T"])
    ext = block(["XTENSION= 'IMAGE   '", "BITPIX  =                   16", "NAXIS   =                    2",
                 "NAXIS1  =                 1000", "NAXIS2  =                  800", "EXPTIME =                  30."])
    v, _ = read_header(primary + ext)
    assert (v["NAXIS"], v["NAXIS1"], v["NAXIS2"], v["EXPTIME"]) == (2, 1000, 800, 30.0)
