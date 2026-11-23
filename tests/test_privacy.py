import json

from helpers import cw, frames_from_fixtures
from skywrapped.stats import to_summary


def test_summary_private(fixture):
    fs = frames_from_fixtures(path_prefix="SECRETFOLDER/", hint="my secret field")  # fixture site = 12.3456, -65.4321
    assert any(f.site for f in fs)
    text = json.dumps(to_summary(cw(fs)))
    for s in ["12.3456", "65.4321", "12.35", "65.43", "SECRETFOLDER", "secret field"]:
        assert s not in text


def test_uncatalogued_hint_never_names_a_target():
    from helpers import fr
    hints = ["MYSECRETFIELD", "Field7", "my secret field", "Smith Backyard 3"]
    fs = [fr(hint=h) for h in hints]
    text = json.dumps(to_summary(cw(fs))).lower()
    for s in ["mysecretfield", "field7", "secret", "smith"]:
        assert s not in text


def test_device_ids_and_free_text_never_reach_output():
    """C2: TELESCOP/INSTRUME pass one sanitiser; device ids, long digit runs and long free text never print raw."""
    from datetime import datetime

    from skywrapped._fitsnorm import to_frame
    from skywrapped.cards import render_cards
    raw = {
        "seestar": {"CREATOR": "ZWO Seestar S50", "INSTRUME": "Seestar S50", "TELESCOP": "S50_4a8b9c2d"},
        "dwarf": {"ORIGIN": "DWARFLAB", "INSTRUME": "DWARFIII", "TELESCOP": "DWARFIII"},
        "generic": {"INSTRUME": "ZWO ASI2600MC Pro 20231234567", "TELESCOP": "Ed Smith's Backyard Esprit 12345678"},
        "hexcam": {"INSTRUME": "QHY268M-0a1b2c3d4e", "TELESCOP": "MyScope_a1b2c3d4"},
    }
    frames = []
    for k, (name, cards) in enumerate(raw.items()):
        for i in range(3):
            v = {"IMAGETYP": "Light", "EXPTIME": 300.0, "FOCALLEN": 400.0 + 200 * k,
                 "DATE-OBS": datetime(2026, 3, 10 + k, 3, i * 6).isoformat(), **cards}
            frames.append(to_frame(v, {}, f"{name}/Light_{i}.fit"))
    w = cw(frames)
    labels = sorted(s.label for s in w.setups)
    assert labels == ["Dwarf 3", "Ed Smith's Backyard Esprit · ASI2600MC Pro", "MyScope · QHY268M", "Seestar S50"]
    text = json.dumps(to_summary(w)) + "".join(c.svg for t in ("observatory", "nebula") for c in render_cards(w, t))
    for s in ["4a8b9c2d", "S50_", "20231234567", "12345678", "Ed Smith's Backyard Esprit 12345678", "0a1b2c3d4e",
              "a1b2c3d4", "DWARFIII"]:
        assert s not in text, s
