import importlib.util
import struct
import zlib

import pytest

from helpers import sample
from skywrapped.cards import render_cards

needs_resvg = pytest.mark.skipif(importlib.util.find_spec("resvg_py") is None, reason="needs resvg-py")
from skywrapped.render_png import svg_to_png


def decode(png: bytes):
    """Minimal PNG decoder (8-bit, non-interlaced, RGB/RGBA): returns (w, h, channels, rows of bytes)."""
    w, h, depth, ctype = struct.unpack(">IIBB", png[16:26])
    assert depth == 8 and ctype in (2, 6)
    ch = 3 if ctype == 2 else 4
    idat, pos = b"", 8
    while pos < len(png):
        n, kind = struct.unpack(">I4s", png[pos:pos + 8])
        if kind == b"IDAT":
            idat += png[pos + 8:pos + 8 + n]
        pos += 12 + n
    raw, stride, rows, prev = zlib.decompress(idat), w * ch, [], bytearray(w * ch)
    for y in range(h):
        f, line = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - ch] if i >= ch else 0
            b, c = prev[i], (prev[i - ch] if i >= ch else 0)
            if f == 1:
                line[i] = (line[i] + a) & 255
            elif f == 2:
                line[i] = (line[i] + b) & 255
            elif f == 3:
                line[i] = (line[i] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append(line)
        prev = line
    return w, h, ch, rows


def bright_fraction(img, box, thresh=140):
    w, h, ch, rows = img
    x0, y0, x1, y1 = box
    n = hit = 0
    for y in range(y0, y1):
        for x in range(x0, x1):
            px = rows[y][x * ch:x * ch + 3]
            n += 1
            hit += sum(px) / 3 > thresh
    return hit / n


@needs_resvg
def test_png_dimensions():
    png = svg_to_png(render_cards(sample())[0].svg, 1080)
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(">II", png[16:24]) == (1080, 1350)


@needs_resvg
def test_png_text_drawn():
    img = decode(svg_to_png(render_cards(sample())[0].svg, 1080))
    assert bright_fraction(img, box=(76, 300, 700, 580)) > 0.05


@needs_resvg
def test_poster_dimensions():
    cards = render_cards(sample(), theme="nebula")
    poster = cards[-1]
    assert poster.name == "poster"
    assert struct.unpack(">II", svg_to_png(poster.svg, poster.width)[16:24]) == (1600, 900)


@needs_resvg
def test_png_ignores_system_fonts(monkeypatch):
    import resvg_py
    seen = {}
    real = resvg_py.svg_to_bytes

    def spy(**kw):
        seen.update(kw)
        return real(**kw)
    monkeypatch.setattr(resvg_py, "svg_to_bytes", spy)
    svg_to_png(render_cards(sample())[0].svg, 1080)
    assert seen["skip_system_fonts"] is True and len(seen["font_files"]) >= 2


@needs_resvg
def test_control_characters_never_break_the_svg_or_png():
    """I4: a label with characters XML cannot hold still renders, without them."""
    import xml.etree.ElementTree as ET
    w = sample()
    w.setups[0].label = "Rig\x01 one\x1f\ufffe"
    w.top_targets[0].label = "M\x0b 42\ud800"
    for theme in ("observatory", "nebula"):
        for c in render_cards(w, theme):
            ET.fromstring(c.svg)
            for bad in ("\x01", "\x1f", "\ufffe", "\x0b", "\ud800"):
                assert bad not in c.svg
            assert svg_to_png(c.svg, c.width)[:8] == b"\x89PNG\r\n\x1a\n"
    gear = next(c.svg for c in render_cards(w) if c.name == "gear")
    assert "Rig one" in gear


def test_esc_keeps_tab_newline_return():
    from skywrapped.cards.svg import esc
    assert esc("a\tb\nc\rd\x00e<&>\"") == "a\tb\nc\rde&lt;&amp;&gt;&quot;"
