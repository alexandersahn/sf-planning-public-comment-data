"""Pro-housing group presence at the Planning Commission, 1998-present.

Two series, both the share of proceedings at which at least one member of a
pro-housing organization spoke:

  meetings  every commission hearing
  hearings  agenda items on the Regular Calendar or Discretionary Review
            whose text trips the housing keyword flag

and in each, two lines: the YIMBY movement proper (SFBARF, SF YIMBY, YIMBY
Action) and any pro-housing group, which adds the Housing Action Coalition
and GrowSF.

Affiliation comes from `role_long` in the released `comments.csv`, which the
build assigns from the curated rosters in `pipeline/rosters.py` plus each
speaker's own self-identification. See analysis/README.md for provenance.

Writes analysis/output/*.csv and analysis/figures/*.png.
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PUB = ROOT / "public"
OUT = Path(__file__).resolve().parent / "output"
FIG = Path(__file__).resolve().parent / "figures"

YIMBY_ROLES = {"YIMBY"}
PRO_HOUSING_ROLES = {"YIMBY", "Pro-Housing Advocacy"}

# roles that are not members of the public testifying on their own behalf
NON_PUBLIC = {"Planning Staff", "Project Team", "DR Team", "Legal",
              "Supervisor's Office", "Mayor's Office", "City Agency",
              "Commissioner"}

INK, MUTED, GRID, BG = "#1F2A36", "#5B6570", "#E4DFD6", "#FFFFFF"
ORANGE, BLUE = "#D9622B", "#2A6FB5"


def public_comments():
    c = pd.read_csv(PUB / "comments.csv", low_memory=False)
    c["year"] = pd.to_datetime(c.meeting_date, errors="coerce").dt.year
    pub = c[(c.is_staff != 1) & (c.is_commissioner != 1)
            & ~c.role_long.isin(NON_PUBLIC)].copy()
    pub["is_yimby"] = pub.role_long.isin(YIMBY_ROLES)
    pub["is_ph"] = pub.role_long.isin(PRO_HOUSING_ROLES)
    return pub


def share_by_year(df, unit):
    """Share of `unit` groups per year with >=1 pro-housing speaker."""
    g = df.groupby(unit).agg(year=("year", "first"),
                             any_ph=("is_ph", "any"),
                             any_y=("is_yimby", "any"))
    return g.groupby("year").agg(n=("any_ph", "size"),
                                 share_ph=("any_ph", "mean"),
                                 share_y=("any_y", "mean"))


def plot(d, ylabel, path, ymax):
    d = d.loc[1998:2025]
    fig, ax = plt.subplots(figsize=(14, 6), facecolor=BG)
    ax.set_facecolor(BG)
    ax.plot(d.index, d.share_ph * 100, color=BLUE, lw=2.5, marker="o", ms=7,
            mec=BG, mew=1.5, zorder=3,
            label="Any pro-housing group (adds Housing Action Coalition, GrowSF)")
    ax.plot(d.index, d.share_y * 100, color=ORANGE, lw=2.5, marker="o", ms=7,
            mec=BG, mew=1.5, zorder=4,
            label="YIMBY movement (SFBARF, SF YIMBY, YIMBY Action)")
    ax.legend(loc="upper left", frameon=False, fontsize=15)
    ax.axvline(2014, color=MUTED, lw=1, ls=(0, (3, 3)), zorder=1)
    ax.text(2013.8, ymax * .82, "SFBARF founded,\n2014", ha="right", va="top",
            fontsize=13, color=MUTED)
    ax.set_ylim(0, ymax)
    ax.set_xlim(1997.5, 2026)
    ticks = [0, ymax * .25, ymax * .5, ymax * .75, ymax]
    ax.set_yticks(ticks)
    ax.set_yticklabels([f"{t:.0f}" for t in ticks[:-1]] + [f"{ymax:.0f}%"])
    ax.set_ylabel(ylabel, fontsize=14)
    ax.grid(axis="y", color=GRID, lw=1)
    ax.set_axisbelow(True)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)
    fig.tight_layout()
    fig.savefig(path, dpi=200, facecolor=BG)
    plt.close(fig)


def main():
    OUT.mkdir(exist_ok=True)
    FIG.mkdir(exist_ok=True)
    plt.rcParams.update({"font.family": "Helvetica Neue", "font.size": 15,
                         "text.color": INK, "axes.labelcolor": MUTED,
                         "xtick.color": MUTED, "ytick.color": MUTED})
    pub = public_comments()

    meetings = share_by_year(pub, "meeting_date")
    meetings.to_csv(OUT / "pro_housing_by_meeting.csv")
    plot(meetings,
         "Planning Commission meetings with ≥1\npro-housing group member speaking",
         FIG / "pro_housing_presence_meetings.png", 100)

    items = pd.read_csv(PUB / "items.csv.gz", low_memory=False)
    housing = items[items.section_group.isin(["Regular Calendar",
                                              "Discretionary Review"])
                    & (items.housing_kw == 1)]
    hear = pub[pub.item_id.isin(housing.item_id)]
    hearings = share_by_year(hear, "item_id")
    hearings.to_csv(OUT / "pro_housing_by_hearing.csv")
    plot(hearings,
         "Housing hearings with ≥1 pro-housing\ngroup member speaking",
         FIG / "pro_housing_presence_hearings.png", 45)

    print("meetings, 2010-2025:")
    print(meetings.loc[2010:2025].round(3).to_string())
    print("\nhousing hearings, 2010-2025:")
    print(hearings.loc[2010:2025].round(3).to_string())
    for lab, d in (("meetings", meetings), ("housing hearings", hearings)):
        m = d.loc[2018:2025, ["share_ph", "share_y"]].mean().round(3)
        print(f"{lab} 2018-25 mean: {m.to_dict()}")
    print("\ncomments by pro-housing role:")
    print(pub[pub.is_ph].role_long.value_counts().to_string())


if __name__ == "__main__":
    main()
