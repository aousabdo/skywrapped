# SkyWrapped for Siril

Make your "year in astro" cards from inside Siril: a cover, a night calendar, your top targets, your journey, your
records and your gear, plus a poster. You click, wait and save. No terminal.

SkyWrapped reads only the headers of your light frames (FITS and XISF files), never the pixels, and nothing is
uploaded. The first run downloads one small add-on (the `skywrapped` package, about 1 MB), so the computer must be
online that once.

## Set it up (once)

1. Put `SkyWrapped.py` in a folder of its own, for example `Documents/My Siril scripts`. (If you downloaded this whole
   repository, the `siril` folder next to this file is that folder.) The folder's name is what Siril will show in its
   Scripts menu.
2. In Siril open **Preferences** (on a Mac: Siril > Preferences) and go to the **Scripts** tab.
3. Under **Script Storage Directories** click **+** and choose that folder. Click the button below the list that
   rescans the folders, or restart Siril.
4. The Scripts menu now has your folder's name, and under it **SkyWrapped**.

## Make your cards

1. Choose **Scripts > (your folder) > SkyWrapped**. The first time, the window says it is getting ready while it
   downloads the add-on. When it says "skywrapped is ready", go on.
2. **Lights folder.** Siril's working folder is filled in. That is usually one target or one session, so click
   **Use the parent folder** (as often as it takes) until the folder holds the lights of the whole year, or press
   **Choose...** and pick it. Subfolders are searched.
3. Pick the **year** (this year, a year you type, or all years), the **theme**, and leave the **UTC offset** as it is
   (it starts at your computer's time zone and decides which evening a late frame belongs to). The **skip list** keeps
   rejected subs and preview pictures out of the count; edit it if your folders are named differently.
4. Press **Run**. A bar shows the headers being read (a few thousand files take a few seconds, a very large archive
   about half a minute). **Cancel** stops it.
5. Click through the cards. Changing the theme redraws them at once. Press **Save PNGs**: the cards land in a new
   folder named `skywrapped-<year>` (or `skywrapped-all`) in your Documents folder, never inside your lights folder.
   **Open output folder** shows them. Each run also saves the SVG files, a `summary.json` of the numbers and an
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
- **SkyWrapped is not in the Scripts menu**: the folder was not added, or Siril has not rescanned it yet. Restart Siril.

## Typed command

For scripts and `siril-cli`, the same thing runs without a window:

```
pyscript SkyWrapped.py /path/to/lights --all --tz -5 --default-excludes
```

Options: `--year N` or `--all` (default: this year), `--theme observatory|nebula`, `--tz HOURS`, `--out DIR`
(default: `skywrapped-<year>` in your Documents folder), `--exclude GLOB` (repeatable), `--default-excludes` (the
window's skip list), `--json-only`. They behave as in the `skywrapped` command line, and write the same `summary.json`
and the same card SVGs.

## Notes

- The cards are drawn with the PyQt6 that Siril's Python already has, so nothing else needs installing. They match the
  ones the `skywrapped` command line makes, apart from small differences in how the text is smoothed.
- Tested with Siril 1.4 on macOS. Windows and Linux should work but have not been tried.
- SkyWrapped is MIT licensed, like the rest of this project: https://github.com/aousabdo/skywrapped
