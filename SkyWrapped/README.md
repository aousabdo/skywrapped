# SkyWrapped for Siril

Make your "year in astro" cards from inside Siril: a cover, a night calendar, your top targets, your journey, your
records and your gear, plus a poster. You click, wait and save. No terminal.

SkyWrapped reads only the headers of your light frames (FITS and XISF files), never the pixels, and nothing is
uploaded. The first run downloads one small add-on (the `skywrapped` package, under half a megabyte). If your Siril
does not have PyQt6 yet, which draws the window and the cards, that is downloaded too, and it is much bigger (about
100 MB on Linux). The computer must be online that once.

## Set it up (once)

1. Put `SkyWrapped.py` in a folder of its own, for example `Documents/My Siril scripts`. (If you downloaded this whole
   repository, the `SkyWrapped` folder this file is in is that folder.) The folder's name is what Siril will show under
   **Scripts > Python Scripts**.
2. Open Siril's **Preferences** window (on a Mac it is **Siril > Settings…**) and click **Scripts** in its list.
3. **Scripts Storage Directories** is a text box with one folder per line. Click at the end of the last line, press
   Return, and type (or paste) the full path of your folder, for example `/Users/you/Documents/My Siril scripts`.
   Click the round-arrow button under the box, then **Apply**.
4. The **Scripts** menu now has **Python Scripts > (your folder) > SkyWrapped.py**.

## Make your cards

1. Choose **Scripts > Python Scripts > (your folder) > SkyWrapped.py**. The first time, the window says it is getting
   ready while it downloads the add-on. When it says "skywrapped 0.1.0 is ready" (the number may be newer), go on.
   If PyQt6 is missing, it is downloaded before any window appears: give it a few minutes, and watch Siril's Console.
2. **Lights folder.** Siril's working folder is filled in. That is usually one target or one session, so click
   **Use the parent folder** (as often as it takes) until the folder holds the lights of the whole year, or press
   **Choose...** and pick it. Subfolders are searched.
3. Pick the **year** (this year, a year you type, or all years), the **theme**, and leave the **UTC offset** as it is
   (it starts at your computer's time zone and decides which evening a late frame belongs to). The **skip list** keeps
   rejected subs and preview pictures out of the count; edit it if your folders are named differently.
4. Press **Run**. A bar shows the headers being read (a few thousand files take a few seconds, a very large archive
   about half a minute). **Cancel** stops it.
5. Click through the cards. Changing the theme redraws them at once. Press **Save PNGs**: the cards land in a new
   folder named `skywrapped-<year>` (or `skywrapped-all`) in your Documents folder; **Change...** next to "Save in"
   picks another place. Saving again after another run replaces that folder's cards. **Open output folder** shows them. Each run also saves the SVG files, a `summary.json` of the numbers and an
   `index.html` that flips through the cards. It never writes into a folder that has other files in it.

## If something goes wrong

- **"Could not install skywrapped"**: the one-time download failed, usually because the computer is offline or a
  firewall blocks Python. Connect, then press **Try again**. Siril's Console (the log panel in its main window) shows what pip said. The
  web page https://aousabdo.github.io/skywrapped/ makes the same cards in a browser if the install keeps failing.
- **"No light frames found"**: the folder is wrong or holds only calibration frames. Try **Use the parent folder**, or
  check the skip list: a folder whose own name matches a pattern (say it sits inside a folder called `previews`) is skipped
  entirely. If the message names other years, pick one of them or **All years**.
- **Cards show fewer hours than you expect**: only light frames count. Darks, flats, bias frames, stacks made from subs
  you also have, and duplicates are left out; the line above the cards says how many of each.
- **A night looks like two, or two look like one**: set the UTC offset to your own time zone (for example -5, or 5.5).
- **SkyWrapped is not in the Scripts menu**: the folder's line in Preferences > Scripts is missing or mistyped, or Siril
  has not rescanned it yet. Check the path, click the round-arrow button and **Apply**, or restart Siril.

## Typed command

Given a folder, the same thing runs without a window, in Siril's command line, in scripts and in `siril-cli`.
Typed with no folder (`pyscript SkyWrapped.py`) in Siril, it opens the window.

```
pyscript SkyWrapped.py /path/to/lights --all --tz -5 --default-excludes
```

Options: `--year N` or `--all` (default: this year), `--theme observatory|nebula`, `--tz HOURS`, `--out DIR`
(default: `skywrapped-<year>` in your Documents folder), `--exclude GLOB` (repeatable), `--default-excludes` (the
window's skip list), `--json-only`. They behave as in the `skywrapped` command line, and write the same `summary.json`
and the same card SVGs. Paths may start with `~`.

## Notes

- The cards are drawn with PyQt6 in Siril's Python (installed on the first run if it is missing), so no separate PNG
  library is needed. They match the ones the `skywrapped` command line makes, apart from small differences in how the
  text is smoothed.
- Tested with Siril 1.4.5 on macOS. Windows and Linux should work but have not been tried.
- SkyWrapped is MIT licensed, like the rest of this project: https://github.com/aousabdo/skywrapped
