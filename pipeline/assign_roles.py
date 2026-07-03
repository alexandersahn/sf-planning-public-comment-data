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
ORG_RULES = [
    (r"Staff ([Rr]eport|[Pp]resentation)|^Planning (Department )?[Ss]taff\b", "Planning Staff"),
    (r"([Ll]egislative )?([Aa]ide to |[Rr]epresenting |Office of )Sup|^Supervisor", "Supervisor's Office"),
    (r"^Mayor|MOHCD|City Attorney", "Mayor's Office"),
    (r"Community Benefit District", "Community Benefit District"),
    (r"Tenant|Housing Rights Committee", "Tenant Association"),
    (LAW_FIRMS, "Legal"),
    (r"(Residents|Resident's|Neighborhood|Neighbors|Homes|Dwellers|Community|"
     r"Improvement|Park|Hill|Valley|Promotion|Triangle|Residence|Hollow|"
     r"Residential) (Council|Association)", "Neighborhood Association"),
    (r"Bernal|Cow Hollow|North Beach|Twin Peaks|Telegraph Hill|Upper Noe|"
     r"Neighborhood Association|Potrero Booster", "Neighborhood Association"),
    (r"(Merchants?|Merchant's|Commercial|Development|Restaurant) Association|"
     r"Chamber of Commerce|Union Square Alliance", "Commercial Association"),
    (r"^(Church|Unitarian|St\.)|Christian", "Religious"),
    (r"TODCO|Mission Housing|MEDA|Bernal Heights Housing Corporation|"
     r"Chinatown Community Development Center", "Affordable Housing Developer"),
    (r"Local [0-9]+|[Uu]nion\b|[Cc]arpenter|[Bb]uilding [Tt]rade|Trades|"
     r"Electrical|Residential Builders", "Construction"),
    (r"SFHAC|Housing Action Coalition|YIMBY|Grow SF|Grow the Richmond|Density",
     "YIMBY"),
    (r"Anti-Displacement|Mission Agenda|PODER|^MAC\b|Mission Anti|Eviction|"
     r"Market Street for the Masses", "Anti-Displacement"),
    (r"^(Native|Asian|LGBTQ|Samoan|Chinese|Latino|Both Sides of the Conversation)|"
     r"Calle 24", "Race/Immigration/LGBTQ Groups"),
    (r"Young Community Developers|Tenderloin Housing Clinic|Vincent de Paul|"
     r"Self-Help for the Elderly|Mercy Housing|Sixth Street Agenda|"
     r"Nihonmachi Little Friends", "Social Services"),
    (r"Coalition for San Francisco Neighborhood|San Francisco Land Use Coalition|"
     r"Coalition for Adequate Review|SFRG|San Francisco Tomorrow|"
     r"San Francisco Citizens for Considered Development", "Slow Growth"),
    (r"SPUR", "SPUR"),
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
    "Chamber of Commerce": "Business Groups",
    "Commercial Association": "Business Groups",
    "Community Benefit District": "Business Groups",
    "Construction": "Business Groups",
    "Race/Immigration/LGBTQ Groups": "Social Interest Groups",
    "Religious": "Social Interest Groups",
    "Social Services": "Social Interest Groups",
    "SPUR": "Pro-Development Interest Groups",
    "YIMBY": "Pro-Development Interest Groups",
    "Mayor's Office": "Inter-Governmental",
    "Supervisor's Office": "Inter-Governmental",
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
    for pat, role in ORG_RULES:
        if (re.match(pat, text) if anchored else re.search(pat, text)):
            return role
    return None


def main():
    com = pd.read_csv(OUT / "comments.csv", low_memory=False,
                      keep_default_na=False, na_values=[""])
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

    def assign(row_idx):
        rt, org, cm = (fields[0].iat[row_idx], fields[1].iat[row_idx],
                       fields[2].iat[row_idx])
        nm = name_l.iat[row_idx]
        # 1. project-specific roles
        for f in (rt, cm):
            if DR_TEAM_RE.search(f):
                return "DR Team"
        for f in (rt, cm):
            if re.search(LAW_FIRMS, f):
                return "Legal"
            if PROJECT_TEAM_RE.search(f):
                return "Project Team"
        # 2. staff / commissioner
        if com["is_staff"].iat[row_idx]:
            return "Planning Staff"
        if com["is_commissioner"].iat[row_idx]:
            return "Commissioner"
        # 3. org-based classification (org column first, then title, then
        # comment text — the latter anchored at the start)
        for f, anch in ((org, False), (rt, False), (cm, True)):
            role = classify_org(f, anchored=anch)
            if role:
                return role
        # 4. registered neighborhood-group roster
        if nm in nhood_map:
            return classify_org(str(nhood_map[nm])) or "Neighborhood Association"
        # 5. author's name-level lookup
        if nm in lookup_role_map:
            return lookup_role_map[nm]
        return None

    com["role_long"] = [assign(i) for i in range(len(com))]

    # manual overrides (paper's corrections) take precedence
    manual = {k.lower(): v for k, v in MANUAL_ROLES.items()}
    override = name_l.map(manual)
    com.loc[override.notna(), "role_long"] = override[override.notna()]

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
        f.write(f"\nrole-implied signs added: {int(m.sum())}\n")
    print(open(VAL / "roles_report.txt").read())


if __name__ == "__main__":
    main()
