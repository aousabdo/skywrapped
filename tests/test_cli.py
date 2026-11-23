import importlib.util
import json

import pytest

import skywrapped
from skywrapped.cli import main


def test_cli_json_only(tmp_path, fixture_dir):
    assert main([str(fixture_dir), "--json-only", "--out", str(tmp_path / "o"), "--year", "2026", "--tz", "-5"]) == 0
    assert json.loads((tmp_path / "o" / "summary.json").read_text())["frames"] >= 1


def test_cli_no_lights(tmp_path, capsys):
    assert main([str(tmp_path), "--json-only", "--out", str(tmp_path / "o")]) == 2
    assert "No light frames found" in capsys.readouterr().err


def test_cli_version(capsys):
    with pytest.raises(SystemExit) as e:
        main(["--version"])
    assert e.value.code == 0 and skywrapped.__version__ in capsys.readouterr().out


def test_cli_all_final_line_has_counts_and_no_paths(tmp_path, fixture_dir, capsys):
    assert main([str(fixture_dir), "--json-only", "--out", str(tmp_path / "o"), "--all", "--tz", "0"]) == 0
    cap = capsys.readouterr()
    last = cap.out.strip().splitlines()[-1]
    assert " h · " in last and "nights" in last and "frames" in last and "targets" in last
    assert "Light_" not in cap.out + cap.err and str(fixture_dir) not in cap.out + cap.err
    assert json.loads((tmp_path / "o" / "summary.json").read_text())["year"] is None


def test_cli_default_out_dir_is_year_folder(tmp_path, fixture_dir, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main([str(fixture_dir), "--json-only", "--year", "2026", "--tz", "0"]) == 0
    assert (tmp_path / "skywrapped-2026" / "summary.json").exists()


def test_cli_exclude(tmp_path, fixture_dir, capsys):
    assert main([str(fixture_dir), "--json-only", "--out", str(tmp_path / "o"), "--exclude", "*"]) == 2
    assert "No light frames found" in capsys.readouterr().err


needs_resvg = pytest.mark.skipif(importlib.util.find_spec("resvg_py") is None, reason="needs resvg-py")


@needs_resvg
def test_cli_writes_everything(tmp_path, fixture_dir):
    out = tmp_path / "out"
    out.mkdir()
    assert main([str(fixture_dir), "--out", str(out), "--year", "2026", "--tz", "-5"]) == 0
    for n in ["card-1.png", "poster.png", "summary.json", "index.html", "card-1.svg", "poster.svg"]:
        assert (out / n).exists(), n
    html = (out / "index.html").read_text(encoding="utf-8")
    assert 'src="card-1.png"' in html and 'src="poster.png"' in html
    assert "http://" not in html and "https://" not in html and str(out) not in html
    n_png = len(list(out.glob("card-*.png")))
    assert n_png == len(list(out.glob("card-*.svg"))) and n_png >= 5


def test_cli_missing_resvg_exits_3(tmp_path, fixture_dir, monkeypatch, capsys):
    out = tmp_path / "out"
    out.mkdir()
    import sys
    monkeypatch.setitem(sys.modules, "resvg_py", None)
    assert main([str(fixture_dir), "--out", str(out), "--year", "2026", "--tz", "-5"]) == 3
    assert "pip install 'skywrapped[cli]'" in capsys.readouterr().err


ARGS = ["--year", "2026", "--tz", "-5"]


@needs_resvg
def test_marked_folder_cleared_of_own_files_only(tmp_path, fixture_dir):
    out = tmp_path / "out"
    out.mkdir()
    (out / ".skywrapped-output").write_text("x")
    for n in ["card-9.png", "card-9.svg", "index.html", "poster.png", "summary.json"]:
        (out / n).write_text("old")
    (out / "notes.txt").write_text("mine")
    assert main([str(fixture_dir), "--out", str(out), *ARGS]) == 0
    assert not (out / "card-9.png").exists() and not (out / "card-9.svg").exists()
    assert (out / "notes.txt").read_text() == "mine" and (out / ".skywrapped-output").exists()
    assert (out / "card-1.png").stat().st_size > 1000


def test_unmarked_nonempty_folder_exit_4(tmp_path, fixture_dir, capsys):
    out = tmp_path / "out"
    out.mkdir()
    (out / "notes.txt").write_text("mine")
    assert main([str(fixture_dir), "--out", str(out), *ARGS]) == 4
    assert "Choose an empty output folder (or one skywrapped made before)." in capsys.readouterr().err
    assert sorted(p.name for p in out.iterdir()) == ["notes.txt"]


def test_json_only_rerun_removes_old_cards(tmp_path, fixture_dir):
    out = tmp_path / "out"
    out.mkdir()
    (out / ".skywrapped-output").write_text("x")
    for n in ["card-1.png", "card-1.svg", "poster.png", "index.html"]:
        (out / n).write_text("old")
    assert main([str(fixture_dir), "--json-only", "--out", str(out), *ARGS]) == 0
    assert sorted(p.name for p in out.iterdir()) == [".skywrapped-output", "summary.json"]


def test_missing_resvg_exits_3_and_clears_old_pngs(tmp_path, fixture_dir, monkeypatch, capsys):
    out = tmp_path / "out"
    out.mkdir()
    import sys
    (out / ".skywrapped-output").write_text("x")
    (out / "card-1.png").write_text("old")
    (out / "index.html").write_text("old")
    monkeypatch.setitem(sys.modules, "resvg_py", None)
    assert main([str(fixture_dir), "--out", str(out), *ARGS]) == 3
    assert "pip install 'skywrapped[cli]'" in capsys.readouterr().err
    assert not (out / "card-1.png").exists() and not (out / "index.html").exists()


def _light(fixture, when: str) -> bytes:
    """The ASIAIR light fixture with another DATE-OBS (same length, so the cards stay 80 wide)."""
    data = fixture("asiair_2600air")
    old = b"2026-09-06T05:11:25.157930"
    assert len(when) == len(old) and old in data
    return data.replace(old, when.encode())


def test_cli_wrong_year_names_the_years_found(tmp_path, fixture, capsys):
    """I6: counts and years only, and the nearest year to try."""
    lights = tmp_path / "lights"
    lights.mkdir()
    (lights / "Light_a.fit").write_bytes(_light(fixture, "2025-09-06T05:11:25.157930"))
    (lights / "Light_b.fit").write_bytes(_light(fixture, "2026-09-06T05:11:25.157930"))
    assert main([str(lights), "--json-only", "--out", str(tmp_path / "o"), "--year", "2024", "--tz", "0"]) == 2
    err = capsys.readouterr().err.strip().splitlines()[-1]
    assert err == "No light frames from 2024. Found lights from: 2025, 2026. Try --year 2025 or --all."
    assert main([str(lights), "--json-only", "--out", str(tmp_path / "o"), "--year", "2027", "--tz", "0"]) == 2
    err = capsys.readouterr().err.strip().splitlines()[-1]
    assert err == "No light frames from 2027. Found lights from: 2025, 2026. Try --year 2026 or --all."
    assert "Light_" not in err and str(lights) not in err


def test_cli_other_errors_are_not_reported_as_no_lights(tmp_path, fixture_dir, monkeypatch):
    """I3: only NoLightsError means "no lights"; any other error surfaces as itself."""
    import skywrapped.cli as cli

    def broken(*a, **k):
        raise ValueError("a bug, not an empty folder")
    monkeypatch.setattr(cli, "compute_wrapped", broken)
    with pytest.raises(ValueError, match="a bug"):
        main([str(fixture_dir), "--json-only", "--out", str(tmp_path / "o"), "--year", "2026"])


def test_cli_nan_declination_does_not_stop_the_run(tmp_path, fixture):
    """I3: 50 good frames and one whose OBJCTDEC is 'NaN': the run succeeds; that frame simply has no position."""
    lights = tmp_path / "lights"
    lights.mkdir()
    good = fixture("seestar_sub")
    old = b"2026-05-14T03:12:45.931528"
    for i in range(50):
        stamp = f"2026-05-14T03:{13 + i // 6:02d}:{(i % 6) * 10:02d}.000000".encode()
        (lights / f"Light_{i:03d}.fit").write_bytes(good.replace(old, stamp))
    text = good.decode("ascii")
    cards = [text[i:i + 80] for i in range(0, len(text), 80)]
    bad = [c for c in cards if c[:8].strip() not in ("RA", "DEC")]
    end = bad.index(next(c for c in bad if c[:8].strip() == "END"))
    bad[end:end] = ["OBJCTRA = '00 42 44.3'".ljust(80), "OBJCTDEC= 'NaN     '".ljust(80)]
    raw = "".join(bad).encode("ascii")
    (lights / "Light_nan.fit").write_bytes(raw + b" " * (-len(raw) % 2880))
    assert main([str(lights), "--json-only", "--out", str(tmp_path / "o"), "--year", "2026", "--tz", "0"]) == 0
    s = json.loads((tmp_path / "o" / "summary.json").read_text())
    assert s["frames"] == 51 and s["targets"] == 1 and s["top_targets"][0]["key"] == "M31"
    assert s["top_targets"][0]["frames"] == 51  # the position-less frame joins M 31 by its OBJECT 'M 31'


def test_cli_final_line_plurals_and_type_assumed(tmp_path, fixture, capsys):
    lights = tmp_path / "lights"
    lights.mkdir()
    (lights / "Light_a.fit").write_bytes(fixture("asiair_2600air"))
    assert main([str(lights), "--json-only", "--out", str(tmp_path / "o"), "--year", "2026", "--tz", "0"]) == 0
    last = capsys.readouterr().out.strip().splitlines()[-1]
    assert last == "0.1 h · 1 night · 1 frame · 1 target"
    (lights / "Dark_b.fit").write_bytes(fixture("asiair_dark"))
    (lights / "x.fits").write_bytes(fixture("dwarf_sub"))           # no IMAGETYP: counted, type assumed
    assert main([str(lights), "--json-only", "--out", str(tmp_path / "o"), "--year", "2026", "--tz", "0"]) == 0
    last = capsys.readouterr().out.strip().splitlines()[-1]
    assert " · 2 nights · 2 frames · 2 targets · skipped: 1 calibration frame · 1 type assumed (counted)" in last


def test_cli_one_missing_path(tmp_path, capsys):
    assert main([str(tmp_path / "nope"), "--json-only", "--out", str(tmp_path / "o")]) == 2
    assert capsys.readouterr().err.strip() == "1 of the given paths does not exist."
    assert main([str(tmp_path / "a"), str(tmp_path / "b"), "--json-only", "--out", str(tmp_path / "o")]) == 2
    assert capsys.readouterr().err.strip() == "2 of the given paths do not exist."
