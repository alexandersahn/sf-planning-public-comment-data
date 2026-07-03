"""Descriptive figures for the README, written to public/figures/.

  1. comments_by_year.png     comment volume per year, stacked by polarity
  2. polarity_share.png       share of signed comments that oppose, by year
  3. groups_over_time.png     interest-group comments per year, by group
  4. project_map.png          geocoded agenda items across the city
  5. top_commenters.png       most frequent named speakers
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PUB = ROOT / "public"
FIG = PUB / "figures"
FIG.mkdir(exist_ok=True)

plt.rcParams.update({
    "figure.dpi": 150, "savefig.bbox": "tight",
    "font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.alpha": 0.25, "grid.linewidth": 0.5,
    "axes.axisbelow": True,
})

POS, NEG, NEU, GREY = "#2b8cbe", "#d7301f", "#969696", "#d9d9d9"


def load():
    com = pd.read_csv(PUB / "comments.csv", low_memory=False)
    com["year"] = com["meeting_date"].astype(str).str[:4].astype(int)
    com = com[com["year"].between(1998, 2026)]
    items = pd.read_csv(PUB / "items.csv.gz", low_memory=False)
    return com, items


def fig_comments_by_year(com):
    g = com.groupby(["year", com["sign"].fillna("none")]).size().unstack(fill_value=0)
    for c in "+-=":
        if c not in g:
            g[c] = 0
    fig, ax = plt.subplots(figsize=(8, 3.4))
    bottom = None
    for key, color, label in [("+", POS, "support (+)"), ("-", NEG, "oppose (−)"),
                              ("=", NEU, "neutral (=)"), ("none", GREY, "no recorded sign")]:
        vals = g[key]
        ax.bar(g.index, vals, bottom=bottom, color=color, label=label, width=0.8)
        bottom = vals if bottom is None else bottom + vals
    ax.set_ylabel("public comments")
    ax.set_title("Public comments at the SF Planning Commission, by year and recorded polarity")
    ax.legend(frameon=False, ncol=4, fontsize=8, loc="upper left")
    ax.set_xlim(1997.4, 2026.6)
    fig.savefig(FIG / "comments_by_year.png")
    plt.close(fig)


def fig_polarity_share(com):
    signed = com[com["sign"].isin(["+", "-"])]
    g = signed.groupby("year")["sign"].value_counts().unstack(fill_value=0)
    g = g[(g["+"] + g["-"]) >= 100]  # years with too few signed comments mislead
    share = g["-"] / (g["+"] + g["-"])
    n = g.sum(axis=1)
    fig, ax = plt.subplots(figsize=(8, 3))
    ax.plot(share.index, share.values, color=NEG, lw=2)
    ax.scatter(share.index, share.values, s=10 + 40 * n / n.max(), color=NEG, zorder=3)
    ax.axhline(0.5, color="grey", lw=0.8, ls="--")
    ax.set_ylabel("share of signed comments\nthat oppose")
    ax.set_ylim(0, 1)
    ax.set_title("Opposition share among stenographer-signed comments (point size ∝ volume)")
    fig.savefig(FIG / "polarity_share.png")
    plt.close(fig)


def fig_groups(com):
    keep = ["Neighborhood Association", "Project Team", "Housing Interest Groups",
            "Pro-Development Interest Groups", "Business Groups",
            "Social Interest Groups"]
    colors = {"Neighborhood Association": "#e6550d", "Project Team": "#969696",
              "Housing Interest Groups": "#756bb1",
              "Pro-Development Interest Groups": "#2b8cbe",
              "Business Groups": "#31a354", "Social Interest Groups": "#c51b8a"}
    g = (com[com["role_group"].isin(keep)]
         .groupby(["year", "role_group"]).size().unstack(fill_value=0)
         .rolling(3, center=True, min_periods=1).mean())
    fig, ax = plt.subplots(figsize=(8, 3.6))
    for col in keep:
        if col in g:
            ax.plot(g.index, g[col], lw=1.8, color=colors[col], label=col)
    ax.set_ylabel("comments per year (3-yr avg)")
    ax.set_title("Interest-group and project-team comments over time")
    ax.legend(frameon=False, fontsize=8, ncol=2)
    fig.savefig(FIG / "groups_over_time.png")
    plt.close(fig)


def fig_map(items):
    d = items.dropna(subset=["latitude", "longitude"])
    d = d[(d["latitude"].between(37.70, 37.84)) & (d["longitude"].between(-122.53, -122.35))]
    com_counts = None
    fig, ax = plt.subplots(figsize=(5.6, 5.6))
    era = pd.cut(pd.to_numeric(d["meeting_date"].astype(str).str[:4]),
                 [1997, 2007, 2017, 2027], labels=["1998–2007", "2008–2017", "2018–2026"])
    for lab, color in zip(["1998–2007", "2008–2017", "2018–2026"],
                          ["#fdae6b", "#e6550d", "#7f2704"]):
        sub = d[era == lab]
        ax.scatter(sub["longitude"], sub["latitude"], s=3, alpha=0.25,
                   color=color, label=f"{lab}  (n={len(sub):,})", linewidths=0)
    ax.set_aspect(1 / 0.79)  # approx cos(latitude)
    ax.set_xticks([]); ax.set_yticks([])
    ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(False)
    leg = ax.legend(frameon=False, fontsize=8, loc="lower left", markerscale=4)
    for lh in leg.legend_handles:
        lh.set_alpha(1)
    ax.set_title("Agenda items heard by the Commission, geocoded (n={:,})".format(len(d)))
    fig.savefig(FIG / "project_map.png")
    plt.close(fig)


def fig_top_commenters(com):
    named = com[com["name_clean"].notna() & (com["name_clean"] != "")
                & (com["is_staff"] != 1)]
    top = named["name_clean"].value_counts().head(15)[::-1]
    roles = {n: named.loc[named["name_clean"] == n, "role_group"].mode()
             for n in top.index}
    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.barh(top.index, top.values, color="#2b8cbe")
    for i, (n, v) in enumerate(top.items()):
        r = roles[n]
        lab = r.iloc[0] if len(r) else ""
        ax.text(v + 8, i, str(lab), va="center", fontsize=7, color="dimgrey")
    ax.set_xlabel("comments, 1998–2026")
    ax.set_title("Most frequent public commenters (non-staff)")
    ax.set_xlim(0, top.max() * 1.35)
    fig.savefig(FIG / "top_commenters.png")
    plt.close(fig)


if __name__ == "__main__":
    com, items = load()
    fig_comments_by_year(com)
    fig_polarity_share(com)
    fig_groups(com)
    fig_map(items)
    fig_top_commenters(com)
    print("wrote", len(list(FIG.glob("*.png"))), "figures to", FIG)
