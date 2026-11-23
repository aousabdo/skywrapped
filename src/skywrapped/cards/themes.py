"""The two card looks, with the values of the approved mockup (mockup-cards-v1.html)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Glow:
    """A radial glow over the background: ``color`` at ``opacity`` in the centre, fading to ``end`` at 0."""
    color: str
    end: str
    cx: int  # percent of the card
    cy: int
    r: int
    opacity: float


@dataclass(frozen=True)
class Theme:
    name: str
    bg: str
    glow: str
    fg: str
    muted: str
    accent: str
    accent2: str
    cell0: str
    ramp: tuple[str, str, str, str, str]
    serif: bool          # serif headings (observatory) or sans (nebula)
    glows: tuple[Glow, ...]
    stars: int           # starfield size on a portrait card
    star_r: tuple[float, float]  # radius = r0 + random * span
    cell_rx: int         # corner radius of calendar squares
    cover_size: int      # the cover's big number
    head: str            # font key for headings and numbers (see svg.FONTS)
    body: str = "sans"   # font key for everything else


OBSERVATORY = Theme(
    name="observatory", bg="#07090f", glow="#0f1a2e", fg="#ece6d8", muted="#8c93a3", accent="#d9a55b",
    accent2="#7fa7c9", cell0="#141a26", ramp=("#3a2f22", "#6b4f2c", "#a77b3e", "#d9a55b", "#f5d9a0"), serif=True,
    glows=(Glow("#0f1a2e", "#07090f", 50, 38, 75, 1.0),),
    stars=170, star_r=(0.6, 1.7), cell_rx=3, cover_size=300, head="serif",
)

NEBULA = Theme(
    name="nebula", bg="#160a33", glow="#0a3340", fg="#ffffff", muted="#c3b8e0", accent="#ffd166",
    accent2="#ff6f91", cell0="rgba(255,255,255,0.08)", ramp=("#3d2a7a", "#6a3fb5", "#c04fd0", "#ff6f91", "#ffd166"),
    serif=False,
    glows=(Glow("#c2185b", "#c2185b", 88, 8, 70, 0.75), Glow("#00bfa5", "#00bfa5", 5, 100, 75, 0.55)),
    stars=90, star_r=(0.8, 2.2), cell_rx=6, cover_size=330, head="display",
)

THEMES: dict[str, Theme] = {t.name: t for t in (OBSERVATORY, NEBULA)}
