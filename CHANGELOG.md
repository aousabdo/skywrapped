# Changelog

## Unreleased

- README: the run commands use a real-looking folder instead of a `PATH` placeholder, and show `pip`, `uvx` and
  `pipx` side by side, so the first command works without pipx.
- A Siril 1.4 script, `SkyWrapped/SkyWrapped.py`: the cards from Siril's Scripts menu (a window) or its command line
  (`pyscript SkyWrapped.py <folder>`). It installs the `skywrapped` package on first run and draws the PNGs with Siril's
  own PyQt6. Setup steps in `SkyWrapped/README.md`.

## 0.1.0 - 2026-11-23

First release.

- Reads FITS, `.fz` and XISF headers only (no pixel data) and counts light frames into nights, targets and rigs.
- Six portrait cards and a landscape poster, in an observatory and a nebula theme, as SVG and PNG, plus
  `summary.json` and a small `index.html`.
- Command line: `--year`, `--all`, `--theme`, `--out`, `--exclude`, `--tz`, `--json-only`, `--version`. Output
  folders are marked and never mixed between runs.
- A web page that runs the same code in the browser with Pyodide; files are not uploaded.
- Header fixtures for ASIAIR, Celestron Origin, N.I.N.A., ZWO Seestar, Dwarf 3 and Ekos/KStars.
