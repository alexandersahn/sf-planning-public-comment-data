"""Parse SF Planning Commission meeting minutes into structured records.

Handles three source formats:
  1. 1998-2014 mirrored HTML (S3 meetingarchive; often several meetings per page)
  2. 2015-2018 sfgov.org/sfplanningarchive HTML (one meeting per page)
  3. 2019-2026 PDFs (extracted with `pdftotext -layout`)

Output: one row per agenda item with meeting metadata, section, item number,
record id, item text, and the SPEAKERS / ACTION / vote blocks.
"""

import re
import subprocess
import unicodedata
from pathlib import Path

from bs4 import BeautifulSoup

# ---------------------------------------------------------------- text extraction

def extract_text(path):
    path = Path(path)
    # some archive URLs serve PDFs from .html-looking paths — sniff magic bytes
    with open(path, "rb") as f:
        magic = f.read(5)
    if path.suffix.lower() == ".pdf" or magic == b"%PDF-":
        out = subprocess.run(
            ["pdftotext", "-layout", "-enc", "UTF-8", str(path), "-"],
            capture_output=True, text=True, timeout=120,
        )
        text = out.stdout
    else:
        soup = BeautifulSoup(path.read_text(errors="replace"), "lxml")
        for tag in soup(["script", "style"]):
            tag.decompose()
        text = soup.get_text("\n")
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("’", "'").replace("‘", "'")
    text = text.replace("“", '"').replace("”", '"')
    text = text.replace("\r", "")
    # strip page/site furniture (repeated on every page or in mirror footers)
    text = re.sub(r"(?m)^.*Page \d+ of \d+.*$", "", text)
    text = re.sub(r"(?m)^\s*Last updated:.*$", "", text)
    text = re.sub(r"(?m)^\x0c?San Francisco Planning Commission\s+\w+day, [A-Z][a-z]+ \d{1,2}, \d{4}\s*$", "", text)
    text = text.replace("\x0c", "\n")
    # mojibake: runs of '?' from broken encodings in the mirrored pages
    text = re.sub(r"\?{3,}", " ", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


# ---------------------------------------------------------------- meeting splitting

# A meeting document starts with one of these headers.
# All-caps "MINUTES OF ..." variants are matched case-sensitively so that
# "Draft Minutes of Regular Meeting of ..." (minutes-adoption agenda items)
# do not split a meeting in two.
MEETING_START = re.compile(
    r"(?:MINUTES\s+OF\s+(?:MEETING|SPECIAL|JOINT|REGULAR|THE\s+REGULAR|THE\s+SPECIAL)[^\n]*"
    r"|SAN\s+FRANCISCO\s*\n+\s*PLANNING\s+COMMISSION(?:\s*\n+[^\n]*){0,4}?\s*\n+\s*"
    r"(?:Meeting\s+Minutes|Minutes\s+of\s+(?:the\s+)?Meeting))"
)


def split_meetings(text):
    """Split a document that may contain several meetings into per-meeting text."""
    starts = [m.start() for m in MEETING_START.finditer(text)]
    if not starts:
        return [text]
    docs = []
    for i, s in enumerate(starts):
        e = starts[i + 1] if i + 1 < len(starts) else len(text)
        docs.append(text[s:e])
    return docs


# ---------------------------------------------------------------- meeting metadata

DATE_RE = re.compile(
    r"(?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day\s*,?\s*\n?\s*"
    r"([A-Z][a-z]+|[A-Z]+)\s+(\d{1,2})\s*,?\s+(\d{4})",
    re.IGNORECASE,
)
MONTHS = {m.lower(): i + 1 for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"])}
# common typos observed in the minutes
MONTH_FIXES = {"janaury": "january", "feburary": "february", "spetember": "september",
               "septemeber": "september", "ocotber": "october"}

TIME_RE = re.compile(r"(\d{1,2}):(\d{2})\s*([AaPp])\.?\s?[Mm]\.?")
ADJOURN_RE = re.compile(
    r"ADJOURN(?:MENT|ED)?[^\n]{0,120}?(\d{1,2}):(\d{2})\s*([AaPp])\.?\s?[Mm]\.?",
    re.IGNORECASE | re.DOTALL,
)


def _norm_time(h, m, ap):
    h = int(h) % 12
    if ap.lower() == "p":
        h += 12
    return f"{h:02d}:{m}"


STAFF_ATTEND_RE = re.compile(
    r"STAFF\s+IN\s+ATTENDANCE\s*:?\s*(.*?)(?:\n\s*\n|SPEAKER\s+KEY|$)",
    re.IGNORECASE | re.DOTALL)
COMMISSIONERS_RE = re.compile(
    r"(?:COMMISSIONERS?\s+PRESENT|^PRESENT)\s*:\s*(.*?)(?:\n\s*\n|COMMISSIONERS?\s+ABSENT|ABSENT)",
    re.IGNORECASE | re.DOTALL | re.MULTILINE)


def parse_meeting_meta(text):
    head = text[:4000]
    meta = {"meeting_date": None, "start_time": None, "end_time": None,
            "meeting_type": None, "staff_in_attendance": None,
            "commissioners_present": None}
    sm = STAFF_ATTEND_RE.search(head)
    if sm:
        meta["staff_in_attendance"] = re.sub(r"\s+", " ", sm.group(1)).strip()[:1500]
    cm = COMMISSIONERS_RE.search(head)
    if cm:
        meta["commissioners_present"] = re.sub(r"\s+", " ", cm.group(1)).strip()[:500]
    m = DATE_RE.search(head)
    if not m:
        # fallback: bare "MONTH DD, YYYY" near top
        m = re.search(r"([A-Z][A-Za-z]+)\s+(\d{1,2})\s*,\s*(\d{4})", head)
    if m:
        mon = m.group(1).lower()
        mon = MONTH_FIXES.get(mon, mon)
        if mon in MONTHS:
            meta["meeting_date"] = f"{m.group(3)}-{MONTHS[mon]:02d}-{int(m.group(2)):02d}"
        after = head[m.end():m.end() + 200]
        t = TIME_RE.search(after)
        if t:
            meta["start_time"] = _norm_time(*t.groups())
    if re.search(r"SPECIAL", head[:600], re.IGNORECASE):
        meta["meeting_type"] = "special"
    elif re.search(r"JOINT", head[:600], re.IGNORECASE):
        meta["meeting_type"] = "joint"
    else:
        meta["meeting_type"] = "regular"
    a = ADJOURN_RE.search(text[-4000:]) or ADJOURN_RE.search(text)
    if a:
        meta["end_time"] = _norm_time(*a.groups())
    return meta


# ---------------------------------------------------------------- sections & items

# "A." then title in caps — same line, next line, or separated by a blank line.
GAP = r"[ \t]*(?:\n[ \t]*){0,2}"
SECTION_RE = re.compile(
    r"(?m)^[ \t]*([A-Z])\." + GAP +
    r"([A-Z][A-Z0-9 \t'\",&/()–—-]{6,}?)[ \t]*$"
)
# some eras (mid-2000s) drop the letter prefix entirely
SECTION_NOLETTER_RE = re.compile(
    r"(?m)^[ \t]*([A-Z][A-Z0-9 \t'\",&/()–—-]{10,90}?)[ \t]*$"
)
# a real agenda section title must start with one of these
SECTION_VOCAB = re.compile(
    r"^(CONSIDERATION|ITEMS?\b|COMMISSION\b|COMMISSIONERS|DIRECTOR|DEPARTMENT|"
    r"GENERAL\s+PUBLIC|PUBLIC\s+COMMENT|REGULAR\s+CALENDAR|"
    r"CONSENT\s+CALENDAR|DISCRETIONARY|SPECIAL\s+DISCRETIONARY|CLOSED\s+SESSION|"
    r"SPECIAL\s+CALENDAR|THE\s+DRAFT\s+MINUTES|CONSIDERATION\s+OF\s+FINDINGS)"
)
MAX_SECTION_TITLE = 80

# item start: "12. 2024-005242CUA" | "1. 97.669C" | "5a. 2005.0999E";
# number and id may be separated by a blank line (2015-2018 HTML).
ITEM_RE = re.compile(
    r"(?m)^[ \t]*(\d{1,2}[a-z]?)\.?" + GAP +
    r"((?:19|20)?\d{2,4}[.-]\d{3,6}[A-Za-z!@]*(?:-\d+)?)"
)
# item with no case id, identified by staff contact: "5. (J. IONIN: (415) 558-6309)"
ITEM_NOID_RE = re.compile(
    r"(?m)^[ \t]*(\d{1,2}[a-z]?)\." + GAP +
    r"\(?[A-Z][a-zA-Z]*\.?\s*[A-Z]+\s*:\s*\(\d{3}\)"
)
# administrative items with a caps title and no case id:
# "3. LAND ACKNOWLEDGEMENT", "4. CONSIDERATION OF ADOPTION:"
ITEM_ADMIN_RE = re.compile(
    r"(?m)^[ \t]*(\d{1,2}[a-z]?)\." + GAP +
    r"([A-Z][A-Z0-9 \t'\",:/&()–—-]{5,})[ \t]*$"
)

# The label and its colon can be separated by blank lines ("ACTION\n\n:"),
# appear in mixed case ("Adjournment:"), or carry typos ("ACTON:").
BLOCK_RE = re.compile(
    r"(?m)^[ \t]*(SPEAKERS?|SPEAKER\(S\)|ACTIONS?|ACTON|ACTION\(S\)|APPROVED|"
    r"AYES?|NO?ES|NAYE?S?|ABSENT|RECUSED?|EXCUSED|PRESENT|MOTIONS?|"
    r"RESOLUTIONS?|DRA|NOTE|RESULT|ADJOURNMENT|ADOPTED)"
    r"[ \t]*(?:\n[ \t]*){0,2}:",
    re.IGNORECASE,
)
# mid-2000s minutes drop the colon: the label sits alone on a line
BLOCK_NOCOLON_RE = re.compile(
    r"(?m)^[ \t]*(SPEAKERS?|SPEAKER\(S\)|ACTION|AYES|NAYES|NOES|ABSENT|"
    r"MOTION|RESOLUTION|EXCUSED|RECUSED)[ \t]*$")
BLOCK_CANON = {
    "SPEAKER": "SPEAKERS", "SPEAKERS": "SPEAKERS", "SPEAKER(S)": "SPEAKERS",
    "NOES": "NAYES", "NES": "NAYES", "NAY": "NAYES", "NAYS": "NAYES", "NAYES": "NAYES",
    "AYE": "AYES",
    "RECUSE": "RECUSED", "RECUSED": "RECUSED",
    "ACTON": "ACTION", "ACTIONS": "ACTION", "ACTION(S)": "ACTION",
    "APPROVED": "ACTION", "MOTIONS": "MOTION", "RESOLUTIONS": "RESOLUTION",
}


CAPS_LINE_RE = re.compile(r"^[ \t]*([A-Z][A-Z0-9 \t'\",\.:&/()–—-]{2,90})[ \t]*$")
LETTER_ONLY_RE = re.compile(r"^[ \t]*([A-Z])\.[ \t]*$")
LETTER_TITLE_RE = re.compile(r"^[ \t]*([A-Z])\.[ \t]+([A-Z][A-Z0-9 \t'\",&/()–—-]{2,90})[ \t]*$")


def find_sections(text):
    """Locate agenda section headers, joining titles wrapped across lines.

    Handles: "A. REGULAR CALENDAR" (same line), "A." + title on next line(s),
    and unlettered wrapped headers like "REGULAR\nCALENDAR" (mid-2000s HTML).
    """
    lines = text.split("\n")
    # positions of line starts
    pos = [0]
    for ln in lines[:-1]:
        pos.append(pos[-1] + len(ln) + 1)

    sections = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        letter, first, start = None, None, pos[i]
        m = LETTER_TITLE_RE.match(ln)
        if m:
            letter, first = m.group(1), m.group(2)
        else:
            m = LETTER_ONLY_RE.match(ln)
            if m:
                # letter alone; title on the next non-empty caps line
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if j < len(lines):
                    m2 = CAPS_LINE_RE.match(lines[j])
                    if m2:
                        letter, first = m.group(1), m2.group(1)
                        i = j
            else:
                m3 = CAPS_LINE_RE.match(ln)
                if m3 and len(m3.group(1).strip()) >= 4:
                    letter, first = "", m3.group(1)
        if first is None:
            i += 1
            continue
        # join immediately-following caps continuation lines (wrapped titles)
        title_parts = [first.strip()]
        j = i + 1
        while j < len(lines) and len(title_parts) < 3:
            nxt = lines[j]
            if not nxt.strip():
                break
            m4 = CAPS_LINE_RE.match(nxt)
            if not m4:
                break
            title_parts.append(m4.group(1).strip())
            j += 1
        title = re.sub(r"\s+", " ", " ".join(title_parts)).strip()
        if SECTION_VOCAB.match(title) and len(title) <= MAX_SECTION_TITLE:
            sections.append((start, letter or "", title))
            i = j
        else:
            i += 1
    return sections


def parse_blocks(item_text):
    """Split an item's text into description + labeled blocks."""
    matches = list(BLOCK_RE.finditer(item_text))
    starts = set(m.start() for m in matches)
    for m in BLOCK_NOCOLON_RE.finditer(item_text):
        if m.start() not in starts:
            matches.append(m)
    matches.sort(key=lambda m: m.start())
    blocks = {}
    desc_end = matches[0].start() if matches else len(item_text)
    blocks["_description"] = item_text[:desc_end].strip()
    for i, m in enumerate(matches):
        raw = m.group(1).upper()
        key = BLOCK_CANON.get(raw, raw)
        end = matches[i + 1].start() if i + 1 < len(matches) else len(item_text)
        val = item_text[m.end():end].strip()
        # "APPROVED: +5 -0" is the action itself, not a label for it
        if raw == "APPROVED":
            val = ("Approved " + val).strip()
        if key in blocks and blocks[key]:
            blocks[key] += "\n" + val
        else:
            blocks[key] = val
    return blocks


def parse_meeting(text, source_file=""):
    """Parse one meeting's text into a list of item dicts."""
    meta = parse_meeting_meta(text)

    sections = find_sections(text)
    items = [(m.start(), m.group(1), m.group(2)) for m in ITEM_RE.finditer(text)]
    taken = set(it[0] for it in items)
    for m in ITEM_NOID_RE.finditer(text):
        if m.start() not in taken:
            items.append((m.start(), m.group(1), ""))
            taken.add(m.start())
    sec_positions = set(s[0] for s in sections)
    for m in ITEM_ADMIN_RE.finditer(text):
        if m.start() not in taken and m.start() not in sec_positions:
            items.append((m.start(), m.group(1), ""))
            taken.add(m.start())
    # drop "items" that appear before the first section (calendar refs in preamble)
    first_sec = sections[0][0] if sections else 0
    items = sorted([it for it in items if it[0] >= first_sec])

    boundaries = sorted(
        [(pos, "section", letter, title) for pos, letter, title in sections]
        + [(pos, "item", num, rid) for pos, num, rid in items]
    )

    rows = []
    cur_section = None
    cur_letter = None
    for i, b in enumerate(boundaries):
        pos, kind, a, bb = b
        end = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(text)
        if kind == "section":
            cur_letter, cur_section = a, bb
            # section-level content with no numbered item (e.g. general public comment)
            content = text[pos:end]
            content_body = SECTION_RE.sub("", content, count=1).strip()
            nxt = boundaries[i + 1] if i + 1 < len(boundaries) else None
            if content_body and (nxt is None or nxt[1] == "section"):
                blocks = parse_blocks(content_body)
                rows.append({**meta, "file": source_file,
                             "section_letter": cur_letter, "section": cur_section,
                             "item_num": "", "record_id": "",
                             "item_text": blocks.pop("_description"), **blocks})
        else:
            blocks = parse_blocks(text[pos:end])
            rows.append({**meta, "file": source_file,
                         "section_letter": cur_letter, "section": cur_section,
                         "item_num": a, "record_id": bb,
                         "item_text": blocks.pop("_description"), **blocks})
    return rows


def parse_file(path):
    text = extract_text(path)
    rows = []
    for doc in split_meetings(text):
        rows.extend(parse_meeting(doc, source_file=Path(path).name))
    return rows


if __name__ == "__main__":
    import json
    import sys
    for p in sys.argv[1:]:
        rows = parse_file(p)
        print(f"=== {p}: {len(rows)} items")
        for r in rows[:4]:
            print(json.dumps({k: (v[:100] if isinstance(v, str) else v)
                              for k, v in r.items()}, indent=1))
