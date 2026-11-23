"""The web page's Python side (web_api): header slices in, the command line's numbers out."""
import json
import struct
from datetime import date

import pytest
from helpers import put

from skywrapped import TESTED_VENDORS, web_api
from skywrapped.cli import main
from skywrapped.scan import FIRST_READ, scan_paths

END = b"END" + b" " * 77
TODAY = date.today().isoformat()  # the CLI uses date.today() too


@pytest.fixture(autouse=True)
def fresh():
    web_api.reset()
    yield
    web_api.reset()


def _end_of_header(data: bytes) -> int:
    """The byte just past the last END card (the .fz fixtures have two headers)."""
    ends = [i for i in range(0, len(data), 80) if data[i:i + 80] == END]
    return ends[-1] + 80


def _files(folder, root="lights") -> dict[str, bytes]:
    """Relative path (as the browser gives it) -> file bytes, for every file in a flat folder."""
    return {f"{root}/{p.name}": p.read_bytes() for p in sorted(folder.iterdir())}


def _feed(files: dict[str, bytes], first: dict[str, bytes] | None = None) -> int:
    """Drive parse_batch the way worker.js does: one slice per file, then re-slice whatever is asked for.

    ``first`` overrides the first slice per path (default: the first FIRST_READ bytes). Returns the rounds used.
    """
    first = first or {p: d[:FIRST_READ] for p, d in files.items()}
    pending = web_api.parse_batch(list(first.items()))
    rounds = 1
    while pending:
        rounds += 1
        assert rounds <= 10
        pending = web_api.parse_batch([(p, files[p][:need]) for p, need in pending])
    return rounds


def _cli_summary(tmp_path, folder, *args) -> dict:
    out = tmp_path / "cli_out"
    assert main([str(folder), "--json-only", "--out", str(out), *args]) == 0
    return json.loads((out / "summary.json").read_text(encoding="utf-8"))


def test_short_slices_then_full_slices_match_the_cli(tmp_path, fixture_dir):
    cli = _cli_summary(tmp_path, fixture_dir, "--year", "2026", "--tz", "-5")
    files = _files(fixture_dir)
    short = {p: d[:_end_of_header(d) - 100] for p, d in files.items()}

    pending = web_api.parse_batch(list(short.items()))
    assert sorted(p for p, _ in pending) == sorted(files)          # every short slice asks for more
    for p, need in pending:
        assert len(short[p]) < need <= len(files[p])
    rounds = 1
    while pending:
        rounds += 1
        assert rounds <= 4
        pending = web_api.parse_batch([(p, files[p][:need]) for p, need in pending])

    out = json.loads(web_api.finish(2026, -5.0, TODAY, "observatory"))
    assert out["summary"] == cli
    assert set(out) == {"summary", "cards"}


def test_first_read_completes_every_fixture_in_one_round(fixture_dir):
    assert _feed(_files(fixture_dir)) == 1


def test_all_years_matches_the_cli(tmp_path, fixture_dir):
    cli = _cli_summary(tmp_path, fixture_dir, "--all", "--tz", "0")
    _feed(_files(fixture_dir))
    out = json.loads(web_api.finish(None, 0.0, TODAY, "observatory"))
    assert out["summary"] == cli and out["summary"]["year"] is None


def test_cards_are_the_rendered_set_with_file_stems(fixture_dir):
    _feed(_files(fixture_dir))
    cards = json.loads(web_api.finish(2026, -5.0, TODAY, "observatory"))["cards"]
    assert cards[-1]["name"] == "poster" and cards[-1]["stem"] == "poster"
    assert (cards[-1]["width"], cards[-1]["height"]) == (1600, 900)
    portrait = cards[:-1]
    assert [c["stem"] for c in portrait] == [f"card-{i}" for i in range(1, len(portrait) + 1)]
    assert all((c["width"], c["height"]) == (1080, 1350) for c in portrait)
    assert all(c["svg"].startswith("<svg") and "@font-face" in c["svg"] for c in cards)


def test_theme_switch_changes_only_the_svgs(fixture_dir):
    _feed(_files(fixture_dir))
    obs = json.loads(web_api.finish(2026, -5.0, TODAY, "observatory"))
    neb = json.loads(web_api.rerender("nebula"))
    assert neb["summary"] == obs["summary"]
    shape = [(c["name"], c["stem"], c["width"], c["height"]) for c in obs["cards"]]
    assert shape == [(c["name"], c["stem"], c["width"], c["height"]) for c in neb["cards"]]
    assert all(a["svg"] != b["svg"] for a, b in zip(obs["cards"], neb["cards"]))
    assert json.loads(web_api.rerender("observatory")) == obs


def test_finish_again_with_another_year_needs_no_new_slices(fixture_dir):
    _feed(_files(fixture_dir))
    a = json.loads(web_api.finish(2026, -5.0, TODAY, "observatory"))["summary"]
    b = json.loads(web_api.finish(None, -5.0, TODAY, "nebula"))["summary"]
    old = json.loads(web_api.finish(2020, -5.0, TODAY, "nebula"))["summary"]  # the Ekos fixture is a 2020 file
    assert (a["year"], b["year"]) == (2026, None)
    assert a["frames"] + old["frames"] == b["frames"] and a["frames"] > 0
    assert a["hours"] + old["hours"] == pytest.approx(b["hours"])


def test_unreadable_files_are_counted_not_asked_for_again(fixture, fixture_dir):
    files = _files(fixture_dir)
    files.update({
        "lights/junk.fits": b"GIF89a" + b"\0" * 5000,                                   # not a header at all
        "lights/empty.fit": b"",                                                         # nothing to read
        "lights/cut.fit": fixture("asiair_2600air")[:4000],                             # ends before its END card
        "lights/huge.xisf": b"XISF0100" + struct.pack("<I", 0xFFFFFFF0) + b"\0" * 4,    # header over the 1 MiB cap
    })
    pending = web_api.parse_batch([(p, d[:FIRST_READ]) for p, d in files.items()])
    assert sorted(p for p, _ in pending) == ["lights/cut.fit", "lights/empty.fit"]
    assert web_api.parse_batch([(p, files[p][:need]) for p, need in pending]) == []
    summary = json.loads(web_api.finish(2026, -5.0, TODAY, "observatory"))["summary"]
    assert summary["skipped"]["unreadable"] == 4


def test_select_follows_the_scan_rules(tmp_path, fixture):
    names = ["a.fit", "._a.fit", ".hidden.fits", ".git/b.fit", "c.txt", "previews/c.jpg", "d.FITS", "sub/e.xisf",
             "sub/._e.xisf", "f.fts", "g.fz"]
    for n in names:
        put(tmp_path / "lights" / n, fixture("asiair_2600air"))
    _, cli_skipped = scan_paths([str(tmp_path / "lights")], [])

    paths = [f"lights/{n}" for n in names] + [".lights/h.fit"]  # a hidden folder picked as the root still counts
    keep = web_api.select(paths)
    assert [paths[i] for i in keep] == ["lights/a.fit", "lights/d.FITS", "lights/sub/e.xisf", "lights/f.fts",
                                        "lights/g.fz", ".lights/h.fit"]
    _feed({paths[i]: fixture("asiair_2600air") for i in keep})
    summary = json.loads(web_api.finish(None, 0.0, TODAY, "observatory"))["summary"]
    assert summary["skipped"]["metadata_file"] == cli_skipped["metadata_file"] == 2


def test_nothing_private_leaves(fixture_dir):
    files = {f"SECRETFOLDER/my secret field/{p.rsplit('/', 1)[1]}": d for p, d in _files(fixture_dir).items()}
    _feed(files)
    text = web_api.finish(None, 0.0, TODAY, "observatory") + web_api.rerender("nebula")
    for s in ["SECRETFOLDER", "secret field", "12.3456", "65.4321", "Light_"]:
        assert s not in text


def test_no_lights_reports_counts_only(fixture):
    _feed({"SECRET/Light_dark.fit": fixture("asiair_dark"), "SECRET/junk.fit": b"\0" * 100})
    out = json.loads(web_api.finish(2026, 0.0, TODAY, "observatory"))
    assert out["error"] == "no_lights" and out["headers"] == 1 and out["skipped"]["unreadable"] == 1
    assert out["years"] == [] and "SECRET" not in json.dumps(out)
    with pytest.raises(ValueError):
        web_api.rerender("nebula")


def test_no_lights_in_that_year_names_the_years_found(fixture_dir):
    _feed(_files(fixture_dir))
    out = json.loads(web_api.finish(1999, 0.0, TODAY, "observatory"))
    assert out["error"] == "no_lights" and out["years"] == [2020, 2026]


def test_reset_forgets_everything(fixture_dir):
    _feed(_files(fixture_dir))
    web_api.reset()
    assert json.loads(web_api.finish(None, 0.0, TODAY, "observatory"))["headers"] == 0


def test_bytes_like_slices_are_accepted(fixture):
    data = fixture("asiair_2600air")
    assert web_api.parse_batch([("a/Light_1.fit", memoryview(data)), ("a/Light_2.fit", bytearray(data))]) == []


def test_unknown_theme_is_refused(fixture_dir):
    _feed(_files(fixture_dir))
    with pytest.raises(ValueError):
        web_api.finish(2026, 0.0, TODAY, "sepia")


def test_tested_vendors():
    assert TESTED_VENDORS[:2] == ("ASIAIR", "Celestron Origin")


def test_only_no_lights_is_reported_as_no_lights(fixture_dir, monkeypatch):
    """I3: any other error in finish() surfaces (the worker posts it as an internal error), never as "no lights"."""
    _feed(_files(fixture_dir))

    def broken(*a, **k):
        raise ValueError("a bug")
    monkeypatch.setattr(web_api, "compute_wrapped", broken)
    with pytest.raises(ValueError, match="a bug"):
        web_api.finish(2026, 0.0, TODAY, "observatory")


def test_a_need_that_asks_for_no_more_bytes_is_unreadable(fixture, monkeypatch):
    """The worker re-slices while parse_batch asks for more: a need <= the bytes given would make it spin."""
    data = fixture("asiair_2600air")[:2880]
    monkeypatch.setattr(web_api, "next_read", lambda d: len(d))
    assert web_api.parse_batch([("a/Light_1.fit", data)]) == []
    monkeypatch.setattr(web_api, "next_read", lambda d: len(d) - 80)
    assert web_api.parse_batch([("a/Light_2.fit", data)]) == []
    assert web_api._skipped["unreadable"] == 2
