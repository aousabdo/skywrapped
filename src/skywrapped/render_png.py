"""SVG card -> PNG with resvg. resvg-py is imported lazily; only the bundled fonts are used, never system ones."""
import contextlib
from importlib.resources import as_file, files

from .cards import font_files

class MissingPngDependency(RuntimeError):
    """resvg-py is not installed."""


NEEDS = "PNG output needs: pip install 'skywrapped[cli]'"


def _font_paths():
    """Real filesystem paths of the bundled fonts, even if the package were imported from a zip."""
    paths = font_files()
    stack = contextlib.ExitStack()
    from pathlib import Path
    if all(Path(p).is_file() for p in paths):
        return stack, paths
    out = [str(stack.enter_context(as_file(files("skywrapped.cards").joinpath("fonts", Path(p).name))))
           for p in paths]
    return stack, out


def svg_to_png(svg: str, width: int) -> bytes:
    try:
        import resvg_py
    except ImportError as e:
        raise MissingPngDependency(NEEDS) from e
    stack, fonts = _font_paths()
    with stack:
        return bytes(resvg_py.svg_to_bytes(svg_string=svg, width=width, skip_system_fonts=True, font_files=fonts))
