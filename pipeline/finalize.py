"""Assemble the public release: tidy CSVs + codebook + validation summary.

Writes to public/:
  meetings.csv   one row per commission meeting
  items.csv      one row per agenda item (with project attributes)
  comments.csv   one row per public comment (speaker-level)
  codebook.md    variable documentation
  README.md      sources and build notes
"""

import re
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from resolve_commenters import resolve  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "processed"
VAL = ROOT / "data" / "validation"
PUB = ROOT / "public"

ITEM_COLS = [
    "item_id", "meeting_date", "meeting_type", "file", "source_url",
    "section_letter", "section", "section_group", "item_num", "record_id",
    "record_type", "id_parent", "item_text", "prelim_rec",
    "SPEAKERS", "ACTION", "AYES", "NAYES", "ABSENT", "RECUSED", "EXCUSED",
    "MOTION", "RESOLUTION",
    "rec_clean", "rec_dr", "rec_conditions", "rec_final", "rec_num",
    "action_clean", "action_dr", "action_conditions", "action_final",
    "action_num", "rec_action_diff",
    "housing_kw", "office_kw", "commercial_kw", "demo_kw",
    "new_construction_kw", "adu_kw",
    "prj_record_id", "prj_record_status", "prj_project_name",
    "prj_project_address", "prj_block", "prj_lot", "prj_open_date",
    "prj_close_date", "prj_number_of_units_net", "prj_number_of_affordable_units",
    "prj_number_of_units_exist", "prj_number_of_units_prop",
    "prj_change_of_use", "prj_additions", "prj_new_construction",
    "prj_demolition", "prj_adu", "prj_legalization",
    "prj_residential_exist", "prj_residential_prop",
    "prj_retail_commercial_exist", "prj_retail_commercial_prop",
    "prj_office_exist", "prj_office_prop", "prj_industrial_pdr_exist",
    "prj_industrial_pdr_prop", "prj_medical_exist", "prj_medical_prop",
    "prj_cie_exist", "prj_cie_prop", "prj_parking_spaces_prop",
    "site_address", "latitude", "longitude", "geo_source",
]

COMMENT_COLS = [
    "item_id", "meeting_date", "record_id", "section", "item_num",
    "speaker_order", "name_clean", "name_raw", "title", "role_title",
    "organization",
    "is_anonymous", "anon_gender", "name_single", "is_staff", "is_commissioner",
    "role_long", "role_source", "role_group", "sign", "sign_imputed",
    "sign_prob", "sign_source", "comment", "method",
]


SIGN_POS = {"+": "support", "-": "oppose", "=": "neutral"}

EMAIL_RE = re.compile(r"\S*@[\w-]+(\.[\w-]+)*\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?<!\d)(\(?\d{3}\)?[-.\s]){1,2}\d{3}[-.\s]\d{4}(?!\d)")


def scrub_contacts(df, cols):
    """Strip addresses and phone numbers from released text.

    The email corpus is scrubbed when it is exported, but spoken comment
    never was, and stenographers do occasionally transcribe an address a
    speaker read out. Scrubbing at the release boundary covers both channels
    and any future one.
    """
    for c in cols:
        if c in df.columns:
            df[c] = (df[c].astype("string")
                     .str.replace(EMAIL_RE, "[email removed]", regex=True)
                     .str.replace(PHONE_RE, "[phone removed]", regex=True))
    return df


def unify_channels(spoken, items):
    """One table for both channels: spoken testimony and written comment.

    The site used to read spoken comment from here and written comment from a
    file exported by hand out of another project, so the two could not agree
    and the repository could not produce what the site displayed. Both now
    come from this table.

    Channel-specific columns stay rather than being flattened away — the
    stenographer's polarity marks mean something different from an LLM's
    reading of an email body, and pooling them would hide that. `position`
    and `position_source` are the columns that are safe to use across both.
    """
    em_path = OUT / "emails.csv"
    spoken = spoken.copy()
    spoken["channel"] = "spoken"
    spoken["comment_id"] = ["s%07d" % i for i in range(len(spoken))]
    key = items[["item_id", "id_parent"]].drop_duplicates("item_id")
    spoken = spoken.merge(key, on="item_id", how="left")
    sign = spoken["sign"].fillna(spoken.get("sign_imputed"))
    spoken["position"] = sign.map(SIGN_POS)
    spoken["position_source"] = spoken.get("sign_source")
    spoken["text"] = spoken["comment"]

    if not em_path.exists():
        print("no emails.csv; releasing spoken comment only")
        return spoken

    em = pd.read_csv(em_path, low_memory=False)
    em["channel"] = "email"
    em["text"] = em["body"]
    em["position_source"] = "llm"
    em["role_long"] = pd.NA
    em["role_group"] = pd.NA
    em["role_source"] = pd.NA
    em["meeting_date"] = em["meeting_date"].astype(str)

    cols = sorted(set(spoken.columns) | set(em.columns))
    both = pd.concat([spoken.reindex(columns=cols), em.reindex(columns=cols)],
                     ignore_index=True)
    lead = ["comment_id", "channel", "meeting_date", "item_id", "id_parent",
            "record_id", "name_clean", "position", "position_source",
            "role_long", "role_group", "role_source", "text"]
    return both[[c for c in lead if c in both.columns]
                + [c for c in both.columns if c not in lead]]


def drop_fanout_duplicates(com, items):
    """Remove the redundant copies a speaker's testimony fans out into.

    One agenda item that spans several case suffixes (2017-008051 was heard
    as SHD/ENV/DNX/CUA/OFA across sub-items 1a-2e) becomes several item rows,
    and the whole speaker list is attached to each. 456 item slots are also
    parsed twice under two section_groups. Between them, one person speaking
    once on 30 Van Ness on 2020-05-21 is recorded 14 times, and about a fifth
    of all comment rows are redundant.

    The redundant rows are dropped. Keeping them as a flag meant every
    headline count in the repository disagreed with the site unless the
    reader knew to filter, which is a trap rather than a feature; the item
    a comment is attached to is still recorded, just once.
    """
    key = items[["item_id", "id_parent"]].drop_duplicates("item_id")
    c = com.merge(key, on="item_id", how="left")
    dup_key = ["meeting_date", "name_raw", "comment", "id_parent"]
    # only rows that actually resolve to a project can fan out
    resolvable = c["id_parent"].notna() & c["name_raw"].notna()
    dup = (resolvable & c.duplicated(dup_key, keep="first")).values
    print(f"  dropped {int(dup.sum()):,} fan-out duplicate rows")
    return com[~dup].copy()


def main():
    PUB.mkdir(exist_ok=True)

    items = pd.read_csv(OUT / "items.csv", low_memory=False,
                        keep_default_na=False, na_values=[""])
    comments = pd.read_csv(OUT / "comments.csv", low_memory=False,
                           keep_default_na=False, na_values=[""])
    meetings = pd.read_csv(OUT / "meetings.csv")

    items_pub = items[[c for c in ITEM_COLS if c in items.columns]]
    # gzipped: full agenda-item text makes the plain file >50 MB
    items_pub.to_csv(PUB / "items.csv.gz", index=False, compression="gzip")
    (PUB / "items.csv").unlink(missing_ok=True)

    com = comments[[c for c in COMMENT_COLS if c in comments.columns]].copy()
    com = com[com["method"] != "same_as_unresolved"]
    com = drop_fanout_duplicates(com, items)
    com = unify_channels(com, items)
    com = scrub_contacts(com, ["text", "comment", "subject"])
    com = resolve(com)
    com.to_csv(PUB / "comments.csv", index=False)

    # ancillary crosswalk of likely-identical names for downstream linking
    # (applied merges + unapplied candidates with evidence scores)
    applied = pd.read_csv(VAL / "name_merge_log.csv")
    applied["status"] = "applied"
    cand = pd.read_csv(VAL / "name_review.csv")
    cand = cand.rename(columns={})
    cand["status"] = "candidate"
    cand["source"] = "fuzzy_review"
    xwalk = pd.concat([applied, cand], ignore_index=True)[
        ["variant", "canonical", "status", "source", "dist", "ratio",
         "n_variant", "n_canonical"]]
    xwalk.to_csv(PUB / "name_crosswalk.csv", index=False)

    # ancillary staff panel (Wayback Machine directory snapshots, 2011-2026)
    tenure_path = OUT / "staff_tenure.csv"
    if tenure_path.exists():
        pd.read_csv(tenure_path).to_csv(PUB / "staff_tenure.csv", index=False)

    # person-level affiliation roster: the speakers whose stated affiliation
    # was carried to their other comments, so `role_source == roster_derived`
    # can be audited. Only the entries that were actually applied.
    roster_path = VAL / "person_roster.csv"
    if roster_path.exists():
        roster = pd.read_csv(roster_path)
        (roster[roster["used"] == 1].drop(columns=["used"])
         .to_csv(PUB / "person_roster.csv", index=False))

    # meeting-level: add comment counts
    cc = com.groupby("meeting_date").size().rename("n_comments")
    meetings = meetings.merge(cc, on="meeting_date", how="left")
    meetings["n_comments"] = meetings["n_comments"].fillna(0).astype(int)
    meetings.to_csv(PUB / "meetings.csv", index=False)

    # Summary numbers, counted on the deduplicated rows. Reporting len(com)
    # here would advertise the fan-out inflation as the size of the dataset —
    # 76,731 rather than 62,735 — in the same file that tells people to
    # filter it out.
    uniq = com
    sp = uniq[uniq["channel"] == "spoken"]
    signed = sp["sign"].notna().sum()
    named = (uniq["name_clean"].notna() & (uniq["name_clean"] != "")).sum()
    imputed = (int((uniq["sign_source"] == "model").sum())
               if "sign_source" in uniq else 0)

    lines = [
        "# Dataset summary",
        "",
        "Fan-out duplicates — copies of the same testimony repeated across the",
        "item rows it was recorded against — are removed, not flagged.",
        "",
        f"- meetings: {len(meetings)} ({meetings['meeting_date'].min()} to {meetings['meeting_date'].max()})",
        f"- agenda items: {len(items_pub)}",
        f"- public comments: {len(uniq)}",
        f"  - spoken (meeting minutes, 1998-): "
        f"{int((uniq['channel'] == 'spoken').sum())}",
        f"  - written (hearing packets, 2017-): "
        f"{int((uniq['channel'] == 'email').sum())}",
        f"- comments with speaker name: {named} ({named / len(uniq):.0%})",
        f"- spoken comments with a stenographer polarity sign: {signed}"
        f" ({signed / max(len(sp), 1):.0%})",
        f"- comments with model-imputed sign: {imputed}",
        f"- unique commenters: {uniq['commenter_id'].nunique()}"
        f" (name spellings: {uniq.loc[uniq['name_clean'].notna(), 'name_clean'].nunique()})",
        f"- items matched to DataSF project records: {items['prj_record_id'].notna().sum()}",
        f"- items with coordinates: {items['latitude'].notna().sum()}",

    ]
    (PUB / "SUMMARY.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
