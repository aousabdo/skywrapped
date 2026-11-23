"""Build the web page into _site/: the skywrapped wheel (``python -m build``) plus web/, with build values filled in.

    .venv/bin/python scripts/build_web.py [--out _site]

The values come from the package itself: the wheel's file name goes into worker.js, the version and
TESTED_VENDORS into index.html. The output folder is replaced only when this script made it (a marker file).
"""
from __future__ import annotations

import argparse
import html
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import skywrapped  # noqa: E402

PAGES = ("index.html", "app.js", "worker.js", "style.css")
MARKER = ".skywrapped-site"
WHEEL_BUDGET = 2_000_000  # spec: wheel plus data <= 2 MB


def build_wheel(dest: Path) -> Path:
    subprocess.run([sys.executable, "-m", "build", "--wheel", "--outdir", str(dest), str(ROOT)], check=True,
                   stdout=subprocess.DEVNULL)
    wheels = sorted(dest.glob("skywrapped-*.whl"))
    if len(wheels) != 1:
        raise SystemExit(f"expected one wheel, found {len(wheels)}")
    return wheels[0]


def fill(name: str, text: str, wheel: str) -> str:
    values = {
        "@@WHEEL@@": wheel,
        "@@VERSION@@": html.escape(skywrapped.__version__),
        "@@TESTED_VENDORS@@": html.escape(", ".join(skywrapped.TESTED_VENDORS)),
    }
    for token, value in values.items():
        text = text.replace(token, value)
    if "@@" in text:
        raise SystemExit(f"web/{name}: an unfilled @@ token is left")
    return text


def prepare(out: Path) -> None:
    if out.exists():
        if not (out / MARKER).exists():
            raise SystemExit(f"{out} exists and was not made by this script; choose another --out")
        shutil.rmtree(out)
    out.mkdir(parents=True)
    (out / MARKER).write_text("Made by scripts/build_web.py; replaced on every build.\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--out", default=str(ROOT / "_site"))
    args = p.parse_args(argv)
    out = Path(args.out).resolve()

    with tempfile.TemporaryDirectory() as tmp:
        wheel = build_wheel(Path(tmp))
        size = wheel.stat().st_size
        if size > WHEEL_BUDGET:
            raise SystemExit(f"{wheel.name} is {size:,} bytes, over the {WHEEL_BUDGET:,}-byte budget")
        prepare(out)
        shutil.copy2(wheel, out / wheel.name)
    for name in PAGES:
        text = (ROOT / "web" / name).read_text(encoding="utf-8")
        (out / name).write_text(fill(name, text, wheel.name), encoding="utf-8")
    print(f"{out}: {', '.join(PAGES)} and {wheel.name} ({size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
