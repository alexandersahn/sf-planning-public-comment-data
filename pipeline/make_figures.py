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
    # figures describe *public* comment: exclude staff and commissioners
    com = com[(com["is_staff"] != 1) & (com["is_commissioner"] != 1)]
    items = pd.read_csv(PUB / "items.csv.gz", low_memory=False)
    return com, items


POS_IMP, NEG_IMP, NEU_IMP = "#a8cee3", "#fcae91", "#cccccc"


def fig_comments_by_year(com):
    cat = com["sign"].copy()
    imputed = com["sign"].isna() & com["sign_imputed"].notna()
    cat[imputed] = com.loc[imputed, "sign_imputed"] + "imp"
    g = com.groupby(["year", cat.fillna("none")]).size().unstack(fill_value=0)
    order = [("+", POS, "support (+)"), ("+imp", POS_IMP, "support (imputed)"),
             ("-", NEG, "oppose (−)"), ("-imp", NEG_IMP, "oppose (imputed)"),
             ("=", NEU, "neutral (=)"), ("=imp", NEU_IMP, "neutral (imputed)"),
             ("none", GREY, "no sign, not imputable")]
    fig, ax = plt.subplots(figsize=(8, 3.6))
    bottom = None
    for key, color, label in order:
        vals = g[key] if key in g else g.iloc[:, 0] * 0
        ax.bar(g.index, vals, bottom=bottom, color=color, label=label, width=0.8)
        bottom = vals if bottom is None else bottom + vals
    ax.set_ylabel("public comments")
    ax.set_title("Public comments by year and polarity (staff testimony excluded)")
    ax.legend(frameon=False, ncol=4, fontsize=7, loc="upper left")
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
    ax.set_title("Opposition share among stenographer-signed public comments, staff excluded (point size ∝ volume)")
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


def _draw_neighborhoods(ax):
    """Light neighborhood outlines from DataSF Analysis Neighborhoods."""
    import json
    gj_path = ROOT / "data" / "raw" / "neighborhoods.geojson"
    if not gj_path.exists():
        import requests
        r = requests.get(
            "https://data.sfgov.org/resource/ajp5-b2md.geojson",
            params={"$limit": 120}, timeout=60)
        if r.ok:
            gj_path.write_bytes(r.content)
        else:
            return
    gj = json.load(open(gj_path))
    for feat in gj["features"]:
        geom = feat.get("geometry")
        if not geom or not geom.get("type"):
            continue
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" \
            else [geom["coordinates"]]
        for poly in polys:
            ring = poly[0]
            xs = [p[0] for p in ring]
            ys = [p[1] for p in ring]
            ax.fill(xs, ys, color="#f0efeb", zorder=0)
            ax.plot(xs, ys, color="#d4d3cd", lw=0.7, zorder=1)


def fig_map(items, com):
    # com is already staff-excluded by load()
    n_com = (com.groupby("item_id").size().rename("n_comments"))
    d = items.dropna(subset=["latitude", "longitude"]).merge(
        n_com, left_on="item_id", right_index=True, how="left")
    d["n_comments"] = d["n_comments"].fillna(0)
    d = d[(d["latitude"].between(37.70, 37.84))
          & (d["longitude"].between(-122.53, -122.35))]

    fig, ax = plt.subplots(figsize=(6.4, 6.4))
    ax.set_facecolor("white")
    _draw_neighborhoods(ax)

    quiet = d[d["n_comments"] == 0]
    ax.scatter(quiet["longitude"], quiet["latitude"], s=2.5, alpha=0.35,
               color="#b5b5b0", linewidths=0, zorder=2,
               label=f"no public comment  ({len(quiet):,})")
    bins = [(1, 4, "#fdbe85", 5, .5), (5, 19, "#e6550d", 10, .6),
            (20, 10**9, "#7f2704", 24, .8)]
    for lo, hi, color, size, alpha in bins:
        sub = d[d["n_comments"].between(lo, hi)]
        lab = f"{lo}+ comments" if hi > 10**8 else f"{lo}–{hi} comments"
        ax.scatter(sub["longitude"], sub["latitude"], s=size, alpha=alpha,
                   color=color, linewidths=0, zorder=3,
                   label=f"{lab}  ({len(sub):,})")
    ax.set_aspect(1 / 0.79)  # approx cos(latitude)
    ax.set_xlim(-122.525, -122.35)
    ax.set_ylim(37.703, 37.837)
    ax.set_xticks([]); ax.set_yticks([])
    ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(False)
    leg = ax.legend(frameon=False, fontsize=8, loc="lower left",
                    markerscale=2.2, title="agenda items, 1998–2026",
                    title_fontsize=8, alignment="left")
    for lh in leg.legend_handles:
        lh.set_alpha(1)
    ax.set_title("Where the projects are — and where the comments go",
                 fontsize=11)
    fig.savefig(FIG / "project_map.png")
    plt.close(fig)


if __name__ == "__main__":
    com, items = load()
    fig_comments_by_year(com)
    fig_polarity_share(com)
    fig_groups(com)
    fig_map(items, com)
    (FIG / "top_commenters.png").unlink(missing_ok=True)
    print("wrote", len(list(FIG.glob("*.png"))), "figures to", FIG)
