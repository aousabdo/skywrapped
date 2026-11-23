# Changelog

## Unreleased

- README: the run commands use a real-looking folder instead of a `PATH` placeholder, and show `pip`, `uvx` and
  `pipx` side by side, so the first command works without pipx.

## 0.1.0 - 2026-11-23

First release.

- Reads FITS, `.fz` and XISF headers only (no pixel data) and counts light frames into nights, targets and rigs.
- Six portrait cards and a landscape poster, in an observatory and a nebula theme, as SVG and PNG, plus
  `summary.json` and a small `index.html`.
- Command line: `--year`, `--all`, `--theme`, `--out`, `--exclude`, `--tz`, `--json-only`, `--version`. Output
  folders are marked and never mixed between runs.
- A web page that runs the same code in the browser with Pyodide; files are not uploaded.
- Header fixtures for ASIAIR, Celestron Origin, N.I.N.A., ZWO Seestar, Dwarf 3 and Ekos/KStars.
