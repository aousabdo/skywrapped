"""The Siril script (SkyWrapped/SkyWrapped.py): everything that runs without Siril and without Qt.

The script keeps sirilpy and PyQt6 out of its import time, so its helpers (argument parsing, the output-folder rules,
the install check, the typed command, the Qt-compatibility rewrite of the SVGs) can be tested here. The window and
the Qt drawing are checked inside Siril's own Python (siril-cli, offscreen), not in this suite.
"""
import importlib.util
import json
import sys
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

import pytest

import skywrapped
from skywrapped import cli
from skywrapped.cards import render_cards
from skywrapped.scan import scan_paths
from skywrapped.stats import compute_wrapped

SCRIPT = Path(__file__).resolve().parents[1] / "SkyWrapped" / "SkyWrapped.py"
pytestmark = pytest.mark.skipif(not SCRIPT.exists(), reason="SkyWrapped/ is not part of this checkout (sdist)")

needs_resvg = pytest.mark.skipif(importlib.util.find_spec("resvg_py") is None, reason="needs resvg-py")


@pytest.fixture(scope="module")
def sws():
    spec = importlib.util.spec_from_file_location("skywrapped_siril_script", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.load_skywrapped(install=False)
    return mod


def fake_png(svg: str, width: int) -> bytes:
    return b"\x89PNG fake " + str(width).encode()


def test_imports_without_siril_or_qt():
    before = {name for name in ("sirilpy", "PyQt6") if name in sys.modules}
    spec = importlib.util.spec_from_file_location("skywrapped_siril_script_2", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)                     # would raise on a machine without them if it imported them
    assert {name for name in ("sirilpy", "PyQt6") if name in sys.modules} == before
    assert mod.SKYWRAPPED_MIN == "0.1.0"


def test_it_uses_the_cli_helpers_it_expects(sws):
    for name in ("MARKER", "_prepare_out", "_clear_own", "_final_line", "_no_lights", "PROGRESS_EVERY"):
        assert hasattr(cli, name), name
    assert sws.local_offset_hours() == cli._local_offset_h()
    assert sws.version_ok(skywrapped.__version__)


@pytest.mark.parametrize("have,ok", [("0.1.0", True), ("0.1.0.dev0", True), ("0.1.1", True), ("0.10.0", True),
                                     ("1.0", True), ("0.0.9", False), ("", False), ("junk", False)])
def test_version_check(sws, have, ok):
    assert sws.version_ok(have) is ok


def test_arguments_and_plan(sws):
    ns = sws.build_parser().parse_args(["/lights"])
    plan = sws.plan_from_args(ns, today=date(2026, 11, 23))
    assert (plan.year, plan.tz, plan.excludes) == (2026, sws.local_offset_hours(), [])
    ns = sws.build_parser().parse_args(["/a", "/b", "--all", "--tz", "-5", "--theme", "nebula", "--json-only",
                                        "--exclude", "*/x/*", "--default-excludes"])
    plan = sws.plan_from_args(ns)
    assert plan.year is None and plan.tz == -5.0 and ns.theme == "nebula" and ns.json_only and ns.paths == ["/a", "/b"]
    assert plan.excludes == list(sws.DEFAULT_EXCLUDES) + ["*/x/*"]
    assert sws.plan_from_args(sws.build_parser().parse_args(["/a", "--year", "2024"])).year == 2024
    with pytest.raises(SystemExit):
        sws.build_parser().parse_args(["/a", "--year", "2024", "--all"])
    with pytest.raises(SystemExit):
        sws.build_parser().parse_args(["/a", "--theme", "neon"])


def test_parse_excludes_and_titles(sws):
    assert sws.parse_excludes("  */a/*\n\n*/b/*  \n") == ["*/a/*", "*/b/*"]
    assert [sws.card_title(n) for n in ("cover", "poster")] == ["Cover", "Poster"]


def test_output_folder_names_and_rules(sws, tmp_path):
    assert sws.output_name(None) == "skywrapped-all" and sws.output_name(2026) == "skywrapped-2026"
    assert sws.free_output_dir(2026, tmp_path) == tmp_path / "skywrapped-2026"          # nothing there yet
    (tmp_path / "skywrapped-2026").mkdir()                                              # an empty folder is fine
    assert sws.free_output_dir(2026, tmp_path) == tmp_path / "skywrapped-2026"
    (tmp_path / "skywrapped-2026" / "mine.txt").write_text("not ours")                  # other files, no marker: refused
    assert not sws.output_ok(tmp_path / "skywrapped-2026")
    assert sws.free_output_dir(2026, tmp_path) == tmp_path / "skywrapped-2026-2"
    (tmp_path / "skywrapped-all").mkdir()
    (tmp_path / "skywrapped-all" / cli.MARKER).write_text("ours")                       # marked: reused
    (tmp_path / "skywrapped-all" / "card-1.png").write_bytes(b"old")
    assert sws.free_output_dir(None, tmp_path) == tmp_path / "skywrapped-all"
    assert sws.documents_dir().is_dir()


def test_default_excludes_skip_rejected_and_previews(sws, fixture_dir, tmp_path):
    src = next(fixture_dir.glob("*.fit"))
    for sub in ("keep", "rejected", "_rejected", "previews", "deep/previews"):
        d = tmp_path / "lights" / sub
        d.mkdir(parents=True)
        (d / "Light_1.fit").write_bytes(src.read_bytes())
    frames, skipped = sws.scan_frames([str(tmp_path / "lights")], sws.DEFAULT_EXCLUDES)
    assert len(frames) == 1 and skipped["excluded"] == 4
    frames, skipped = sws.scan_frames([str(tmp_path / "lights")], [])
    assert len(frames) == 5 and skipped["excluded"] == 0


def test_scan_can_be_cancelled(sws, fixture_dir):
    seen = []
    with pytest.raises(sws.Cancelled):
        sws.scan_frames([str(fixture_dir)], [], on_progress=lambda d, t: seen.append(d), cancelled=lambda: bool(seen))
    assert seen == [1]


def test_typed_command_json_only_matches_the_cli(sws, fixture_dir, tmp_path):
    a, b = tmp_path / "script", tmp_path / "cli"
    lines = []
    assert sws.run_headless([str(fixture_dir), "--year", "2026", "--tz", "-5", "--json-only", "--out", str(a)],
                            say=lambda m, level="info": lines.append((level, m))) == 0
    assert cli.main([str(fixture_dir), "--year", "2026", "--tz", "-5", "--json-only", "--out", str(b)]) == 0
    assert (a / "summary.json").read_bytes() == (b / "summary.json").read_bytes()
    assert (a / cli.MARKER).exists() and sorted(p.name for p in a.iterdir()) == [cli.MARKER, "summary.json"]
    assert lines[-2][0] == "good" and " h · " in lines[-2][1]
    assert str(fixture_dir) not in json.dumps(lines)                                    # counts and years only


def test_typed_command_writes_the_clis_files(sws, fixture_dir, tmp_path):
    out = tmp_path / "all"
    assert sws.run_headless([str(fixture_dir), "--all", "--tz", "0", "--theme", "nebula", "--out", str(out)],
                            png_renderer=fake_png) == 0
    names = sorted(p.name for p in out.iterdir())
    assert cli.MARKER in names and "summary.json" in names and "index.html" in names
    n = len(list(out.glob("card-*.svg")))
    assert n >= 5 and len(list(out.glob("card-*.png"))) == n and (out / "poster.png").read_bytes().startswith(b"\x89PNG")
    frames, skipped = scan_paths([str(fixture_dir)], [])
    wrapped = compute_wrapped(frames, year=None, default_offset_h=0.0, today=date.today(), skipped=skipped)
    expected = {c.name: c.svg for c in render_cards(wrapped, theme="nebula")}
    assert (out / "poster.svg").read_text(encoding="utf-8") == expected["poster"]
    html = (out / "index.html").read_text(encoding="utf-8")
    assert 'src="card-1.png"' in html and "http://" not in html and str(out) not in html


@needs_resvg
def test_typed_command_cards_match_the_cli_svgs(sws, fixture_dir, tmp_path):
    a, b = tmp_path / "script", tmp_path / "cli"
    assert sws.run_headless([str(fixture_dir), "--year", "2026", "--tz", "-5", "--out", str(a)],
                            png_renderer=fake_png) == 0
    assert cli.main([str(fixture_dir), "--year", "2026", "--tz", "-5", "--out", str(b)]) == 0
    assert sorted(p.name for p in a.iterdir()) == sorted(p.name for p in b.iterdir())
    for p in b.glob("*.svg"):
        assert (a / p.name).read_bytes() == p.read_bytes(), p.name
    assert (a / "summary.json").read_bytes() == (b / "summary.json").read_bytes()


def test_typed_command_refusals(sws, fixture_dir, tmp_path):
    msgs = []
    say = lambda m, level="info": msgs.append((level, m))                              # noqa: E731
    assert sws.run_headless([], say=say) == sws.EXIT_NOTHING and "Give the folder" in msgs[-1][1]
    assert sws.run_headless([str(tmp_path / "missing"), "--all"], say=say) == sws.EXIT_NOTHING
    assert "does not exist" in msgs[-1][1]
    empty = tmp_path / "empty"
    empty.mkdir()
    assert sws.run_headless([str(empty), "--all", "--json-only", "--out", str(tmp_path / "o")], say=say) == 2
    assert "No light frames found" in msgs[-1][1]
    assert sws.run_headless([str(fixture_dir), "--year", "1999", "--json-only", "--out", str(tmp_path / "o")],
                            say=say) == 2
    assert "No light frames from 1999. Found lights from:" in msgs[-1][1] and msgs[-1][0] == "error"
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    (foreign / "keep.txt").write_text("mine")
    assert sws.run_headless([str(fixture_dir), "--all", "--json-only", "--out", str(foreign)], say=say) == 4
    assert [p.name for p in foreign.iterdir()] == ["keep.txt"]                           # never touched


def test_default_output_goes_to_documents_not_the_lights(sws, fixture_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(sws, "documents_dir", lambda: tmp_path / "docs")
    (tmp_path / "docs").mkdir()
    monkeypatch.chdir(fixture_dir)
    assert sws.run_headless([str(fixture_dir), "--all", "--tz", "0", "--json-only"], say=lambda *a, **k: None) == 0
    assert (tmp_path / "docs" / "skywrapped-all" / "summary.json").exists()
    assert sorted(p.name for p in fixture_dir.iterdir() if not p.name.startswith("Light_")) == []


def test_png_failure_leaves_what_the_cli_leaves(sws, fixture_dir, tmp_path, monkeypatch):
    """A PNG that cannot be drawn: the same files are left behind as by the command line (exit 3 on both)."""
    from skywrapped import render_png

    def cli_broken(svg, width=None):
        raise render_png.MissingPngDependency("no drawing available")
    monkeypatch.setattr(render_png, "svg_to_png", cli_broken)
    cli_out = tmp_path / "cli"
    assert cli.main([str(fixture_dir), "--all", "--tz", "0", "--out", str(cli_out)]) == 3

    def broken(svg, width):
        raise sws.PngUnavailable("no drawing available")
    out = tmp_path / "o"
    msgs = []
    assert sws.run_headless([str(fixture_dir), "--all", "--tz", "0", "--out", str(out)], png_renderer=broken,
                            say=lambda m, level="info": msgs.append(m)) == sws.EXIT_NO_PNG
    assert sorted(p.name for p in out.iterdir()) == sorted(p.name for p in cli_out.iterdir())
    assert (out / "summary.json").exists() and not list(out.glob("*.svg")) and not list(out.glob("*.png"))
    assert msgs[-1] == "no drawing available"


def test_typed_paths_may_start_with_a_tilde(sws, fixture_dir, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert sws.run_headless([f"~/{fixture_dir.name}", "--all", "--tz", "0", "--json-only", "--out", "~/cards"],
                            say=lambda *a, **k: None) == 0
    assert (tmp_path / "cards" / "summary.json").exists()
    assert not (Path.cwd() / "~").exists()


class _FakeSiril:
    def __init__(self, headless):
        self.headless = headless

    def connect(self):
        return True

    def is_cli(self):
        return True                                   # sirilpy says True for anything but a menu click

    def is_headless(self):
        return self.headless

    def log(self, *a, **k):
        pass

    def disconnect(self):
        pass


@pytest.mark.parametrize("headless, argv, expected", [
    (False, [], "window"),                            # menu click, or `pyscript SkyWrapped.py` typed in Siril
    (False, ["/lights"], "typed"),                    # a folder given: no window
    (True, [], "typed"),                              # siril-cli / headless Siril: no screen, so the usage message
])
def test_window_or_typed_command(sws, monkeypatch, headless, argv, expected):
    import types
    fake = types.SimpleNamespace(SirilInterface=lambda: _FakeSiril(headless),
                                 LogColor=types.SimpleNamespace(RED=1, GREEN=2, DEFAULT=0))
    monkeypatch.setitem(sys.modules, "sirilpy", fake)
    calls = []
    monkeypatch.setattr(sws, "run_window", lambda siril: calls.append("window"))
    monkeypatch.setattr(sws, "run_headless", lambda a, say: calls.append("typed") or 0)
    assert sws.main(argv) == 0
    assert calls == [expected]


def test_install_decisions(sws, monkeypatch):
    calls = []
    monkeypatch.setattr(sws, "installed_version", lambda: "0.1.0")
    assert sws.ensure_skywrapped(installer=lambda v: calls.append(v)) == "0.1.0" and calls == []   # installed: used as is

    state = {"v": None}
    monkeypatch.setattr(sws, "installed_version", lambda: state["v"])

    def install(minimum):
        calls.append(minimum)
        state["v"] = "0.1.0"
    said = []
    assert sws.ensure_skywrapped(say=said.append, installer=install) == "0.1.0"                     # missing: installed
    assert calls == ["0.1.0"] and "Installing skywrapped" in said[0] and "internet" in said[0]

    calls.clear()
    state["v"] = "0.0.5"                                                                            # too old: upgraded
    assert sws.ensure_skywrapped(say=said.append, installer=install) == "0.1.0" and calls == ["0.1.0"]
    assert "Updating skywrapped 0.0.5" in said[-1]


def test_install_failure_is_explained(sws, monkeypatch):
    monkeypatch.setattr(sws, "installed_version", lambda: None)

    def offline(minimum):
        raise OSError("network is unreachable")
    with pytest.raises(sws.SetupError) as e:
        sws.ensure_skywrapped(installer=offline)
    text = str(e.value)
    assert "Could not install skywrapped" in text and "online" in text and "aousabdo.github.io/skywrapped" in text
    assert "network is unreachable" in text                                                          # the technical detail

    def exits(minimum):
        raise SystemExit(1)                                                                         # sirilpy exits on a restart
    with pytest.raises(sws.SetupError):
        sws.ensure_skywrapped(installer=exits)

    monkeypatch.setattr(sws, "installed_version", lambda: None)                                     # installer "worked", nothing there
    with pytest.raises(sws.SetupError, match="still missing"):
        sws.ensure_skywrapped(installer=lambda minimum: None)


def test_old_python_is_explained(sws, monkeypatch):
    monkeypatch.setattr(sws, "installed_version", lambda: None)
    monkeypatch.setattr(sws, "MIN_PYTHON", (3, 99))                                                 # "this Python is too old"
    with pytest.raises(sws.SetupError, match=r"needs Python 3\.99 or newer"):
        sws.ensure_skywrapped(installer=lambda v: pytest.fail("must not try"))


def test_qt_rewrite_of_the_text(sws):
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100" viewBox="0 0 200 100">'
           '<text x="100" y="50" font-family="\'Skywrapped Inter\', sans-serif" font-size="20" fill="#fff" '
           'letter-spacing="2" text-anchor="end">A&amp;B</text>'
           '<text x="10" y="80" font-family="\'Skywrapped EB Garamond\', serif" font-size="30">Hello <tspan fill="#f00">x</tspan>'
           '</text></svg>')
    out = sws.qt_ready_svg(svg, advance=lambda family, weight, ch: 0.5)
    root = ET.fromstring(out)
    texts = [e for e in root if e.tag.endswith("text")]
    first = texts[:3]
    assert [t.text for t in first] == ["A", "&", "B"]                          # one text per letter, xml-escaped and decoded
    assert [float(t.get("x")) for t in first] == [100 - 36, 100 - 36 + 12, 100 - 36 + 24]   # end-anchored: 3 x (10 + 2) wide
    assert all(t.get("font-family") == "Skywrapped Inter" and t.get("letter-spacing") is None
               and t.get("text-anchor") is None for t in first)
    last = texts[3]
    assert last.get("font-family") == "Skywrapped EB Garamond" and last.get("x") == "10"      # untracked text stays whole
    assert "Hello " in "".join(last.itertext())


def test_no_wait_cursor():
    """Qt's wait cursor crashes Siril's Python on macOS (signal 11, PyQt6 6.11): the script must never set one."""
    code = "\n".join(ln for ln in SCRIPT.read_text(encoding="utf-8").splitlines() if not ln.lstrip().startswith("#"))
    assert "setOverrideCursor" not in code and "WaitCursor" not in code and "BusyCursor" not in code


def test_qt_colours_have_no_rgba(sws):
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
           '<rect fill="rgba(255,255,255,0.08)" width="1" height="1"/>'
           '<rect fill="rgba(255, 0, 128, 50%)" fill-opacity="0.5" stroke="rgba(0,0,0,1)" width="1" height="1"/>'
           '<circle fill="#fff" fill-opacity="0.3" r="1"/>'
           '<radialGradient id="g"><stop offset="0" stop-color="rgba(16,32,48,0.25)"/></radialGradient>'
           '<rect fill="rgba(nonsense)" width="1" height="1"/></svg>')
    root = ET.fromstring(sws.qt_colors(svg))
    r1, r2, c, g, r3 = list(root)
    assert (r1.get("fill"), r1.get("fill-opacity")) == ("#ffffff", "0.08")
    assert (r2.get("fill"), r2.get("fill-opacity")) == ("#ff0080", "0.25")       # 50 % times the 0.5 it had
    assert (r2.get("stroke"), r2.get("stroke-opacity")) == ("#000000", "1")
    assert (c.get("fill"), c.get("fill-opacity")) == ("#fff", "0.3")             # untouched
    assert (g[0].get("stop-color"), g[0].get("stop-opacity")) == ("#102030", "0.25")
    assert r3.get("fill") == "rgba(nonsense)"                                      # not understood: left alone
    assert sws.qt_colors("<svg/>") == "<svg/>"


def test_qt_rewrite_leaves_real_cards_valid(sws, fixture_dir):
    frames, skipped = sws.scan_frames([str(fixture_dir)], [])
    wrapped = sws.count_year(frames, skipped, None, 0.0)
    for theme in sws.THEMES:
        for stem, card in sws.draw_cards(wrapped, theme):
            out = sws.qt_ready_svg(card.svg, advance=lambda family, weight, ch: 0.55)
            assert "rgba(" not in out                                              # Qt would paint it black
            root = ET.fromstring(out)
            assert root.get("width") == str(card.width)
            for t in root.iter():
                if t.tag.endswith("text"):
                    assert "," not in t.get("font-family") and "'" not in t.get("font-family")
                    assert t.get("letter-spacing") is None or len(t) > 0       # only a text with child elements keeps it
