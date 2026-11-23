"""index.html: the PNG cards on one page. Relative paths only, no scripts, no external requests."""
import html
from pathlib import Path

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Skywrapped</title>
<style>body{{margin:0;padding:24px;background:#111;font-family:system-ui,sans-serif;color:#ccc}}
h1{{font-size:18px;font-weight:600;margin:0 0 16px}}
.grid{{display:flex;flex-wrap:wrap;gap:16px;align-items:flex-start}}
img{{display:block;max-width:100%;height:auto;border-radius:6px}}
.p{{width:min(360px,100%)}}.w{{width:min(740px,100%)}}</style></head>
<body><h1>Your year in astro</h1><div class="grid">
{imgs}
</div></body></html>
"""


def card_stems(cards: list):
    """Yield (card, file stem): portrait cards are card-1, card-2, ... in order; the poster is 'poster'."""
    n = 0
    for c in cards:
        if c.name == "poster":
            yield c, "poster"
        else:
            n += 1
            yield c, f"card-{n}"


def write_preview(out_dir: Path, cards: list) -> Path:
    """``cards``: Card objects; portrait cards are card-N.png in order, the poster is poster.png."""
    imgs = []
    for c, stem in card_stems(cards):
        if stem == "poster":
            imgs.append('<img class="w" src="poster.png" alt="Poster">')
        else:
            alt = html.escape(f"{stem.replace('card-', 'Card ')}: {c.name}", quote=True)
            imgs.append(f'<img class="p" src="{stem}.png" alt="{alt}">')
    path = Path(out_dir) / "index.html"
    path.write_text(PAGE.format(imgs="\n".join(imgs)), encoding="utf-8")
    return path
