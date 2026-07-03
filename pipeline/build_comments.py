"""Extract per-speaker comment records from the item-level dataset.

Reads data/processed/items.csv, applies speakers.parse_speakers to every
SPEAKERS block, and writes:
  data/processed/comments_raw.csv    one row per speaker-comment
  data/validation/speaker_report.txt method/coverage stats
"""

import sys
from collections import Counter
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from speakers import parse_speakers  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "processed"
VAL = ROOT / "data" / "validation"


def main():
    items = pd.read_csv(OUT / "items.csv", low_memory=False,
                        keep_default_na=False, na_values=[""])
    items["item_id"] = range(len(items))

    recs = []
    methods = Counter()
    for row in items.itertuples():
        block = row.SPEAKERS
        if pd.isna(block):
            continue
        parsed, method = parse_speakers(block)
        methods[method] += 1
        for i, p in enumerate(parsed):
            recs.append({
                "item_id": row.item_id,
                "meeting_date": row.meeting_date,
                "record_id": row.record_id,
                "section": row.section,
                "item_num": row.item_num,
                "speaker_order": i + 1,
                "sign": p.get("sign"),
                "name_raw": p.get("name_raw", ""),
                "comment": p.get("comment", ""),
                "same_as": p.get("same_as", ""),
                "method": method,
            })

    df = pd.DataFrame(recs)

    # ---- resolve "Same as Item 9a." references within the same meeting ----
    # items file identifies a meeting by (file, meeting_date)
    item_meta = items.set_index("item_id")[["file", "meeting_date", "item_num"]]
    df = df.merge(item_meta[["file"]], left_on="item_id", right_index=True, how="left")
    same = df[df["method"] == "same_as"].copy()
    ref_num = same["same_as"].str.extract(r"[Ii]tem\s+#?\s*(\d{1,2}[a-z]?)", expand=False)
    resolved_frames = []
    resolved_idx = set()
    lookup = df[df["method"] != "same_as"].groupby(
        ["file", "meeting_date", "item_num"])
    groups = set(lookup.groups.keys())
    for idx, row in same.iterrows():
        num = ref_num.get(idx)
        if pd.isna(num):
            continue
        key = (row["file"], row["meeting_date"], num)
        if key not in groups:
            continue
        cp = lookup.get_group(key).copy()
        cp["item_id"] = row["item_id"]
        cp["record_id"] = row["record_id"]
        cp["section"] = row["section"]
        cp["item_num"] = row["item_num"]
        cp["method"] = "same_as_resolved"
        resolved_frames.append(cp)
        resolved_idx.add(idx)
    unresolved = same.loc[~same.index.isin(resolved_idx)].assign(
        method="same_as_unresolved")
    df = pd.concat(
        [df[df["method"] != "same_as"]]
        + resolved_frames + [unresolved], ignore_index=True)
    print(f"same_as blocks resolved: {len(resolved_idx)} / {len(same)}")
    df = df.drop(columns=["file"])
    df.to_csv(OUT / "comments_raw.csv", index=False)
    items.to_csv(OUT / "items.csv", index=False)  # now includes item_id

    n_blocks = sum(methods.values())
    with open(VAL / "speaker_report.txt", "w") as f:
        f.write(f"SPEAKERS blocks: {n_blocks}\n")
        f.write(f"comment records: {len(df)}\n")
        f.write(f"records with sign: {int(df['sign'].notna().sum())}\n\n")
        f.write("blocks by method:\n")
        for m, n in methods.most_common():
            f.write(f"  {m}: {n} ({n / n_blocks:.1%})\n")
        f.write("\ncomment records by method:\n")
        for m, n in df["method"].value_counts().items():
            f.write(f"  {m}: {n}\n")
    print(open(VAL / "speaker_report.txt").read())


if __name__ == "__main__":
    main()
