"""Year-in-astro cards as SVG: six 1080 x 1350 portrait cards and a 1600 x 900 poster, in two themes.

Pure stdlib (it runs in Pyodide). The two OFL fonts are embedded in every SVG as base64 ``@font-face`` rules;
``font_files()`` gives their paths for renderers that load fonts from files instead.
"""
from .layouts import Card, render_cards
from .svg import font_files
from .themes import THEMES, Theme

__all__ = ["Card", "THEMES", "Theme", "font_files", "render_cards"]
