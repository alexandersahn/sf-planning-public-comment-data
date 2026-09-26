"""Identify staff, government, project-team, and interest-group speakers.

Improves on the published pipeline in two ways:
  1. Planning staff are identified from the minutes' own per-meeting
     "STAFF IN ATTENDANCE" rosters (era-correct, 1998-2026) rather than a
     static 2022 staff-directory snapshot (which is still used as a
     supplement). Commissioners are identified the same way.
  2. Organization classification runs on the dedicated `organization` /
     `role_title` columns first, then falls back to comment text.

Role taxonomy and rules are ported from the paper's
"3. clean_match_voterfile.R" (roles/roles2/roles_all), including the author's
manual name-level overrides, the registered neighborhood-group roster, and
the name-level lookup_role.csv.

Writes: data/processed/comments.csv (role_long, role_group, is_staff,
        is_commissioner columns), data/validation/roles_report.txt
"""

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from speakers import is_name_like  # noqa: E402
from rosters import curated_lookup, PROPAGATABLE_ROLES, YEAR_FLOOR  # noqa: E402

# A speaker's stated affiliation is carried to their other comments only
# within this many years either side of the hearings where they stated it.
# Names recur across three decades in this corpus and are not unique, so an
# open-ended window would merge distinct people who share a name.
ROSTER_WINDOW_YEARS = 4
# Minimum share of a speaker's stated labels that must agree before the modal
# role is treated as that person's affiliation.
ROSTER_MIN_AGREEMENT = 0.6

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "processed"
VAL = ROOT / "data" / "validation"
ORIG = ROOT / "replication_original" / "data"

LAW_FIRMS = (r"Reuben and Alter|Ruben and Alter|Sanger and Olson|Reuben and Junius|"
             r"Reuben, Junius & Rose|Coblentz, Patch, Duffy and Bass|"
             r"Steffel, Levitt and Weiss|Steefel, Levitt and Weiss|"
             r"Morrison and Forrester|Law Office")

# (regex, role_long) — applied to organization, role_title, then comment.
# Ported from the paper's comment- and org-based rules; order matters.
#
# Matching is case-insensitive (the minutes are inconsistent: "SF YIMBY",
# "SF Yimby", "yimby"), so every acronym alternative carries explicit \b
# guards — without them "MEDA" matches "Alameda" and "SPUR" matches
# "spurred" once case stops constraining them.
ORG_RULES = [
    (r"Staff ([Rr]eport|[Pp]resentation)|^Planning (Department )?[Ss]taff\b", "Planning Staff"),
    (r"([Ll]egislative )?([Aa]ide to |[Rr]epresenting |Office of )Sup|^Supervisor", "Supervisor's Office"),
    (r"^Mayor|\bMOHCD\b|City Attorney", "Mayor's Office"),
    # City departments other than Planning. Kept below the Mayor's Office rule
    # so MOHCD and the City Attorney stay where the paper put them.
    (r"\b(SFMTA|SFPUC|SFUSD|SFFD|SFPD|OEWD|DPW|DPH|DBI|CAO|MOH|MTA|PUC)\b|"
     r"Port of San Francisco|\bSF Port\b|Rec(reation)? and Park|"
     r"Department of (Public Works|Public Health|Building Inspection)|"
     r"Deputy C\.?A\.?\b", "City Agency"),
    (r"Community Benefit District|\bYBCBD\b|Yerba Buena CBD", "Community Benefit District"),
    (r"Tenant|Housing Rights Committee", "Tenant Association"),
    (LAW_FIRMS, "Legal"),
    (r"(Residents|Resident's|Neighborhood|Neighbors|Homes|Dwellers|Community|"
     r"Improvement|Park|Hill|Valley|Promotion|Triangle|Residence|Hollow|"
     r"Residential) (Council|Association)", "Neighborhood Association"),
    (r"Bernal|Cow Hollow|North Beach|Twin Peaks|Telegraph Hill|Upper Noe|"
     r"Neighborhood Association|Potrero Booster|\bTHD\b|All Things Bayview|"
     r"\bATB\b", "Neighborhood Association"),
    (r"(Merchants?|Merchant's|Commercial|Development|Restaurant) Association|"
     r"Chamber of Commerce|Union Square Alliance|Hotel Council|\bSF Travel\b|"
     r"Bay Area Council|Small Business Forward", "Commercial Association"),
    (r"^(Church|Unitarian|St\.)|Christian", "Religious"),
    (r"TODCO|Mission Housing|\bMEDA\b|Bernal Heights Housing Corporation|"
     r"Chinatown Community Development Center|\bCCDC\b|\bTNDC\b|\bSFHDC\b|"
     r"Tenderloin Neighborhood Development", "Affordable Housing Developer"),
    # Organized labor that is not the building trades; kept above the
    # construction rule, which would otherwise swallow it on "union".
    (r"Teamsters|\bSEIU\b|\bILWU\b|UNITE HERE|Labor Council", "Labor"),
    (r"Local [0-9]+|[Uu]nion\b|[Cc]arpenter|[Bb]uilding [Tt]rade|Trades|"
     r"Electrical|Residential Builders", "Construction"),
    # The paper lumped the YIMBY movement together with the Housing Action
    # Coalition and GrowSF. They are separate organizations with different
    # founding dates and different memberships, and by volume this bucket was
    # mostly HAC, so they are now split.
    (r"\bYIMBY\b|\bSFBARF\b|\bBARF\b|Renters'? Federation|Grow ?SF|"
     r"Grow the Richmond", "YIMBY"),
    (r"Housing Action Coalition|\bSFHAC\b|\bHAC\b", "Pro-Housing Advocacy"),
    (r"San Francisco Heritage|\bSF Heritage\b|Victorian Alliance",
     "Historic Preservation"),
    (r"Anti-Displacement|Mission Agenda|PODER|^MAC\b|Mission Anti|Eviction|"
     r"Market Street for the Masses|\bSOMCAN\b|"
     r"South of Market Community Action", "Anti-Displacement"),
    (r"^(Native|Asian|LGBTQ|Samoan|Chinese|Latino|Both Sides of the Conversation)|"
     r"Calle 24|SOMA Pilipinas", "Race/Immigration/LGBTQ Groups"),
    (r"Young Community Developers|Tenderloin Housing Clinic|Vincent de Paul|"
     r"Self-Help for the Elderly|Mercy Housing|Sixth Street Agenda|"
     r"Nihonmachi Little Friends", "Social Services"),
    (r"Coalition for San Francisco Neighborhood|San Francisco Land Use Coalition|"
     r"Coalition for Adequate Review|\bSFRG\b|San Francisco Tomorrow|"
     r"\bNUSF\b|Neighborhoods United|"
     r"San Francisco Citizens for Considered Development", "Slow Growth"),
    (r"\bSPUR\b", "SPUR"),
]

DR_TEAM_RE = re.compile(
    r"^([Rr]epresenting |Attorney for (the )?)?(1st |2nd |3rd |[4-9]th |[Ff]irst )?"
    r"([Dd]\.?[Rr]\.?\s?[Rr]equestor|[Rr]equestor|Discretionary [Rr]eview|DR[0-9]?\b)")
PROJECT_TEAM_RE = re.compile(
    r"^([Aa]ttorney for |[Oo]n behalf of |[Rr]epresenting )?(the )?"
    r"([Pp]roject |[Pp]roperty |[Bb]uilding )?"
    r"([Ss]ponsor|[Oo]wner|[Aa]rchitect|[Dd]eveloper)\b"
    r"|^[Pp]roject ([Ss]ponsor|[Tt]eam|[Aa]rchitect)")

ROLE_GROUP = {
    "Affordable Housing Developer": "Housing Interest Groups",
    "Anti-Development": "Housing Interest Groups",
    "Slow Growth": "Housing Interest Groups",
    "Anti-Displacement": "Housing Interest Groups",
    "Tenant Association": "Housing Interest Groups",
    "Historic Preservation": "Housing Interest Groups",
    "Chamber of Commerce": "Business Groups",
    "Commercial Association": "Business Groups",
    "Community Benefit District": "Business Groups",
    "Construction": "Business Groups",
    "Labor": "Business Groups",
    "Race/Immigration/LGBTQ Groups": "Social Interest Groups",
    "Religious": "Social Interest Groups",
    "Social Services": "Social Interest Groups",
    "SPUR": "Pro-Development Interest Groups",
    "YIMBY": "Pro-Development Interest Groups",
    "Pro-Housing Advocacy": "Pro-Development Interest Groups",
    "Mayor's Office": "Inter-Governmental",
    "Supervisor's Office": "Inter-Governmental",
    "City Agency": "Inter-Governmental",
    "Commissioner": "Inter-Governmental",
    "Project Team": "Project Team",
    "Legal": "Project Team",
}

# the paper's manual name-level corrections (roles_all case_when)
MANUAL_ROLES = {
    "Judson Stuart True": "Supervisor's Office",
    "Kanishka Karunaratne": "Supervisor's Office",
    "Mike Williams": "Commercial Association",
    "Patricia Vaughey": "Neighborhood Association",
    "Anastasia Yovanopoulos": "Neighborhood Association",
    "Sue Hestor": "Neighborhood Association",
    "Elizabeth Gordon": "Planning Staff",
    "Erick Arguello": "Race/Immigration/LGBTQ Groups",
    "Kanishka Burns": "Planning Staff",
    "Daniel Yadegar": "Supervisor's Office",
    "Danny Yadegar": "Supervisor's Office",
    "David Wayne Mcguire": "Anti-Displacement",
    "Ian Lewis": "Construction",
    "Joan Girardot": "Slow Growth",
    "Judith Berkowitz": "Slow Growth",
    "Marlayne A Morgan": "Neighborhood Association",
    "Dean Preston": "Supervisor's Office",
    "Doug Shoemaker": "Social Services",
    "Rose L Wilson": "Slow Growth",
    "Sarah Jones": "Planning Staff",
    "Jim Hewitt": "Construction",
    "James Hewitt": "Construction",
    "Marlayne Morgan": "Social Services",
    "Michael McGuire": "Social Services",
    "Rose Wilson": "Slow Growth",
}

DESCRIPTOR_RE = re.compile(r"\s*[–—-]\s*[^,;]*$")


def roster_names(cell):
    """Split a 'STAFF IN ATTENDANCE' string into clean person names."""
    if not isinstance(cell, str) or not cell.strip():
        return []
    out = []
    for part in re.split(r"[,;]| and ", cell):
        p = DESCRIPTOR_RE.sub("", part).strip(" .")
        p = re.sub(r"\s+", " ", p)
        if is_name_like(p) and 2 <= len(p.split()) <= 4:
            out.append(p.title() if p.isupper() else p)
    return out


def classify_org(text, anchored=False):
    """Classify a field against ORG_RULES.

    anchored=True (used for free comment text) requires the match at the
    start of the text, mirroring the paper's '^'-anchored comment rules —
    otherwise loose tokens like 'Density' hit mid-sentence words.
    """
    if not isinstance(text, str) or not text.strip():
        return None
    flags = re.IGNORECASE
    for pat, role in ORG_RULES:
        if (re.match(pat, text, flags) if anchored
                else re.search(pat, text, flags)):
            return role
    return None


def build_derived_roster(com, name_l, years, staff_all):
    """Infer each speaker's standing affiliation from their own testimony.

    Evidence is restricted to comments where the speaker stated an
    affiliation (`stated_*` sources). Curated, lookup and neighborhood-roster
    labels are already person-level, so feeding them back in would only
    re-derive them; case roles (Project Team, DR Team, Legal) describe a
    relationship to one item and are excluded by PROPAGATABLE_ROLES.

    Guards, in order of how much they matter:
      * two or more name tokens — 4,009 speakers are recorded by a single
        token ("Kiefer", "Gloria") and those collide constantly;
      * the modal role must hold at least ROSTER_MIN_AGREEMENT of the
        speaker's stated labels, so people who have represented two
        different kinds of organization are left to the comment-level rules;
      * a tenure window of ROSTER_WINDOW_YEARS either side of the years they
        actually stated it;
      * never a name on the Planning staff roster.

    Returns (lookup dict, rows for the audit file).
    """
    ev = pd.DataFrame({
        "nm": name_l,
        "year": years,
        "role": com["role_long"],
        "src": com["role_source"],
    })
    ev = ev[ev["src"].isin(["stated_org", "stated_role_title", "stated_comment"])
            & ev["role"].isin(PROPAGATABLE_ROLES)
            & ev["nm"].str.split().str.len().ge(2)
            & ~ev["nm"].isin(staff_all)
            & ev["year"].notna()]

    derived, rows = {}, []
    for nm, g in ev.groupby("nm"):
        counts = g["role"].value_counts()
        role, n = counts.index[0], int(counts.iloc[0])
        agreement = n / len(g)
        lo = int(g["year"].min()) - ROSTER_WINDOW_YEARS
        hi = int(g["year"].max()) + ROSTER_WINDOW_YEARS
        keep = agreement >= ROSTER_MIN_AGREEMENT
        rows.append({"name": nm, "role_long": role, "n_stated": len(g),
                     "n_modal": n, "agreement": round(agreement, 3),
                     "year_lo": lo, "year_hi": hi,
                     "distinct_roles": int(counts.size), "used": int(keep)})
        if keep:
            derived[nm] = {"role": role, "lo": lo, "hi": hi}
    return derived, rows


ROLE_ONLY = re.compile(
    r"^\s*(co-)?(project |property |building |discretionary review )?"
    r"(sponsor|architect|owner|developer|team|representative|requestor|"
    r"applicant|consultant|engineer|planner|contractor|speaker|staff)s?"
    r"('s)?\s*(representative)?\s*$", re.I)
ROLE_SUFFIX = re.compile(
    r"\s*[-–—,]+\s*(co-)?(project |property |building |discretionary review )?"
    r"(sponsor|architect|owner|developer|requestor|applicant)s?\s*$", re.I)


def demote_role_labels(com):
    """Treat a bare role label as anonymous, because that is what it is.

    157 speakers are recorded under a role rather than a name — "Project
    Sponsor", "Requestor", "Project Architect" — and is_anonymous was 0 on
    every one, so they read as named individuals and accumulated across
    hearings as if they were one person. They are as anonymous as "Speaker".
    Where a name is attached ("Jerry -- Project Sponsor") the name is kept
    and the role moves to role_title.

    Returns the number of records demoted.
    """
    raw = com["name_clean"].fillna("")
    stripped = raw.str.replace(ROLE_SUFFIX, "", regex=True).str.strip()
    is_role = stripped.str.match(ROLE_ONLY) | raw.str.match(ROLE_ONLY)

    # "Jerry -- Project Sponsor": keep Jerry, move the role to role_title
    recovered = stripped.ne(raw) & ~is_role & stripped.ne("")
    suffix = [r[len(t):].strip(" -–—,") for r, t in zip(raw[recovered],
                                                        stripped[recovered])]
    fill = recovered & com["role_title"].isna()
    com.loc[fill, "role_title"] = pd.Series(suffix, index=raw[recovered].index)[fill[recovered]]
    com.loc[recovered, "name_clean"] = stripped[recovered]

    com.loc[is_role & com["role_title"].isna(), "role_title"] = raw[is_role].str.strip()
    com.loc[is_role, "is_anonymous"] = 1
    com.loc[is_role, "name_clean"] = pd.NA
    return int(is_role.sum()), int(recovered.sum())


def main():
    com = pd.read_csv(OUT / "comments.csv", low_memory=False,
                      keep_default_na=False, na_values=[""])
    n_role, n_recovered = demote_role_labels(com)
    meetings = pd.read_csv(OUT / "meetings.csv")

    # ------------------------------------------------------------ rosters
    staff_by_meeting = {}
    staff_all = set()
    comm_by_meeting = {}
    for _, m in meetings.iterrows():
        names = roster_names(m.get("staff_in_attendance"))
        staff_by_meeting.setdefault(m["meeting_date"], set()).update(
            n.lower() for n in names)
        staff_all.update(n.lower() for n in names)
        comm_by_meeting.setdefault(m["meeting_date"], set()).update(
            n.lower() for n in roster_names(m.get("commissioners_present")))

    # supplement: 2022 staff directory snapshot from the replication archive
    try:
        staff_csv = pd.read_csv(ORIG / "lookup_planning_staff.csv",
                                encoding="latin1", on_bad_lines="skip")
        staff_all.update(str(n).strip().lower() for n in staff_csv["name"].dropna()
                         if is_name_like(str(n).strip()))
    except Exception as e:  # noqa: BLE001
        print("staff lookup skipped:", e)

    # Wayback staff panel: tenure windows per staff member (2011-2026),
    # matched with a +/- 1 year margin around first/last directory sighting
    tenure_windows = {}
    tenure_path = OUT / "staff_tenure.csv"
    if tenure_path.exists():
        tn = pd.read_csv(tenure_path, parse_dates=["first_seen", "last_seen"])
        margin = pd.Timedelta(days=365)
        for _, r in tn.iterrows():
            tenure_windows[str(r["name"]).strip().lower()] = (
                r["first_seen"] - margin, r["last_seen"] + margin)

    # registered neighborhood-group roster (name -> organization)
    nhood = pd.read_excel(ORIG / "lookup_nhood_groups.xlsx")
    nhood.columns = [c.strip() for c in nhood.columns]
    nhood = nhood[~nhood["ORGANIZATION"].isin(["Board of Supervisors", "-"])]
    nhood["full"] = (nhood["FIRST"].fillna("").str.strip() + " "
                     + nhood["LAST"].fillna("").str.strip()).str.strip().str.title()
    nhood_map = {r["full"].lower(): r["ORGANIZATION"]
                 for _, r in nhood.iterrows() if len(r["full"].split()) >= 2}

    # name-level roles from the author's lookup
    lr = pd.read_csv(ORIG / "lookup_role.csv", encoding="latin1")
    lookup_role_map = {str(n).strip().lower(): r for n, r in
                       zip(lr["name_clean"], lr["role"]) if pd.notna(r)}

    # ------------------------------------------------------------ assignment
    name_l = com["name_clean"].fillna("").str.strip().str.lower()
    com["is_staff"] = 0
    com["is_commissioner"] = 0
    com["role_long"] = pd.NA

    fields = [com["role_title"].fillna(""), com["organization"].fillna(""),
              com["comment"].fillna("").str.slice(0, 120)]

    same_meeting_staff = [
        nm != "" and nm in staff_by_meeting.get(md, set())
        for nm, md in zip(name_l, com["meeting_date"])]
    corpus_staff = name_l.isin(staff_all) & (name_l != "")
    mdates = pd.to_datetime(com["meeting_date"], errors="coerce")
    panel_staff = [
        nm in tenure_windows and pd.notna(md)
        and tenure_windows[nm][0] <= md <= tenure_windows[nm][1]
        for nm, md in zip(name_l, mdates)]
    com["is_staff"] = (pd.Series(same_meeting_staff, index=com.index)
                       | corpus_staff
                       | pd.Series(panel_staff, index=com.index)).astype(int)
    # commissioners matched only within their own meeting to avoid flagging
    # unrelated citizens who share a commissioner's name
    com["is_commissioner"] = [
        int(nm != "" and nm in comm_by_meeting.get(md, set()))
        for nm, md in zip(name_l, com["meeting_date"])]

    curated = curated_lookup()
    year_floor = {k.lower(): v for k, v in YEAR_FLOOR.items()}
    years = mdates.dt.year

    def assign(row_idx):
        """Return (role_long, role_source) for one comment."""
        rt, org, cm = (fields[0].iat[row_idx], fields[1].iat[row_idx],
                       fields[2].iat[row_idx])
        nm = name_l.iat[row_idx]
        # 1. case-specific roles: someone's relationship to *this* item
        for f in (rt, cm):
            if DR_TEAM_RE.search(f):
                return "DR Team", "case_role"
        for f in (rt, cm):
            if re.search(LAW_FIRMS, f):
                return "Legal", "case_role"
            if PROJECT_TEAM_RE.search(f):
                return "Project Team", "case_role"
        # 2. staff / commissioner, from the meeting's own attendance roster
        if com["is_staff"].iat[row_idx]:
            return "Planning Staff", "attendance"
        if com["is_commissioner"].iat[row_idx]:
            return "Commissioner", "attendance"
        # 3. curated person-level roster (hand-collected membership)
        if nm in curated:
            role, canonical = curated[nm]
            floor = year_floor.get(canonical.lower())
            yr = years.iat[row_idx]
            if floor is None or (pd.notna(yr) and yr >= floor):
                return role, "roster_curated"
        # 4. affiliation stated in this comment (org column first, then
        # title, then comment text — the latter anchored at the start)
        for f, anch, src in ((org, False, "stated_org"),
                             (rt, False, "stated_role_title"),
                             (cm, True, "stated_comment")):
            role = classify_org(f, anchored=anch)
            if role:
                return role, src
        # 5. registered neighborhood-group roster
        if nm in nhood_map:
            return (classify_org(str(nhood_map[nm])) or "Neighborhood Association",
                    "nhood_roster")
        # 6. author's name-level lookup
        if nm in lookup_role_map:
            return lookup_role_map[nm], "lookup_role"
        return None, None

    assigned = [assign(i) for i in range(len(com))]
    com["role_long"] = [a[0] for a in assigned]
    com["role_source"] = [a[1] for a in assigned]

    # ------------------------------------------------- derived person roster
    # Most speakers name their organization in only some of their
    # appearances. Build a roster from the comments where they did, and carry
    # it to the ones where they did not.
    derived, roster_rows = build_derived_roster(com, name_l, years, staff_all)
    fill = com["role_long"].isna()
    filled_role, filled_src = [], []
    for i in range(len(com)):
        if not fill.iat[i]:
            filled_role.append(com["role_long"].iat[i])
            filled_src.append(com["role_source"].iat[i])
            continue
        ent = derived.get(name_l.iat[i])
        yr = years.iat[i]
        if ent and pd.notna(yr) and ent["lo"] <= yr <= ent["hi"]:
            filled_role.append(ent["role"])
            filled_src.append("roster_derived")
        else:
            filled_role.append(pd.NA)
            filled_src.append(com["role_source"].iat[i])
    com["role_long"] = filled_role
    com["role_source"] = filled_src

    pd.DataFrame(roster_rows).to_csv(VAL / "person_roster.csv", index=False)

    # manual overrides (paper's corrections) take precedence
    manual = {k.lower(): v for k, v in MANUAL_ROLES.items()}
    override = name_l.map(manual)
    com.loc[override.notna(), "role_long"] = override[override.notna()]
    com.loc[override.notna(), "role_source"] = "manual"

    com["role_group"] = com["role_long"].map(
        lambda r: ROLE_GROUP.get(r, r) if pd.notna(r) else pd.NA)

    # role-implied polarity where the stenographer gave none (paper rule)
    if "sign_imputed" not in com.columns:
        com["sign_imputed"] = pd.NA
    if "sign_source" not in com.columns:
        com["sign_source"] = pd.NA
    role_sign = com["role_long"].map({"DR Team": "-", "Project Team": "+",
                                      "Legal": "+"})
    m = com["sign"].isna() & role_sign.notna()
    com.loc[m, "sign_imputed"] = role_sign[m]
    com.loc[m, "sign_source"] = "role"
    com.loc[com["sign"].notna(), "sign_source"] = "stenographer"

    com.to_csv(OUT / "comments.csv", index=False)

    with open(VAL / "roles_report.txt", "w") as f:
        f.write(f"comment records: {len(com)}\n")
        f.write(f"staff roster (from minutes attendance): "
                f"{len(staff_all)} unique names\n")
        f.write(f"records flagged is_staff: {int(com['is_staff'].sum())}\n")
        f.write(f"records flagged is_commissioner: {int(com['is_commissioner'].sum())}\n")
        f.write(f"records with role_long: {int(com['role_long'].notna().sum())}\n\n")
        f.write("role_long distribution:\n")
        for k, v in com["role_long"].value_counts().items():
            f.write(f"  {k}: {v}\n")
        f.write("\nrole_group distribution:\n")
        for k, v in com["role_group"].value_counts().items():
            f.write(f"  {k}: {v}\n")
        f.write("\nrole_source distribution:\n")
        for k, v in com["role_source"].value_counts().items():
            f.write(f"  {k}: {v}\n")

        roster = pd.read_csv(VAL / "person_roster.csv")
        f.write(f"\nderived person roster: {len(roster)} speakers with a "
                f"stated affiliation, {int(roster['used'].sum())} used "
                f"(rest failed the {ROSTER_MIN_AGREEMENT:.0%} agreement test)\n")
        f.write(f"comments labeled by the derived roster: "
                f"{int((com['role_source'] == 'roster_derived').sum())}\n")
        f.write(f"comments labeled by the curated roster: "
                f"{int((com['role_source'] == 'roster_curated').sum())}\n")

        pubmask = (com["is_staff"] != 1) & (com["is_commissioner"] != 1)
        named = pubmask & com["name_clean"].notna() & (com["is_anonymous"] != 1)
        f.write(f"\nnamed public comments: {int(named.sum())}\n")
        f.write(f"  with a role: {int((named & com['role_long'].notna()).sum())} "
                f"({(com.loc[named, 'role_long'].notna().mean()):.1%})\n")
        f.write(f"\nrole-implied signs added: {int(m.sum())}\n")
    print(open(VAL / "roles_report.txt").read())


if __name__ == "__main__":
    main()
