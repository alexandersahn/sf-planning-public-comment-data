"""Resolve name spellings to a single commenter, across both channels.

The same person is spelled differently in the minutes and in the packets —
"David Brockman" at the microphone, "David Broockman" in an email — and the
stenographer renders some names by ear, so "Sonja Trauss" also appears as
"Transs", "Trouss" and "Kraus". Counting distinct `name_clean` therefore
overstates the number of participants, and doing that count in one place
while the site does it another way guarantees the two disagree.

This runs once, in the pipeline, and ships `commenter_id` on the release so
every consumer counts the same thing.

Merging is deliberately conservative. Exact-name matching alone joins 737
name pairs across the two channels, but roughly a third of those are
namesakes: *john goldberg* spoke in 1998 and emailed in 2023, and the corpus
holds eight different Lees with common first names. A false merge invents a
participation history for a real person, which is worse than leaving two
records apart, so a name match is only acted on with corroboration — a
shared project, or activity within two years plus an uncommon surname.
"""

import collections
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rosters import CURATED  # noqa: E402

FUZZ_MIN = 90          # token_sort_ratio, for surname typos
SURNAME_MIN = 60       # surname similarity, for names heard wrong
COMMON_SURNAME = 20    # a surname this widespread cannot corroborate alone
NEAR_YEARS = 2

_CAMEL = re.compile(r"^([A-Z][a-z]+)([A-Z][a-z].*)$")


def _n(s):
    s = str(s or "").lower().strip()
    s = re.sub(r"[^a-z\s'-]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def _alias_map():
    out = {}
    for _role, people in CURATED.items():
        for canon, alts in people.items():
            for a in [canon] + list(alts):
                out[_n(a)] = _n(canon)
    return out


def normalise(s, alias):
    raw = str(s or "").strip()
    m = _CAMEL.match(raw)          # "SonjaTranss" -> "Sonja Transs"
    if m:
        raw = m.group(1) + " " + m.group(2)
    k = _n(raw)
    return alias.get(k, k)


def resolve(com):
    """Add `commenter_id` to the unified comment table."""
    try:
        from rapidfuzz import fuzz
    except ImportError:
        print("  rapidfuzz missing; commenter_id falls back to exact names")
        fuzz = None

    alias = _alias_map()
    com = com.copy()
    com["_n"] = com["name_clean"].map(lambda s: normalise(s, alias))
    com["_year"] = pd.to_datetime(com["meeting_date"], errors="coerce").dt.year

    named = com[com["_n"].str.split().str.len() >= 2]
    prof = named.groupby("_n").agg(
        proj=("id_parent", lambda s: set(s.dropna())),
        yrs=("_year", lambda s: set(s.dropna())))
    names = list(prof.index)
    last = collections.Counter(x.split()[-1] for x in names)

    parent = {n: n for n in names}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    def corroborated(x, y):
        shared = prof.proj[x] & prof.proj[y]
        if shared:
            return True
        gap = min((abs(a - b) for a in prof.yrs[x] for b in prof.yrs[y]),
                  default=999)
        common = max(last[x.split()[-1]], last[y.split()[-1]])
        return gap <= NEAR_YEARS and common <= COMMON_SURNAME

    if fuzz is not None:
        blocks = collections.defaultdict(list)
        for n in names:
            t = n.split()
            blocks[("sur", t[0][0], t[-1][:3])].append(n)
            # a surname heard wrong shares no prefix, so also block on an
            # uncommon first name
            blocks[("first", t[0])].append(n)
        first_freq = collections.Counter(n.split()[0] for n in names)

        for key, members in blocks.items():
            if len(members) < 2 or len(members) > 400:
                continue
            if key[0] == "first" and first_freq[key[1]] > 12:
                continue
            for i in range(len(members)):
                for j in range(i + 1, len(members)):
                    x, y = members[i], members[j]
                    if key[0] == "first":
                        if fuzz.ratio(x.split()[-1], y.split()[-1]) < SURNAME_MIN:
                            continue
                    elif fuzz.token_sort_ratio(x, y) < FUZZ_MIN:
                        continue
                    if corroborated(x, y):
                        union(x, y)

    # curated aliases are hand-verified and merge unconditionally
    for n in names:
        c = alias.get(n)
        if c and c in parent:
            union(n, c)

    canon = {n: find(n) for n in names}
    merged = sum(1 for k, v in canon.items() if k != v)
    com["commenter_id"] = com["_n"].map(canon).fillna(com["_n"])
    # anonymous and single-token speakers are not resolvable into a person
    com.loc[com["_n"].str.split().str.len() < 2, "commenter_id"] = pd.NA
    print(f"  resolved {len(names):,} name spellings into "
          f"{com['commenter_id'].nunique():,} commenters ({merged} merged)")
    return com.drop(columns=["_n", "_year"])
