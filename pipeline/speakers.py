"""Split SPEAKERS blocks into (sign, name, comment) records.

Formats observed across 1998-2026:
  A. Sign-prefixed lines (2005+):   "+ Jane Doe – Project presentation"
  B. Parenthesized signs (2000s):   "(+) Jane Doe  concerns"
  C. Tone-group lists:              "In support: A, B. Opposed: C, D"
  D. Name / "Re:" pairs (1998-2003 general public comment)
  E. Plain comma lists (1998-2010): "Jane Doe, John Smith, ..."
  F. Unsigned "Name – comment" lines (2015-2018 staff-run items)
"""

import re

NBSP = " "

NONE_RE = re.compile(r"^\s*[-–—]?\s*(none\.?|n/?a)?\s*$", re.IGNORECASE)
SAME_AS_RE = re.compile(
    r"^\s*\(?\[?\s*(same\s+as|see\s+speakers?\s+(?:for|on)|see\s+item)\s*(.*)",
    re.IGNORECASE,
)

SIGN_LINE_RE = re.compile(r"^\s*(\+/-|\(\+\)|\(-\)|\(=\)|[+=−–-])\s+(?=\S)")
SIGN_CANON = {"(+)": "+", "(-)": "-", "(=)": "=", "−": "-", "–": "-", "—": "-"}

# name/comment separators, in priority order
SEP_RES = [
    re.compile(r"\s*[–—]\s*"),           # en/em dash, spaced or attached
    re.compile(r"\s+-\s+"),              # spaced hyphen
    re.compile(r"\s{2,}"),               # column gap (pdftotext -layout)
    re.compile(r",\s+(?=[a-z(])"),       # comma before lowercase (desc, not name)
]

TONE_GROUP_RE = re.compile(
    r"(?i)(in\s+(?:favor|support)[^:\n]{0,60}:|opposed?[^:\n]{0,25}:|"
    r"in\s+opposition[^:\n]{0,40}:|neutral:|support(?:ing)?\s+(?:the\s+)?project:)"
)

RE_PAIR_RE = re.compile(r"(?m)^\s*Re:\s*(.+)$")

NAME_STOP = set(
    "he she they it the this that these those a an is are was were and of to "
    "in for on with his her their its at as be been being have has had i we "
    "you my our your there here not no if but or so because about".split())


def is_name_like(s):
    """Heuristic: does this string look like a person's name (not a sentence)?"""
    s = str(s).strip().rstrip(".").strip()
    if not s or not s[0].isupper():
        return False
    toks = s.split()
    if not 1 <= len(toks) <= 6:
        return False
    if any(t.lower() in NAME_STOP for t in toks):
        return False
    caps = sum(1 for t in toks if t[0].isupper())
    return caps >= max(1, len(toks) - 1)


TITLE_RE = re.compile(
    r"^(Dr|Rev|Mr|Mrs|Prof|Ms|Lt|Fr|Capt|Father|Sup|Sarg|Reverend|Supervisor|"
    r"Captain|Commissioner|President|Secretary|Officer|Sgt)\.?\s+", re.IGNORECASE)


def _clean_block(block):
    if block is None:
        return ""
    b = block.replace(NBSP, " ")
    b = re.sub(r"\(s\)\s*:?", "", b, count=1) if b.lower().startswith("(s)") else b
    b = re.sub(r"\n[ \t]*:", ":", b)          # "Name\n: comment" -> "Name: comment"
    b = re.sub(r"(?m)^[\s?¿·•*_-]+$\n?", "", b)  # junk/mojibake-only lines
    b = re.sub(r"^[?¿\s]+", "", b)             # leading mojibake
    b = re.sub(r"[ \t]+\n", "\n", b)
    return b.strip()


def _split_name_comment(chunk):
    chunk = chunk.strip()
    # try separators on the first line; rest of lines are comment continuation
    lines = chunk.split("\n", 1)
    first, rest = lines[0], (lines[1].strip() if len(lines) > 1 else "")
    for sep in SEP_RES:
        m = sep.search(first)
        if m:
            name = first[:m.start()].strip()
            comment = (first[m.end():].strip() + " " + rest).strip()
            if 0 < len(name.split()) <= 6:
                return name, comment
    if 0 < len(first.split()) <= 6:
        return first.strip(), rest
    return chunk if not rest else first, rest


def _tone_from_group(label):
    low = label.lower()
    if "neutral" in low:
        return "="
    if re.search(r"opposed|opposition|favor of (?:the )?(dr|appeal)|support of (?:the )?(dr|appeal)", low):
        return "-"
    if "favor" in low or "support" in low:
        return "+"
    return None


def _split_list(text):
    """Split 'A, B, C and D' into names."""
    text = re.sub(r"\s+", " ", text).strip().rstrip(".")
    parts = re.split(r",|;|\band\b", text)
    return [p.strip() for p in parts if p.strip()]


def parse_speakers(block):
    """Return (records, method). records: list of dicts sign/name_raw/comment."""
    b = _clean_block(block)
    # a leading "RE: <topic>" header (general-public-comment narratives)
    # is context, not a speaker — strip it and note it on the records
    topic = None
    mre = re.match(r"^\s*RE?:\s*([^\n]*)\n+", b, re.IGNORECASE)
    if mre:
        topic = mre.group(1).strip()
        b = b[mre.end():].strip()
    recs, method = _parse_speakers(b)
    if topic:
        for r in recs:
            r["comment"] = (f"[Re: {topic}] " + r.get("comment", "")).strip()
    return recs, method


def _parse_speakers(b):
    if NONE_RE.match(b):
        return [], "none"
    # match "Same as ..." even when line-wraps split words ("S\nee Speakers...")
    flat = re.sub(r"\s+", " ", b)
    flat_nospace = re.sub(r"\s+", "", b[:40]).lower()
    if (SAME_AS_RE.match(flat)
            or flat_nospace.startswith(("sameas", "seespeakers", "seeitem"))):
        return [{"sign": None, "name_raw": "", "comment": "",
                 "same_as": flat[:120]}], "same_as"

    lines = [ln for ln in b.split("\n") if ln.strip()]

    # prose tone groups: "A and B spoke in opposition; C spoke in support"
    if re.search(r"(?i)spoke in (support|favor|opposition)", flat):
        segs = re.split(r";", flat)
        recs = []
        ok = True
        for seg in segs:
            gm = re.search(r"(?i)(?:spoke\s+)?in\s+(support|favor|opposition)(?:\s+of[^,]*)?", seg)
            if not gm:
                ok = False
                break
            sign = "+" if gm.group(1).lower() in ("support", "favor") else "-"
            names_part = seg[:gm.start()].strip(" ,;.")
            for nm in _split_list(names_part):
                if 1 <= len(nm.split()) <= 5:
                    recs.append({"sign": sign, "name_raw": nm, "comment": ""})
        if ok and recs:
            return recs, "tone_prose"

    # inline parenthesized signs "(+) A (-) B" take priority when repeated
    if len(re.findall(r"\((?:\+|-|=)\)", b)) >= 2:
        recs = []
        parts = re.split(r"\((\+|-|=)\)", b)
        for i in range(1, len(parts) - 1, 2):
            sign, chunk = parts[i], parts[i + 1].strip(" ,;\n")
            if not chunk:
                continue
            name, comment = _split_name_comment(chunk)
            recs.append({"sign": sign, "name_raw": name, "comment": comment})
        if recs:
            return recs, "sign_inline"

    # --- A/B: sign-prefixed entries -------------------------------------
    n_signed = sum(1 for ln in lines if SIGN_LINE_RE.match(ln))
    if n_signed >= 1 and n_signed >= 0.4 * len(lines):
        recs = []
        cur = None
        for ln in lines:
            sm = SIGN_LINE_RE.match(ln)
            if sm:
                sign = SIGN_CANON.get(sm.group(1), sm.group(1))
                name, comment = _split_name_comment(ln[sm.end():])
                # 2000s minutes use "- " both as a polarity sign and as a
                # bullet under a speaker; a "signed" line whose name reads as
                # a sentence is a bullet continuing the current speaker
                if not is_name_like(name):
                    text = ln[sm.end():].strip()
                    if cur is not None:
                        cur["comment"] = (cur["comment"] + " " + text).strip()
                    else:
                        recs.append({"sign": None, "name_raw": "", "comment": text})
                    continue
                if cur:
                    recs.append(cur)
                cur = {"sign": sign, "name_raw": name, "comment": comment}
            elif cur is not None:
                cur["comment"] = (cur["comment"] + " " + ln.strip()).strip()
            # leading unsigned lines before any sign: treat as unsigned entry
            else:
                name, comment = _split_name_comment(ln)
                recs.append({"sign": None, "name_raw": name, "comment": comment})
        if cur:
            recs.append(cur)
        return recs, "sign_lines"

    # inline parenthesized signs: "(+) A (-) B ..."
    if re.search(r"\((?:\+|-|=)\)", b):
        recs = []
        parts = re.split(r"\((\+|-|=)\)", b)
        for i in range(1, len(parts) - 1, 2):
            sign, chunk = parts[i], parts[i + 1].strip(" ,;\n")
            if not chunk:
                continue
            name, comment = _split_name_comment(chunk)
            recs.append({"sign": sign, "name_raw": name, "comment": comment})
        if recs:
            return recs, "sign_inline"

    # --- C: tone-group lists ---------------------------------------------
    groups = list(TONE_GROUP_RE.finditer(b))
    if groups:
        recs = []
        for i, g in enumerate(groups):
            end = groups[i + 1].start() if i + 1 < len(groups) else len(b)
            sign = _tone_from_group(g.group(1))
            for nm in _split_list(b[g.end():end]):
                if len(nm.split()) <= 6:
                    recs.append({"sign": sign, "name_raw": nm, "comment": ""})
        if recs:
            return recs, "tone_groups"

    # --- D: Name / "Re:" pairs --------------------------------------------
    if RE_PAIR_RE.search(b):
        recs = []
        cur_names = []
        for ln in lines:
            rm = re.match(r"\s*Re:\s*(.*)", ln)
            if rm:
                for nm in cur_names:
                    recs.append({"sign": None, "name_raw": nm,
                                 "comment": "Re: " + rm.group(1).strip()})
                cur_names = []
            else:
                cur_names.extend(n for n in _split_list(ln) if n)
        for nm in cur_names:
            recs.append({"sign": None, "name_raw": nm, "comment": ""})
        return recs, "re_pairs"

    # --- E: comma list (entries may carry "Name – Org" suffixes) -----------
    joined = re.sub(r"\s*\n\s*", " ", b)
    n_dash = len(re.findall(r"\s[–—-]\s", joined))
    if joined.count(",") >= 1 and joined.count(",") >= 2 * n_dash:
        parts = [p for p in re.split(r",|;", joined) if p.strip()]
        recs = []
        for p in parts:
            p = p.strip()
            if re.match(r"(?i)^and\s+", p):
                p = p[4:].strip()
            dm = re.split(r"\s+[–—-]\s+", p, maxsplit=1)
            nm, extra = (dm[0].strip(), dm[1].strip()) if len(dm) == 2 else (p, "")
            if not nm:
                continue
            # descriptor fragments attach to the previous speaker
            if recs and (re.match(r"(?i)^(spoke|representing|in (support|favor|opposition)|on behalf)", nm)
                         or nm[0].islower()):
                recs[-1]["comment"] = (recs[-1]["comment"] + " " + p).strip()
                continue
            recs.append({"sign": None, "name_raw": nm, "comment": extra})
        short = [r for r in recs if 1 <= len(r["name_raw"].split()) <= 4]
        if recs and len(short) / len(recs) >= 0.7:
            return recs, "comma_list"

    # --- name-colon pairs: "Sue Hestor: Requested continuance..." ----------
    colon_starts = [ln for ln in lines
                    if re.match(r"^[A-Z][A-Za-z.' -]{2,40}:\s", ln)
                    and len(ln.split(":")[0].split()) <= 4
                    and not ln.split(":")[0].isupper()]
    if len(colon_starts) >= 2:
        recs, cur = [], None
        for ln in lines:
            m2 = re.match(r"^([A-Z][A-Za-z.' -]{2,40}):\s*(.*)", ln)
            if m2 and len(m2.group(1).split()) <= 4 and not m2.group(1).isupper():
                if cur:
                    recs.append(cur)
                cur = {"sign": None, "name_raw": m2.group(1).strip(),
                       "comment": m2.group(2).strip()}
            elif cur is not None:
                cur["comment"] = (cur["comment"] + " " + ln.strip()).strip()
        if cur:
            recs.append(cur)
        if recs:
            return recs, "name_colon"

    # --- F: unsigned "Name – comment" lines --------------------------------
    # entry-start lines look like "First Last – ..."; other lines are
    # wrapped continuations of the previous entry's comment
    entry_starts = [i for i, ln in enumerate(lines)
                    if re.match(r"^\s*[A-Z][A-Za-z.'()-]*([ \t]+\S+){0,5}\s*[–—]\s", ln)
                    or re.match(r"^\s*[A-Z][A-Za-z.'()-]*([ \t]+[A-Z][A-Za-z.'()-]*){0,4},?\s+-\s", ln)]
    if len(entry_starts) >= 2 or (len(entry_starts) == 1 and entry_starts[0] == 0):
        recs = []
        for k, si in enumerate(entry_starts):
            end = entry_starts[k + 1] if k + 1 < len(entry_starts) else len(lines)
            chunk = "\n".join(lines[si:end])
            name, comment = _split_name_comment(chunk.replace("\n", " "))
            recs.append({"sign": None, "name_raw": name, "comment": comment})
        # leading lines before the first entry: try to keep as an entry
        if entry_starts[0] > 0:
            head = " ".join(lines[:entry_starts[0]])
            name, comment = _split_name_comment(head)
            if 1 <= len(name.split()) <= 5:
                recs.insert(0, {"sign": None, "name_raw": name, "comment": comment})
        return recs, "dash_lines"

    dash_lines = [ln for ln in lines if re.search(r"\s[–—-]\s", ln)]
    if lines and len(dash_lines) >= 0.5 * len(lines):
        recs = []
        cur = None
        for ln in lines:
            if re.search(r"\s[–—-]\s", ln):
                if cur:
                    recs.append(cur)
                name, comment = _split_name_comment(ln)
                cur = {"sign": None, "name_raw": name, "comment": comment}
            elif cur is not None:
                cur["comment"] = (cur["comment"] + " " + ln.strip()).strip()
            else:
                name, comment = _split_name_comment(ln)
                cur = {"sign": None, "name_raw": name, "comment": comment}
        if cur:
            recs.append(cur)
        ok = [r for r in recs if 1 <= len(r["name_raw"].split()) <= 5]
        if recs and len(ok) / len(recs) >= 0.6:
            return recs, "dash_lines"

    # --- single name -------------------------------------------------------
    if len(joined.split()) <= 5 and joined and joined[0].isupper():
        return [{"sign": None, "name_raw": joined.strip(" ,."), "comment": ""}], "single"

    # --- narrative: first line is a plausible name, rest is the comment ----
    if lines:
        first = lines[0].strip().rstrip(",")
        first_name_part = first.split(",")[0]
        if (1 <= len(first_name_part.split()) <= 5 and first[0].isupper()
                and not first.isupper() and len(lines) > 1):
            return [{"sign": None, "name_raw": first,
                     "comment": " ".join(ln.strip() for ln in lines[1:])}], "first_line_name"

    return [{"sign": None, "name_raw": "", "comment": b}], "unparsed"


if __name__ == "__main__":
    tests = [
        "+ Vika Eissen – Project presentation",
        "= Sophie Hayward, MOH – Response to questions\n= Sue Hestor – Critical",
        "None",
        "Same as Item 9a.",
        "Mr. Cassidy, Joe Mott, Sue Hestor",
        "Brett Gladstone\n\nRe: 1220 Jones Street\n\nCurtis Davis\n\nRe: 75 Pleasant",
        "In support: Al B, Cy D. Opposed: Ed F",
        "(+) Jane Doe (-) John Smith  too tall",
        "Jim Meko – Intent of the code provisions",
    ]
    for t in tests:
        recs, method = parse_speakers(t)
        print(method, "->", [(r.get("sign"), r["name_raw"], r["comment"][:30]) for r in recs])
