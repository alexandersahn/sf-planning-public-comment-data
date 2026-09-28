"""Written public comment: emails submitted to the Commission before a hearing.

The Commission publishes correspondence in the packet PDF posted before each
hearing (`{YYYYMMDD}pre.pdf`). `fetch_packets.py` downloads those and
`parse_packets.py` splits them into individual messages; this module takes
the parsed and coded corpus and turns it into release rows.

Input is `data/reference/emails_coded.csv.gz`, a committed artifact. It holds
the LLM coding — position and the project each message concerns — which cost
real money to produce and is not reproducible for free, so it is versioned
rather than regenerated. Sender addresses are not in it: they are reduced to
a salted digest (`sender_id`) that preserves every linkage the data needs
without publishing 7,472 people's addresses.

Writes data/processed/emails.csv.
"""

import hashlib
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "data" / "reference" / "emails_coded.csv.gz"
OUT = ROOT / "data" / "processed"
VAL = ROOT / "data" / "validation"

# Messages that are not public comment on a project.
NOT_COMMENT = re.compile(
    r"^\s*(\*{3}\s*media advisory|for immediate release|"
    r"mayor'?s? (press )?office|schedule of public events)", re.I)


def campaign_key(df):
    """Group near-identical messages into the campaign that produced them.

    The upstream detector groups on subject-line similarity, which merges
    opposing campaigns that share a slogan: "Save the Castro Theatre" was the
    subject of both the pro-renovation and the preservationist letter drives,
    giving one 851-message campaign split 427 support / 424 oppose. Inside a
    body cluster the coded position is ~99% consistent, so the grouping was
    wrong, not the coding. Keep the detector's grouping and split only the
    campaigns that come out internally mixed.
    """
    form = df["is_form"] == 1
    mixed = df[form].groupby("form_name")["position"].agg(
        lambda x: (x == "support").any() and (x == "oppose").any())
    mixed = set(mixed[mixed].index)
    key = df["form_name"].where(form)
    split = key.isin(mixed)
    key = key.mask(split, key + " [" + df["position"].fillna("unclear") + "]")
    return key


def link_items(em, items):
    """Attach each message to the agenda item it concerns.

    The packet date is usually not the hearing date: of 1,865 distinct
    (packet date, project) pairs only 684 (37%) match an item heard that day,
    because items get continued. So the project link is the durable one and
    the item is derived — the project's first hearing on or after the packet
    date — with the lag recorded so anyone who needs the strict subset can
    filter on it.
    """
    it = (items[items["id_parent"].notna()]
          [["item_id", "id_parent", "meeting_date"]].copy())
    it["meeting_date"] = pd.to_datetime(it["meeting_date"], errors="coerce")
    it = it.sort_values("meeting_date")

    em = em.copy()
    em["_packet"] = pd.to_datetime(em["meeting_date"], errors="coerce")
    em = em.sort_values("_packet")
    merged = pd.merge_asof(
        em.dropna(subset=["_packet", "id_parent"]),
        it.rename(columns={"meeting_date": "_heard"}),
        left_on="_packet", right_on="_heard", by="id_parent",
        direction="forward", allow_exact_matches=True)
    merged["item_lag_days"] = (merged["_heard"] - merged["_packet"]).dt.days
    merged["item_heard_as_calendared"] = (merged["item_lag_days"] == 0).astype("Int64")
    return merged.drop(columns=["_packet", "_heard"])


def main():
    if not REF.exists():
        print(f"no email corpus at {REF}; skipping written comment")
        return
    em = pd.read_csv(REF, low_memory=False)
    n0 = len(em)

    em = em[~em["body"].fillna("").str.match(NOT_COMMENT)]
    em = em[em["sender_id"].fillna("") != ""]
    n_dropped = n0 - len(em)

    # one message per sender, project and packet date
    em = em.drop_duplicates(["sender_id", "id_parent", "meeting_date", "body"])

    em["campaign"] = campaign_key(em)
    em["is_campaign"] = em["campaign"].notna().astype(int)

    items = pd.read_csv(OUT / "items.csv", low_memory=False,
                        usecols=["item_id", "id_parent", "meeting_date"])
    em = link_items(em, items)

    em["channel"] = "email"
    em["comment_id"] = [
        "e" + hashlib.sha1(f"{s}|{d}|{b[:80]}".encode()).hexdigest()[:12]
        for s, d, b in zip(em["sender_id"], em["meeting_date"],
                           em["body"].fillna(""))]
    em.to_csv(OUT / "emails.csv", index=False)

    mixed = em[em.campaign.notna()].groupby("campaign")["position"].agg(
        lambda x: (x == "support").any() and (x == "oppose").any()).sum()
    VAL.mkdir(exist_ok=True)
    with open(VAL / "emails_report.txt", "w") as f:
        f.write(f"messages in corpus: {n0}\n")
        f.write(f"dropped (not public comment, or no sender): {n_dropped}\n")
        f.write(f"released: {len(em)}\n")
        f.write(f"unique senders: {em['sender_id'].nunique()}\n")
        f.write(f"projects: {em['id_parent'].nunique()}\n")
        f.write(f"linked to an agenda item: {em['item_id'].notna().sum()}\n")
        f.write(f"  heard as calendared: "
                f"{int((em['item_heard_as_calendared'] == 1).sum())}\n")
        f.write(f"campaign messages: {int(em['is_campaign'].sum())} in "
                f"{em['campaign'].nunique()} campaigns\n")
        f.write(f"campaigns with mixed positions: {int(mixed)}\n")
        f.write(f"date range: {em['meeting_date'].min()} to "
                f"{em['meeting_date'].max()}\n")
    print(open(VAL / "emails_report.txt").read())


if __name__ == "__main__":
    main()
