"""Parse every downloaded minutes file into the item-level dataset.

Reads data/raw/manifest.csv, parses each file with parse_minutes, de-duplicates
meetings that appear in more than one document, and writes:
  data/processed/items.csv         one row per agenda item
  data/processed/meetings.csv      one row per meeting
  data/validation/parse_report.txt coverage stats
"""

import csv
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parse_minutes import extract_text, parse_meeting, split_meetings  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"
VAL = ROOT / "data" / "validation"

BLOCK_COLS = ["SPEAKERS", "ACTION", "AYES", "NAYES", "ABSENT", "RECUSED",
              "EXCUSED", "PRESENT", "MOTION", "RESOLUTION", "DRA", "NOTE"]


def is_special_doc(fname):
    low = fname.lower()
    return any(k in low for k in ["closed", "jnt", "joint", "recpark", "offsite"])


import re  # noqa: E402

MONTHS = {m: i + 1 for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"])}
MONTH_FIXES = {"janaury": "january", "feburary": "february",
               "spetember": "september", "septemeber": "september"}


def expected_date(rec):
    """Date implied by the source: filename YYYYMMDD or the archive link label.

    Minutes documents occasionally carry the wrong date in their own header
    (stenographer copy-paste); the archive metadata is authoritative for
    single-meeting documents.
    """
    m = re.search(r"(19|20)(\d{2})(\d{2})(\d{2})_", rec["file"].rsplit("/", 1)[-1])
    if m:
        return f"{m.group(1)}{m.group(2)}-{m.group(3)}-{m.group(4)}"
    lab = rec.get("label", "") + " " + rec.get("row_text", "")
    m = re.search(r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", lab)
    if m:
        mon = MONTH_FIXES.get(m.group(1).lower(), m.group(1).lower())
        if mon in MONTHS:
            return f"{m.group(3)}-{MONTHS[mon]:02d}-{int(m.group(2)):02d}"
    return None


def main():
    manifest = list(csv.DictReader(open(RAW / "manifest.csv")))
    all_rows = []
    fails = []
    for rec in manifest:
        if rec["status"].startswith("error"):
            fails.append((rec["file"], rec["status"]))
            continue
        path = ROOT / rec["file"]
        if not path.exists() or path.stat().st_size == 0:
            fails.append((rec["file"], "missing"))
            continue
        try:
            text = extract_text(path)
            rows = []
            docs = split_meetings(text)
            for doc in docs:
                rows.extend(parse_meeting(doc, source_file=path.name))
            # reconcile document-internal date errors against source metadata
            exp = expected_date(rec)
            parsed_dates = set(r["meeting_date"] for r in rows)
            if exp and len(parsed_dates) == 1:
                cur = next(iter(parsed_dates))
                if cur != exp:
                    for r in rows:
                        r["meeting_date"] = exp
                        r["date_corrected"] = True
            for r in rows:
                r["source_url"] = rec["url"]
                r["source_label"] = rec["label"]
                r["special_doc"] = is_special_doc(path.name)
            if not rows:
                fails.append((rec["file"], "0 rows"))
            all_rows.extend(rows)
        except Exception as e:  # noqa: BLE001
            fails.append((rec["file"], f"parse error: {e}"))

    df = pd.DataFrame(all_rows)
    for c in BLOCK_COLS:
        if c not in df.columns:
            df[c] = None

    # --- de-duplicate meetings that appear in multiple source documents.
    # Key: (meeting_date, meeting_type). Keep the source file yielding the
    # most items; special-session docs (closed/joint) are kept separately.
    df["n_items_in_file_date"] = df.groupby(
        ["meeting_date", "meeting_type", "file"])["file"].transform("count")
    best = (
        df.groupby(["meeting_date", "meeting_type", "file"])
        .agg(n=("file", "count"), special=("special_doc", "first"))
        .reset_index()
        .sort_values(["meeting_date", "meeting_type", "n"], ascending=[True, True, False])
    )
    keep_files = set()
    for (_, _), grp in best.groupby(["meeting_date", "meeting_type"], dropna=False):
        non_special = grp[~grp["special"]]
        chosen = (non_special if len(non_special) else grp).iloc[0]["file"]
        keep_files.add((chosen, grp.iloc[0]["meeting_date"], grp.iloc[0]["meeting_type"]))
        # also keep special docs (their content is not in the regular minutes)
        for _, r in grp[grp["special"]].iterrows():
            keep_files.add((r["file"], r["meeting_date"], r["meeting_type"]))
    mask = df.apply(lambda r: (r["file"], r["meeting_date"], r["meeting_type"]) in keep_files, axis=1)
    dropped_dupes = int((~mask).sum())
    df = df[mask].drop(columns=["n_items_in_file_date"])

    df = df.sort_values(["meeting_date", "file", "item_num"],
                        key=lambda s: s.astype(str)).reset_index(drop=True)

    meta_cols = ["meeting_date", "meeting_type", "start_time", "end_time",
                 "file", "source_url"]
    keep = meta_cols + ["staff_in_attendance", "commissioners_present",
                        "special_doc", "section_letter", "section", "item_num",
                        "record_id", "item_text"] + BLOCK_COLS
    df = df[[c for c in keep if c in df.columns]]

    OUT.mkdir(parents=True, exist_ok=True)
    VAL.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT / "items.csv", index=False)

    meetings = (df.groupby(["meeting_date", "meeting_type", "file"], dropna=False)
                .agg(start_time=("start_time", "first"),
                     end_time=("end_time", "first"),
                     n_items=("item_text", "count"),
                     n_with_speakers=("SPEAKERS", lambda s: s.notna().sum()),
                     staff_in_attendance=("staff_in_attendance", "first"),
                     commissioners_present=("commissioners_present", "first"),
                     source_url=("source_url", "first"))
                .reset_index())
    meetings.to_csv(OUT / "meetings.csv", index=False)

    yr = Counter(str(d)[:4] for d in df["meeting_date"].dropna())
    with open(VAL / "parse_report.txt", "w") as f:
        f.write(f"files in manifest: {len(manifest)}\n")
        f.write(f"parse failures / empty: {len(fails)}\n")
        f.write(f"duplicate-meeting rows dropped: {dropped_dupes}\n")
        f.write(f"total items: {len(df)}\n")
        f.write(f"meetings: {len(meetings)}\n")
        f.write(f"items with record_id: {int((df['record_id'] != '').sum())}\n")
        f.write(f"items with SPEAKERS: {int(df['SPEAKERS'].notna().sum())}\n")
        f.write(f"items with ACTION: {int(df['ACTION'].notna().sum())}\n")
        f.write("\nitems by year:\n")
        for y in sorted(yr):
            f.write(f"  {y}: {yr[y]}\n")
        f.write("\nfailures:\n")
        for fl, why in fails:
            f.write(f"  {fl}: {why}\n")
    print(open(VAL / "parse_report.txt").read()[:2000])


if __name__ == "__main__":
    main()
