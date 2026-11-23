# Data licences

The code is MIT (see `LICENSE`). The data files bundled in the package are released under their own terms, listed
here with their sources: the deep-sky catalogue and the distance table under CC-BY-SA 4.0, the card fonts under the
SIL Open Font License 1.1.

- **Deep-sky catalogue** (`src/skywrapped/data/catalogue.json.gz`, built by `scripts/build_catalogue.py`; rebuild with
  `.venv/bin/python scripts/build_catalogue.py`, which fetches into the git-ignored `.cache/`). It holds ids, aliases,
  J2000 positions, sizes, magnitudes, common names and object kinds from the sources below.
  - **OpenNGC** (`database_files/NGC.csv` and `addendum.csv`), Mattia Verga and contributors,
    https://github.com/mattiaverga/OpenNGC, licensed **CC-BY-SA 4.0** (https://creativecommons.org/licenses/by-sa/4.0/).
    It supplies the NGC and IC objects, Messier, Caldwell, Barnard 33, Collinder and Melotte cross-identifications,
    positions, sizes, magnitudes and common names. **Share-alike applies to the bundled data file**: the catalogue
    file is a derivative of OpenNGC and is released under CC-BY-SA 4.0 too. The MIT licence of the code does not
    cover it. Changes: names normalised (`NGC0224` -> `NGC224`), `Dup` rows folded in as aliases, non-existent
    objects dropped, columns reduced, and the entries listed in `scripts/extra_names.csv` added or corrected.
  - **VizieR** (CDS, Strasbourg; queried through astroquery, J2000 positions computed by VizieR):
    - VII/20, Sharpless S., 1959, *A Catalogue of HII Regions*, ApJS 4, 257 (Sh2).
    - VII/7A, Lynds B.T., 1962, *Catalogue of Dark Nebulae*, ApJS 7, 1 (LDN).
    - VII/9, Lynds B.T., 1965, *Catalogue of Bright Nebulae*, ApJS 12, 163 (LBN).
    - VII/220A, Barnard E.E., 1927, *A Photographic Atlas of Selected Regions of the Milky Way* (Barnard's
      dark objects, CDS table VII/220A).
    - VII/21, van den Bergh S., 1966, *Catalogue of Reflection Nebulae*, AJ 71, 990 (vdB).
    Tables from CDS are free to use with acknowledgement: "This research has made use of the VizieR catalogue access
    tool, CDS, Strasbourg, France" (Ochsenbein, Bauer & Marcout 2000, A&AS 143, 23).
  - **SIMBAD** (CDS), for the coordinates of five named fields (44 Tau, DG 26, NY Cep, zeta Oph, AF Lac) in
    `scripts/extra_names.csv`: "This research has made use of the SIMBAD database, operated at CDS, Strasbourg,
    France" (Wenger et al. 2000, A&AS 143, 9).
  - `scripts/extra_names.csv` (hand-curated common names and aliases, not taken from a catalogue; the Rho Ophiuchi position, 16h25m -23.4 deg, is
    approximate) is part of this project and released under the same CC-BY-SA 4.0 terms as the data file.
- **Distances** (`src/skywrapped/data/distances.csv`, built by `scripts/build_distances.py`; every row names its source,
  with the bibcodes of the measurements it uses). Values are medians of **SIMBAD** `mesDistance` measurements ("This
  research has made use of the SIMBAD database, operated at CDS, Strasbourg, France"; Wenger et al. 2000, A&AS 143,
  9), plus the globular-cluster distances of Baumgardt & Vasiliev 2021, MNRAS 505, 5957 (2021MNRAS.505.5957B; from
  Baumgardt's public table, https://people.smp.uq.edu.au/HolgerBaumgardt/globular/) and Fesen et al. 2021, MNRAS, for
  the Cygnus Loop (doi:10.1093/mnras/stab2066). The table is released under CC-BY-SA 4.0, like the catalogue. Review
  notes: `scripts/distances_review.md`.
- **Fonts on the cards** (`src/skywrapped/cards/fonts/`, built by `scripts/subset_fonts.py` from the variable fonts in
  https://github.com/google/fonts, `ofl/ebgaramond` and `ofl/inter`), both licensed under the **SIL Open Font License
  1.1** (https://openfontlicense.org); the full licence texts are in `src/skywrapped/cards/fonts/OFL.txt`.
  - **EB Garamond**, Copyright 2017 The EB Garamond Project Authors (https://github.com/octaviopardo/EBGaramond12):
    `EBGaramond-Regular.ttf`, the observatory theme's headings and numbers.
  - **Inter**, Copyright 2020 The Inter Project Authors (https://github.com/rsms/inter): `Inter-Regular.ttf` (body text
    in both themes) and `InterDisplay-ExtraBold.ttf` (the nebula theme's headings and numbers).

  Changes (these are Modified Versions under the OFL): static instances (EB Garamond weight 400; Inter weight 400 at
  optical size 14 and weight 800 at optical size 32), subset to Basic Latin, Latin-1 Supplement, Latin Extended-A and
  a few punctuation marks, hinting removed, EB Garamond's digits mapped to its proportional lining figures, and the
  family names changed to "Skywrapped EB Garamond", "Skywrapped Inter" and "Skywrapped Inter Display" so they never
  collide with an installed copy. `metrics.json` beside them holds their advance widths.
