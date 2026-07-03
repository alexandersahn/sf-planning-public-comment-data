"""Clean speaker names: garbage removal, anonymization flags, typo repair,
and fuzzy deduplication.

Inputs:  data/processed/comments_raw.csv, author typo lookups (seeded from the
         published replication archive), nickname lookup.
Outputs: data/processed/comments.csv          cleaned comment records
         data/validation/name_merge_log.csv    every applied name merge + source
         data/validation/name_review.csv       fuzzy candidates NOT auto-applied
         data/validation/name_report.txt       summary stats
"""

import re
import sys
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein

sys.path.insert(0, str(Path(__file__).resolve().parent))
from speakers import is_name_like  # noqa: E402

# role/title phrases (as opposed to organization names)
ROLE_PHRASE_RE = re.compile(
    r"(?i)^(?:(?:the )?(?:project |legislative |executive |exec\.? |deputy |acting |"
    r"assistant |senior |chief |co-)?"
    r"(?:sponsor|architect|attorney|aide|director|planner|engineer|contractor|"
    r"owner|appellant|d\.?r\.? requestor|requestor|representative|rep\.|counsel|"
    r"president|vice president|chair(?:person|man|woman)?|manager|organizer|"
    r"coordinator|principal|realtor|broker|consultant|developer|staff|secretary|"
    r"treasurer|founder|ceo|cfo)\b"
    r"|(?:representing|on behalf of)\b)")

# unanchored: does the segment mention a role word at all?
ROLE_WORD_RE = re.compile(
    r"(?i)\b(sponsor|architect|attorney|aide|director|planner|engineer|"
    r"contractor|owner|appellant|requestor|representative|counsel|president|"
    r"chair(?:person|man|woman)?|manager|organizer|coordinator|principal|"
    r"realtor|broker|consultant|developer|staff|secretary|treasurer|founder|"
    r"ceo|cfo|representing|on behalf of)\b")

NAME_SUFFIX_RE = re.compile(r"(?i)^(jr|sr|ii|iii|iv|esq)\.?$")

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"
VAL = ROOT / "data" / "validation"
ORIG = ROOT / "replication_original" / "data"

TITLE_RE = re.compile(
    r"^(Dr|Rev|Mr|Mrs|Prof|Ms|Lt|Fr|Capt|Father|Sup|Sarg|Sgt|Reverend|Supervisor|"
    r"Captain|Commissioner|President|Officer|Senator|Assemblymember)\.?\s+",
    re.IGNORECASE)

# whole-entry garbage: not a speaker at all
GARBAGE_RE = re.compile(
    r"^(re:|adjournment|adopted|action|ayes|nayes|noes|absent|motion|resolution|"
    r"note|none|n/?a|and|at|the|prior to|following|thereafter|adjourned)\b[:\s]*|"
    r"^\d+([\s-]|$)|^\W+$|^(19|20)\d{2}$",
    re.IGNORECASE)
ADDRESS_RE = re.compile(
    r"^\d+\s+\w+|\b(street|avenue|boulevard|st\.|ave\.|blvd)\b", re.IGNORECASE)

ANON_RE = re.compile(
    r"speaker|anonymous|unknown|name unclear|unclear name|no name|did not state|"
    r"name not stated|unintelligible|inaudible|^male\b|^female\b|^caller\b|"
    r"^requestor|^representative$|^neighbor$|^resident$|^tenant$|^owner$|"
    r"^applicant$|^architect$|^attorney$|^translator$|^interpreter$|"
    r"^(m|f)\)|^\((m|f)\)", re.IGNORECASE)

ROLE_SIGNS = [
    (re.compile(r"project sponsor|sponsor rep|^sponsor$|architect for|project architect",
                re.IGNORECASE), "+"),
    (re.compile(r"dr requestor|d\.?r\.? requestor|appellant", re.IGNORECASE), "-"),
]

SUPERVISORS = {
    "Becerril": "Alicia Becerril", "Brown": "Vallie Brown", "Campos": "David Campos",
    "Chiu": "David Chiu", "Chu": "David Chiu", "Chris Da": "Chris Daly",
    "Christensen": "Julie Christensen", "Cohen": "Malia Cohen", "Dufty": "Bevan Dufty",
    "Tang": "Katy Tang", "Kathy Tang": "Katy Tang", "Kim": "Jane Kim",
    "Yee": "Leland Yee", "Leland": "Leland Yee", "Leno": "Mark Leno",
    "Farrell": "Mark Farrell", "Mark Ferrell": "Mark Farrell",
    "McGoldrick": "Jacob McGoldrick", "McGoldri": "Jacob McGoldrick",
    "Mirkarimi": "Ross Mirkarimi", "Mar": "Gordon Mar", "Peskin": "Aaron Peskin",
    "Safai": "Ahsha Safai", "Ronen": "Hillary Ronen", "Sandoval": "Gerardo Sandoval",
    "Sheehy": "Jeffrey Sheehy", "Stefani": "Catherine Stefani",
    "Walton": "Shamann Walton", "Haney": "Matthew Haney", "Avalos": "John Avalos",
    "Ammiano": "Tom Ammiano", "Amiano": "Tom Ammiano",
    "Weiner": "Scott Wiener", "Wien": "Scott Wiener", "Wiener": "Scott Wiener",
}


def normalize(name):
    n = re.sub(r"\s+", " ", str(name)).strip()
    n = n.strip(" ,;:.-–—*_'\"")
    n = re.sub(r"\s*\((?!M\)|F\))[^)]*\)$", "", n)  # trailing parenthetical (not (M)/(F))
    return n.strip()


def load_typo_maps():
    maps = {}
    t1 = pd.read_csv(RAW / "lookup_typo1.csv")
    maps.update(dict(zip(t1["speaker.x"], t1["speaker.y"])))
    t2 = pd.read_csv(ORIG / "lookup_typo2.csv", encoding="latin1")
    maps.update(dict(zip(t2["name_clean"], t2["name_corrected"])))
    t3 = pd.read_csv(RAW / "lookup_typo3.csv")
    maps.update(dict(zip(t3["name_all"], t3["name_all.x"])))
    # drop self-maps / NaN
    return {k: v for k, v in maps.items()
            if isinstance(k, str) and isinstance(v, str) and k != v}


def fuzzy_merges(counts):
    """Propose merges of rare variants into common canonical names.

    counts: Series name -> frequency. Auto-merge only when very safe:
    Levenshtein distance 1 on names >= 8 chars, same token count, and the
    canonical is at least 3x more frequent. Distance-2 candidates go to the
    review file.
    """
    names = list(counts.index)
    by_key = {}
    for n in names:
        toks = n.split()
        if len(toks) < 2:
            continue
        key = (n[0].lower(), toks[-1][:2].lower(), len(toks))
        by_key.setdefault(key, []).append(n)

    auto, review = [], []
    for key, group in by_key.items():
        if len(group) < 2:
            continue
        group = sorted(group, key=lambda x: -counts[x])
        for i, canon in enumerate(group):
            for var in group[i + 1:]:
                d = Levenshtein.distance(canon.lower(), var.lower())
                if d == 0 or d > 2:
                    continue
                ratio = fuzz.ratio(canon.lower(), var.lower())
                rec = {"variant": var, "canonical": canon,
                       "dist": d, "ratio": ratio,
                       "n_variant": int(counts[var]), "n_canonical": int(counts[canon])}
                # frequency rule: fold the rarer spelling into the more common
                # one when the frequency evidence is one-sided
                if d == 1 and ((len(var) >= 8 and counts[canon] >= 3 * counts[var]
                                and counts[canon] >= 3)
                               or (len(var) >= 6 and counts[var] == 1
                                   and counts[canon] >= 2)):
                    auto.append(rec)
                elif (d == 2 and len(var) >= 10 and ratio >= 90
                      and counts[var] == 1 and counts[canon] >= 3):
                    auto.append(rec)
                elif ratio >= 88:
                    review.append(rec)
    return auto, review


def main():
    df = pd.read_csv(OUT / "comments_raw.csv",
                     keep_default_na=False, na_values=[""])
    merge_log = []

    # ------------------------------------------------ row-level normalization
    df["name_raw"] = df["name_raw"].fillna("")
    df["name_clean"] = df["name_raw"].map(normalize)

    # a polarity sign that leaked into the name ("= Rich Sucre")
    leaked = df["name_clean"].str.match(r"^[+=−-]\s+\S")
    leaked_sign = df.loc[leaked, "name_clean"].str[0].replace({"−": "-"})
    df.loc[leaked & df["sign"].isna(), "sign"] = leaked_sign
    df.loc[leaked, "name_clean"] = df.loc[leaked, "name_clean"].str.replace(
        r"^[+=−-]\s+", "", regex=True)

    # "Jill Griffin and Jack Jensen" / "Kathleen & Courtney" -> two records
    pair = df["name_clean"].str.match(
        r"^[A-Z][\w.'-]*(\s+[A-Z][\w.'-]*){0,2}\s+(and|&)\s+[A-Z][\w.'-]*(\s+[A-Z][\w.'-]*){0,2}$")
    if pair.any():
        halves = df.loc[pair, "name_clean"].str.split(r"\s+(?:and|&)\s+", regex=True)
        df.loc[pair, "name_clean"] = halves.str[0]
        extra = df.loc[pair].copy()
        extra["name_clean"] = halves.str[1].values
        extra["name_raw"] = extra["name_clean"]
        df = pd.concat([df, extra], ignore_index=True)

    # "Jesse Liu/Carol Cheung" -> two records
    pair2 = df["name_clean"].str.match(
        r"^[A-Z][\w.'-]+(\s+[A-Z][\w.'-]+){0,2}/[A-Z][\w.'-]+(\s+[A-Z][\w.'-]+){0,2}$")
    if pair2.any():
        halves = df.loc[pair2, "name_clean"].str.split("/")
        df.loc[pair2, "name_clean"] = halves.str[0].str.strip()
        extra = df.loc[pair2].copy()
        extra["name_clean"] = halves.str[1].str.strip().values
        extra["name_raw"] = extra["name_clean"]
        df = pd.concat([df, extra], ignore_index=True)

    # gender markers from anonymous entries: "(M) Speaker"
    df["anon_gender"] = df["name_clean"].str.extract(r"^\(?([MF])\)", expand=False)

    # entries where the "name" carries more than a name: split residual
    # dashes; the dash remainder is a role/title if it reads like one,
    # otherwise it is comment text
    df["role_title"] = ""
    df["organization"] = ""
    resid = df["name_clean"].str.contains("–|—", regex=True, na=False)
    split2 = df.loc[resid, "name_clean"].str.split(r"\s*[–—]\s*", n=1, regex=True)
    df.loc[resid, "name_clean"] = split2.str[0].str.strip()
    rest = split2.str[1].fillna("").str.strip()
    rest_is_role = rest.map(lambda s: bool(ROLE_PHRASE_RE.match(s)
                                           or (ROLE_WORD_RE.search(s) and len(s.split()) <= 5))
                            and len(s) < 50)
    df.loc[rest[rest_is_role].index, "role_title"] = rest[rest_is_role]
    add_comment = rest.where(~rest_is_role, "")
    df.loc[resid, "comment"] = (
        add_comment + " " + df.loc[resid, "comment"].fillna("")).str.strip()

    # comma structure: "Name, Title, Organization" — extract title/org
    # BEFORE the sentence filter so real people aren't blanked
    def parse_comma_structure(row_name):
        segs = [s.strip() for s in str(row_name).split(",") if s.strip()]
        # re-join numeric groupings split by the comma ("1,000 Grandmothers")
        merged = []
        for seg in segs:
            if merged and merged[-1] and merged[-1][-1].isdigit() and re.match(r"^\d{3}\b", seg):
                merged[-1] += "," + seg
            else:
                merged.append(seg)
        segs = merged
        if len(segs) < 2 or not is_name_like(segs[0]) or len(segs[0].split()) > 4:
            return row_name, "", ""
        name = segs[0]
        titles, orgs = [], []
        for seg in segs[1:]:
            if NAME_SUFFIX_RE.match(seg):
                name += ", " + seg          # "Martin Luther King, Jr."
            elif ROLE_WORD_RE.search(seg) and len(seg) < 60:
                titles.append(seg)
            else:
                orgs.append(seg)
        return name, "; ".join(titles), ", ".join(orgs)

    has_comma = df["name_clean"].str.contains(",", na=False)
    parsed = df.loc[has_comma, "name_clean"].map(parse_comma_structure)
    df.loc[has_comma, "name_clean"] = parsed.str[0]
    new_title = parsed.str[1]
    new_org = parsed.str[2]
    df.loc[has_comma, "role_title"] = (
        df.loc[has_comma, "role_title"].where(new_title == "", other=new_title))
    df.loc[has_comma, "organization"] = new_org.where(new_org != "", "")

    STOPWORDS = r"(?:is|the|of|to|with|for|she|he|they|we|it|a|in|on|her|his|" \
                r"are|was|will|would|has|have|not|no|at|by|from|as|that|this|be|been)"
    sentence_like = (
        df["name_clean"].str.split().str.len().gt(4)
        | df["name_clean"].str.contains(rf"(?:^|\s){STOPWORDS}(?:\s|$)", regex=True)
        | df["name_clean"].str.match(
            r"(?i)^(urged?|asked|spoke|stated|requested|expressed|concerned?|"
            r"opposed|support(s|ed|ing)?\b|in (support|opposition|favor)|"
            r"these minutes|no one|nobody|there (was|were)|would like|"
            r"read (a|the)|submitted|presentation|response to|staff report)")
    )
    moved = sentence_like & (df["name_clean"] != "")
    df.loc[moved, "comment"] = (
        df.loc[moved, "name_clean"] + " " + df.loc[moved, "comment"].fillna("")).str.strip()
    df.loc[moved, "name_clean"] = ""

    # garbage names -> blank (comment kept)
    is_garbage = (df["name_clean"].str.match(GARBAGE_RE)
                  | df["name_clean"].str.match(r"^\W*$")
                  | df["name_clean"].str.match(ADDRESS_RE)
                  | df["name_clean"].str.fullmatch(r"(?i)none( none)?")
                  | df["name_clean"].str.contains(r"\d", regex=True)      # digits
                  | df["name_clean"].str.contains(r"[:\[\]<>|{}=~`@#$%^*]", regex=True)
                  | df["name_clean"].str.contains(
                      r"(?i)last updated|same as|adjourn|adopted|see speakers|"
                      r"see item|see previous|tape mal|no votes|"
                      r"commissioner[s]? (question|comment)|meeting minutes|"
                      r"acton\b|withdrawn|continuance|continued|"
                      r"live/work|rec/park|permit\b", regex=True)
                  | df["name_clean"].str.fullmatch(r"[A-Z][A-Z\s?'&,.-]{7,}")  # section headers
                  | df["name_clean"].str.match(r"^[a-z]")                  # fragments
                  | df["name_clean"].str.len().lt(3))
    df.loc[is_garbage, "name_clean"] = ""
    is_garbage = is_garbage | moved

    # single-token names are kept but flagged (can't distinguish person)
    df["name_single"] = ((df["name_clean"] != "")
                         & ~df["name_clean"].str.contains(" ")).astype(int)

    # anonymous speakers
    df["is_anonymous"] = (df["name_clean"].str.contains(ANON_RE) & (df["name_clean"] != "")).astype(int)

    # role-implied signs where the stenographer gave none
    for pat, sign in ROLE_SIGNS:
        m = df["sign"].isna() & df["name_clean"].str.contains(pat)
        df.loc[m, "sign"] = sign

    # titles
    df["title"] = df["name_clean"].str.extract(TITLE_RE, expand=False)
    df["name_clean"] = df["name_clean"].str.replace(TITLE_RE, "", regex=True).str.strip()

    # supervisors canonicalization (after title strip, "Supervisor X" -> title)
    sup_mask = df["title"].str.contains("Supervisor|Sup", case=False, na=False)
    df.loc[sup_mask, "name_clean"] = df.loc[sup_mask, "name_clean"].map(
        lambda x: SUPERVISORS.get(x, x))

    # anonymous placeholder names -> blank name, keep flag
    df.loc[df["is_anonymous"] == 1, "name_clean"] = ""

    # ------------------------------------------------ author typo lookups
    typo_map = load_typo_maps()
    hits = df["name_clean"].isin(typo_map)
    for old in df.loc[hits, "name_clean"].unique():
        merge_log.append({"variant": old, "canonical": typo_map[old],
                          "source": "author_lookup"})
    df["name_clean"] = df["name_clean"].map(lambda x: typo_map.get(x, x))

    # ------------------------------------------------ fuzzy dedup
    counts = df.loc[df["name_clean"] != "", "name_clean"].value_counts()
    auto, review = fuzzy_merges(counts)
    auto_map = {r["variant"]: r["canonical"] for r in auto}
    # resolve chains (a->b, b->c)
    for k in list(auto_map):
        v = auto_map[k]
        while v in auto_map:
            v = auto_map[v]
        auto_map[k] = v
    df["name_clean"] = df["name_clean"].map(lambda x: auto_map.get(x, x))
    for r in auto:
        merge_log.append({"variant": r["variant"], "canonical": auto_map[r["variant"]],
                          "source": f"fuzzy_d{r['dist']}"})

    # pure-noise rows: no name, no comment, no sign, not anonymous — these
    # carry no information (address fragments from mis-keyed Re: pairs etc.)
    noise = ((df["name_clean"] == "") & (df["sign"].isna())
             & (df["is_anonymous"] != 1)
             & (df["comment"].fillna("").str.len() < 3)
             & (df["same_as"].fillna("") == ""))
    n_noise = int(noise.sum())
    df = df[~noise]

    # ------------------------------------------------ outputs
    df.to_csv(OUT / "comments.csv", index=False)
    pd.DataFrame(merge_log).to_csv(VAL / "name_merge_log.csv", index=False)
    pd.DataFrame(review).sort_values(["ratio"], ascending=False).to_csv(
        VAL / "name_review.csv", index=False)

    named = df[df["name_clean"] != ""]
    with open(VAL / "name_report.txt", "w") as f:
        f.write(f"comment records: {len(df)}\n")
        f.write(f"with cleaned name: {len(named)}\n")
        f.write(f"unique names: {named['name_clean'].nunique()}\n")
        f.write(f"anonymous records: {int(df['is_anonymous'].sum())}\n")
        f.write(f"garbage names blanked: {int(is_garbage.sum())}\n")
        f.write(f"author-lookup merges applied: {sum(1 for m in merge_log if m['source'] == 'author_lookup')}\n")
        f.write(f"fuzzy auto-merges applied: {len(auto)}\n")
        f.write(f"fuzzy candidates for review: {len(review)}\n")
        f.write(f"records with sign: {int(df['sign'].notna().sum())}\n")
        f.write(f"records with role_title: {int((df['role_title'] != '').sum())}\n")
        f.write(f"records with organization: {int((df['organization'] != '').sum())}\n")
        f.write(f"noise rows dropped: {n_noise}\n")
    print(open(VAL / "name_report.txt").read())


if __name__ == "__main__":
    main()
