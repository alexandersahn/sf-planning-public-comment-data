# analysis/

Analyses built on the released tables in `public/`. Nothing here feeds the
release — `pipeline/` builds the data, `analysis/` reads it.

| script | what it produces |
|---|---|
| `pro_housing_presence.py` | share of hearings and of meetings with at least one pro-housing group member speaking, 1998–present; `output/*.csv` and two figures |

Run from the repository root:

```bash
.venv/bin/python analysis/pro_housing_presence.py
```

## Provenance

Ported (2026-09) from `Dropbox/Admin/public_facing/yimby_law/code`, which
computed these series with a roster of pro-housing organization members
pasted into the analysis script. That roster now lives in
`pipeline/rosters.py` and is applied during the build, so `comments.csv`
ships with the affiliation already attached and these scripts only aggregate.
Four scripts collapsed into one in the process: the two figure scripts there
wrote different series to the same `sf_yimby_presence.png`, so whichever ran
last won.

Not ported: `acct_fig.py` and `lit_figs.py`, which plot hardcoded numbers
from other published papers for a talk rather than anything computed from
this dataset. They belong with the slides, and the originals are untouched.
