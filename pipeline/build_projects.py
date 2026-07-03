"""Classify agenda items (recommendation/action outcomes, record types) and
join DataSF Planning Department project records.

Reads  data/processed/items.csv, data/raw/datasf_projects.csv,
       data/raw/parcel_centroids.csv
Writes data/processed/items.csv (classification columns added)
       data/validation/projects_report.txt
"""

import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"
VAL = ROOT / "data" / "validation"


# ---------------------------------------------------------------- categories

def action_cat(s):
    """Port of the paper's action.cat() classifier."""
    if pd.isna(s) or not str(s).strip():
        return ""
    x = str(s)

    def has(p):
        return re.search(p, x, re.IGNORECASE) is not None

    if has(r"disapprov|deny|denied"):
        return "disapprove"
    if has(r"approv|grant"):
        return "approve"
    if has(r"withdraw"):
        return "withdraw"
    if has(r"pending"):
        return "pending"
    if has(r"negative declaration|mitigated negative|pmnd"):
        return "uphold pmnd"
    if has(r"certif"):
        return "certify eir"
    if has(r"adopt") and has(r"california environmental quality act|ceqa"):
        return "adopt ceqa findings"
    if has(r"adopt") and has(r"shadow"):
        return "adopt shadow study"
    if has(r"adopt"):
        return "adopt resolution"
    if has(r"initiate"):
        return "initiated"
    if has(r"continu"):
        return "continuance"
    if has(r"no action|informational|public comment|review.* comment|none"):
        return "no action"
    if has(r"closed"):
        return "with za"
    return ""


APPROVE_SET = {"adopt resolution", "adopt ceqa findings", "adopt shadow study",
               "approve", "certify eir", "uphold pmnd", "initiated"}


def dr_flag(s):
    if pd.isna(s) or not str(s).strip():
        return ""
    x = str(s)
    dr = re.search(r"discretionary| dr |dr$| d\.r\.| dr[.,;:)]", x, re.IGNORECASE)
    if not dr:
        return ""
    neg = re.search(r"do not|did not|^no | no |not take", x, re.IGNORECASE)
    return "no dr" if neg else "dr"


def conditions_flag(s):
    if pd.isna(s) or not str(s).strip():
        return np.nan
    return int(bool(re.search(r"condition|modif|amend|revise", str(s), re.IGNORECASE)))


def final_cat(clean, dr, cond):
    if clean in ("continuance", "pending"):
        return "continuance"
    if clean in ("no action", "with za"):
        return "no action"
    if dr == "dr" or (cond == 1 and clean in APPROVE_SET):
        return "approve with conditions"
    if (dr == "no dr" and cond == 0) or clean in APPROVE_SET:
        return "approve"
    if clean == "disapprove":
        return "disapprove"
    if clean == "withdraw":
        return "withdraw"
    return ""


NUM_MAP = {"continuance": 0, "no action": 0, "disapprove": -1, "withdraw": -1,
           "approve with conditions": 1, "approve": 2, "": np.nan}

# new-style record ids end in a type code; old-style single letters map to types
OLD_SUFFIX = {"C": "CUA", "D": "DRM", "E": "ENV", "T": "PCA", "Z": "MAP",
              "V": "VAR", "A": "COA", "Q": "CND", "B": "OFA", "L": "LND",
              "X": "DPA", "U": "PPA", "M": "GPA", "P": "CTZ", "K": "SHD",
              "I": "INF"}
NEW_TYPES = ["CUA", "DRP", "DRM", "ENV", "ENX", "PCA", "MAP", "VAR", "COA",
             "CND", "OFA", "LND", "DNX", "DPA", "PPA", "GPA", "CTZ", "SHD",
             "INF", "CWP", "PRJ", "APL", "PPS", "OTH", "AHB", "SHD", "CRV",
             "PTA", "IMP", "TDM", "BOS", "PHA", "ELG", "SB9"]


def record_type(rid):
    if not rid or pd.isna(rid):
        return ""
    rid = str(rid).strip()
    m = re.search(r"[.-]\d+([A-Z!]+)$", rid)
    if not m:
        return ""
    suf = m.group(1).replace("!", "")
    if not suf:
        return ""
    for t in sorted(NEW_TYPES, key=len, reverse=True):
        if suf.endswith(t):
            return t
    # old-style: possibly multiple letters like "DD", "AC", "CE" — first letter wins
    return OLD_SUFFIX.get(suf[-1], OLD_SUFFIX.get(suf[0], ""))


def id_parent(rid):
    """Normalize a record id to its parent project id (strip type letters)."""
    if not rid or pd.isna(rid):
        return ""
    base = re.sub(r"[A-Za-z!]+$", "", str(rid).strip())
    base = re.sub(r"-\d+$", "", base) if base.count("-") > 1 else base
    if re.match(r"^9\d\.", base):
        base = "19" + base
    return base


def section_group(s):
    if pd.isna(s):
        return ""
    if re.search(r"COMMISSION|DEPARTMENT|DIRECTOR", s, re.IGNORECASE):
        return "Administrative"
    if re.search(r"DISCRETIONARY", s, re.IGNORECASE):
        return "Discretionary Review"
    if re.search(r"CONTINU", s, re.IGNORECASE):
        return "Items Proposed for Continuance"
    if re.search(r"GENERAL", s, re.IGNORECASE):
        return "General Public Comment"
    if re.search(r"PUBLIC", s, re.IGNORECASE):
        return "Public Comment"
    if re.search(r"REGULAR", s, re.IGNORECASE):
        return "Regular Calendar"
    if re.search(r"CONSENT", s, re.IGNORECASE):
        return "Consent Calendar"
    if re.search(r"FINDINGS", s, re.IGNORECASE):
        return "Findings"
    if re.search(r"CLOSED", s, re.IGNORECASE):
        return "Closed Session"
    return "Other"


SUFFIX_MAP = {"BL": "BLVD", "BOULEVARD": "BLVD", "AV": "AVE", "AVENUE": "AVE",
              "STREET": "ST", "DRIVE": "DR", "COURT": "CT", "PLACE": "PL",
              "TERRACE": "TER", "TE": "TER", "WY": "WAY", "HY": "HWY",
              "HIGHWAY": "HWY", "ROAD": "RD", "LANE": "LN", "CIRCLE": "CIR",
              "ALLEY": "ALY", "SQUARE": "SQ", "PLAZA": "PLZ"}
UNIT_TOKEN = re.compile(r"^(\d{2,4}[A-Z]{0,2}|[A-Z]{1,2}-?\d+|#\S*|UNIT|APT)$")


SPELLED_ORD = {"FIRST": "01ST", "SECOND": "02ND", "THIRD": "03RD",
               "FOURTH": "04TH", "FIFTH": "05TH", "SIXTH": "06TH",
               "SEVENTH": "07TH", "EIGHTH": "08TH", "NINTH": "09TH",
               "TENTH": "10TH"}


def norm_address(a):
    """Normalize an address to 'NUM NAME SUFFIX' for joining across sources."""
    if a is None or (isinstance(a, float) and pd.isna(a)) or not str(a).strip():
        return ""
    s = str(a).upper().split(",")[0]
    s = re.sub(r"\s+\d{5}(-\d{4})?$", "", s)
    toks = re.sub(r"\s+", " ", s).strip().split(" ")
    # street-number ranges: "2743 - 2761 GEARY" or "2743-2761 GEARY" -> 2743
    if len(toks) >= 3 and toks[1] == "-":
        toks = [toks[0]] + toks[3:]
    if toks:
        toks[0] = re.sub(r"^(\d+)[-–]\d+[A-Z]?$", r"\1", toks[0])
    # drop trailing unit designators (e.g. "190 07TH ST 0001", "370 DE HARO ST TA-1")
    while len(toks) > 3 and UNIT_TOKEN.match(toks[-1]):
        toks.pop()
    # drop single-letter unit tokens after the street number ("1269 B LOMBARD ST")
    toks = [toks[0]] + [t for t in toks[1:] if len(t) > 1 or t.isdigit()] if toks else toks
    if toks:
        toks[-1] = SUFFIX_MAP.get(toks[-1], toks[-1])
    # EAS zero-pads ordinal streets: "5TH AVE" -> "05TH AVE"; "THIRD ST" -> "03RD ST"
    toks = [re.sub(r"^(\d)(ST|ND|RD|TH)$", r"0\1\2", t) for t in toks]
    toks = [SPELLED_ORD.get(t, t) for t in toks]
    return " ".join(toks)


def street_number_lookup(apts_n):
    """Index EAS points by street for nearest-number fallback."""
    idx = {}
    for key, row in apts_n.iterrows():
        m = re.match(r"^(\d+) (.+)$", str(key))
        if not m:
            continue
        idx.setdefault(m.group(2), []).append(
            (int(m.group(1)), row["latitude"], row["longitude"]))
    return {st: sorted(v) for st, v in idx.items()}


def nearest_on_street(key, street_idx, tol=20):
    m = re.match(r"^(\d+) (.+)$", str(key))
    if not m:
        return None
    num, street = int(m.group(1)), m.group(2)
    cands = street_idx.get(street)
    if not cands:
        return None
    best = min(cands, key=lambda c: abs(c[0] - num))
    return (best[1], best[2]) if abs(best[0] - num) <= tol else None


# site address printed at the head of an agenda-item description, e.g.
# "3009 CALIFORNIA STREET - south side between ..." (all-caps in the minutes)
SITE_ADDR_RE = re.compile(
    r"\b(\d{1,5}(?:\s*[-–]\s*\d{1,5})?\s+(?:[A-Z0-9][A-Za-z0-9.']*\s+){0,3}?"
    r"(?:STREETS?|STREET|ST|AVENUE|AVE|BOULEVARD|BLVD|DRIVE|DR|ROAD|RD|WAY|"
    r"TERRACE|TER|COURT|CT|PLACE|PL|LANE|LN|CIRCLE|CIR|ALLEY|HIGHWAY|HWY|"
    r"BROADWAY|EMBARCADERO|Street|Avenue|Boulevard|Drive|Road|Way|Terrace|"
    r"Court|Place|Lane|Circle|Alley|Highway))\b")


def site_address(text):
    if not isinstance(text, str):
        return ""
    m = SITE_ADDR_RE.search(text[:400])
    return m.group(1) if m else ""


PRELIM_RE = re.compile(
    r"Preliminary\s+Recommendation\s*:\s*(.*?)(?:\n\n|\(Propose|\(Continue|$)",
    re.IGNORECASE | re.DOTALL)


def main():
    items = pd.read_csv(OUT / "items.csv", low_memory=False,
                        keep_default_na=False, na_values=[""])
    # idempotency: drop columns this script derives, in case of a rerun
    derived = [c for c in items.columns if c.startswith("prj_")
               or c in {"section_group", "prelim_rec", "record_type", "id_parent",
                        "rec_clean", "action_clean", "rec_dr", "action_dr",
                        "rec_conditions", "action_conditions", "rec_final",
                        "action_final", "rec_num", "action_num", "rec_action_diff",
                        "housing_kw", "office_kw", "commercial_kw", "demo_kw",
                        "new_construction_kw", "adu_kw",
                        "latitude", "longitude", "geo_source", "site_address"}]
    items = items.drop(columns=derived)

    items["section_group"] = items["section"].map(section_group)
    items["prelim_rec"] = items["item_text"].str.extract(PRELIM_RE)[0].str.strip().str[:300]
    items["record_type"] = items["record_id"].map(record_type)
    items["id_parent"] = items["record_id"].map(id_parent)

    items["rec_clean"] = items["prelim_rec"].map(action_cat)
    items["action_clean"] = items["ACTION"].map(action_cat)
    items["rec_dr"] = items["prelim_rec"].map(dr_flag)
    items["action_dr"] = items["ACTION"].map(dr_flag)
    items["rec_conditions"] = items["prelim_rec"].map(conditions_flag)
    items["action_conditions"] = items["ACTION"].map(conditions_flag)
    # DR taken + approved implies conditions (paper rule)
    m = (items["action_dr"] == "dr") & (items["action_clean"] == "approve")
    items.loc[m, "action_conditions"] = 1
    m = (items["action_dr"] != "") & (items["action_clean"] == "")
    items.loc[m, "action_clean"] = "approve"

    items["rec_final"] = [final_cat(c, d, k) for c, d, k in
                          zip(items["rec_clean"], items["rec_dr"], items["rec_conditions"])]
    items["action_final"] = [final_cat(c, d, k) for c, d, k in
                             zip(items["action_clean"], items["action_dr"],
                                 items["action_conditions"])]
    # DRM withdrawals count as approvals of the project (paper rule)
    m = (items["record_type"].isin(["DRM", "DRP"])) & (items["action_clean"] == "withdraw")
    items.loc[m, "action_final"] = "approve"

    items["rec_num"] = items["rec_final"].map(NUM_MAP)
    items["action_num"] = items["action_final"].map(NUM_MAP)
    items["rec_action_diff"] = items["action_num"] - items["rec_num"]

    # content flags from item text
    txt = items["item_text"].fillna("")
    items["housing_kw"] = txt.str.contains(r"housing|dwelling|units|residential",
                                           case=False, regex=True).astype(int)
    items["office_kw"] = txt.str.contains(r"office", case=False).astype(int)
    items["commercial_kw"] = txt.str.contains(
        r"commercial|retail|restaurant|theater|antenna|auto ", case=False).astype(int)
    items["demo_kw"] = txt.str.contains(r"demolition|demolish", case=False).astype(int)
    items["new_construction_kw"] = txt.str.contains("new construction", case=False).astype(int)
    items["adu_kw"] = txt.str.contains(r"accessory dwelling|ADU", regex=True).astype(int)

    # ---------------------------------------------------------- DataSF join
    prj = pd.read_csv(RAW / "datasf_projects.csv", low_memory=False)
    prj["prj_parent"] = prj["record_id"].astype(str).str.replace(
        r"[A-Za-z]+$", "", regex=True)
    keep_prj = ["prj_parent", "record_id", "record_status", "project_name",
                "project_address", "block", "lot", "open_date", "close_date",
                "number_of_units_net", "number_of_affordable_units",
                "number_of_units_exist", "number_of_units_prop",
                "change_of_use", "additions", "new_construction", "demolition",
                "adu", "legalization",
                "residential_exist", "residential_prop",
                "retail_commercial_exist", "retail_commercial_prop",
                "office_exist", "office_prop", "industrial_pdr_exist",
                "industrial_pdr_prop", "medical_exist", "medical_prop",
                "cie_exist", "cie_prop", "parking_spaces_prop"]
    prj_k = prj[keep_prj].copy()
    prj_k.columns = ["prj_parent"] + ["prj_" + c for c in keep_prj[1:]]
    prj_k = prj_k.drop_duplicates("prj_parent", keep="first")

    items = items.merge(prj_k, how="left", left_on="id_parent",
                        right_on="prj_parent").drop(columns=["prj_parent"])

    # parcel centroids -> lat/lon
    cent = pd.read_csv(RAW / "parcel_centroids.csv", dtype={"block": str, "lot": str})
    cent["blklot_key"] = cent["block"].str.strip() + "/" + cent["lot"].str.strip()
    cent = cent.drop_duplicates("blklot_key")
    items["blklot_key"] = (items["prj_block"].astype(str).str.strip() + "/" +
                           items["prj_lot"].astype(str).str.strip())
    items = items.merge(cent[["blklot_key", "latitude", "longitude"]],
                        how="left", on="blklot_key").drop(columns=["blklot_key"])

    items["geo_source"] = pd.NA
    items.loc[items["latitude"].notna(), "geo_source"] = "parcel_centroid"

    # fallback: geocode via EAS address points for historical parcels that
    # no longer exist (renumbered lots, condo conversions)
    apts_path = RAW / "address_points.csv"
    if apts_path.exists():
        apts = pd.read_csv(apts_path)
        apts["norm"] = apts["address_key"].map(norm_address)
        apts_n = apts.groupby("norm")[["latitude", "longitude"]].mean()
        addr_key = items["prj_project_address"].map(norm_address)
        need = items["latitude"].isna() & (addr_key != "")
        lut = {k: (v.latitude, v.longitude) for k, v in apts_n.iterrows() if k}
        got = addr_key[need].map(lut).dropna()
        items.loc[got.index, "latitude"] = [g[0] for g in got]
        items.loc[got.index, "longitude"] = [g[1] for g in got]
        items.loc[got.index, "geo_source"] = "address_point"

        # last resort: the site address printed in the agenda item itself
        # (works for items that never matched a DataSF project record)
        items["site_address"] = items["item_text"].map(site_address)
        site_key = items["site_address"].map(norm_address)
        need2 = items["latitude"].isna() & (site_key != "")
        got2 = site_key[need2].map(lut).dropna()
        items.loc[got2.index, "latitude"] = [g[0] for g in got2]
        items.loc[got2.index, "longitude"] = [g[1] for g in got2]
        items.loc[got2.index, "geo_source"] = "item_address"

        # nearest street number on the same street (parcels without their own
        # EAS point, e.g. odd/even gaps, merged lots)
        street_idx = street_number_lookup(apts_n)
        need3 = items["latitude"].isna() & (site_key != "")
        got3 = site_key[need3].map(
            lambda k: nearest_on_street(k, street_idx)).dropna()
        items.loc[got3.index, "latitude"] = [g[0] for g in got3]
        items.loc[got3.index, "longitude"] = [g[1] for g in got3]
        items.loc[got3.index, "geo_source"] = "street_nearest"

    items.to_csv(OUT / "items.csv", index=False)

    matched = items["prj_record_id"].notna()
    hearing_items = items["record_id"] != ""
    with open(VAL / "projects_report.txt", "w") as f:
        f.write(f"items: {len(items)}\n")
        f.write(f"items with record_id: {int(hearing_items.sum())}\n")
        f.write(f"matched to DataSF project: {int(matched.sum())}\n")
        f.write(f"  ... of items with record_id: {matched[hearing_items].mean():.1%}\n")
        # match rate by era
        yr = items["meeting_date"].astype(str).str[:4].astype("Int64", errors="ignore")
        items2 = items.assign(yr=items["meeting_date"].astype(str).str[:4])
        by_yr = items2[hearing_items].groupby("yr")["prj_record_id"].apply(
            lambda s: s.notna().mean())
        f.write("\nDataSF match rate by year (items with record_id):\n")
        for y, v in by_yr.items():
            f.write(f"  {y}: {v:.1%}\n")
        f.write(f"\nwith coordinates: {int(items['latitude'].notna().sum())}\n")
        f.write("\naction_final distribution:\n")
        for k, v in items["action_final"].value_counts().items():
            f.write(f"  {k or '(blank)'}: {v}\n")
    print(open(VAL / "projects_report.txt").read()[:1500])


if __name__ == "__main__":
    main()
