"""Build the public-facing site from the release tables.

Reads public/comments.csv and public/items.csv.gz, plus the coded email
corpus, and writes a static site: one page per project, a client-side
search index, a data download, and an about page.

There are no pages for individual commenters, and names are not searchable.
Names appear beside the comments they made on a project, as the minutes and
packets already publish them, but the site does not assemble a per-person
dossier. See the note above the project-page section.

Usage:
    python site/build_site.py [--out DIR] [--emails CSV]

The email corpus is not in this repository — it is produced by the
prospective_threats project and exported with the columns listed in
EMAIL_COLS. Point --emails at that export, or set SFPC_EMAILS.
"""

import argparse
import collections
import html
import json
import os
import pickle
import re
import shutil
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))

ap = argparse.ArgumentParser()
ap.add_argument("--out", default=os.path.join(ROOT, "site", "_build"))
args = ap.parse_args()

OUT = args.out
os.makedirs(OUT, exist_ok=True)
for _e in os.listdir(OUT):
    if _e == ".git":
        continue
    _t = os.path.join(OUT, _e)
    shutil.rmtree(_t, ignore_errors=True) if os.path.isdir(_t) else os.remove(_t)
os.makedirs(OUT + "/projects", exist_ok=True)

# Both channels come from the release. They used to come from two places —
# spoken from here, written from a CSV exported by hand out of another
# project — which is why the site and the published data disagreed.
_all = pd.read_csv(os.path.join(ROOT, "public", "comments.csv"), low_memory=False)
it = pd.read_csv(os.path.join(ROOT, "public", "items.csv.gz"), low_memory=False)
sp = _all[_all["channel"] == "spoken"].copy()
em = _all[_all["channel"] == "email"].copy()
em["body"] = em["text"]
print(f"release: {len(sp):,} spoken, {len(em):,} written")

def _n(s):
    s = str(s or "").lower().strip()
    s = re.sub(r"[^a-z\s'-]", "", s)
    return re.sub(r"\s+", " ", s).strip()

# The curated rosters carry hand-collected alternate spellings. They are the
# strongest identity evidence available, and the channels disagree constantly:
# the minutes say "David Brockman", the packets say "David Broockman". Without
# this the same person lands on two pages.
from rosters import CURATED  # noqa: E402

ALIAS = {}
for _role, _people in CURATED.items():
    for _canon, _alts in _people.items():
        for _a in [_canon] + list(_alts):
            ALIAS[_n(_a)] = _n(_canon)

_CAMEL = re.compile(r"^([A-Z][a-z]+)([A-Z][a-z].*)$")


def norm(s):
    """Normalise, splitting run-together names and applying curated aliases."""
    raw = str(s or "").strip()
    m = _CAMEL.match(raw)                    # "SonjaTranss" -> "Sonja Transs"
    if m:
        raw = m.group(1) + " " + m.group(2)
    k = _n(raw)
    return ALIAS.get(k, k)

# id_parent already ships on the release
sp["year"] = pd.to_datetime(sp.meeting_date, errors="coerce").dt.year
em["year"] = pd.to_datetime(em.meeting_date, errors="coerce").dt.year
# 157 speakers are recorded under a bare role label — "Project Sponsor",
# "Requestor", "Project Architect" — and is_anonymous is 0 on every one, so
# the pipeline treats them as named people. They are as anonymous as
# "Speaker". Where a real name is attached ("Jerry -- Project Sponsor"),
# recover the name and drop the role.
ROLE_ONLY = re.compile(
    r"^\s*(co-)?(project |property |building |discretionary review )?"
    r"(sponsor|architect|owner|developer|team|representative|requestor|"
    r"applicant|consultant|engineer|planner|contractor|speaker|staff)s?"
    r"('s)?\s*(representative)?\s*$", re.I)
ROLE_SUFFIX = re.compile(
    r"\s*[-–—,]+\s*(co-)?(project |property |building |discretionary review )?"
    r"(sponsor|architect|owner|developer|requestor|applicant)s?\s*$", re.I)

_raw = sp.name_clean.fillna("")
_stripped = _raw.str.replace(ROLE_SUFFIX, "", regex=True).str.strip()
_is_role = _stripped.str.match(ROLE_ONLY) | _raw.str.match(ROLE_ONLY)
sp["role_label"] = _raw.where(_is_role).str.strip()
sp.loc[_is_role, "is_anonymous"] = 1
sp["name_clean"] = _stripped.where(~_is_role)

sp["n"] = sp.name_clean.map(norm)
em["n"] = em.name_clean.map(norm)

# ------------------------------------------------------------- filters
# Staff reports and presentations are the department talking to the
# commission, not public comment on a project.
STAFF_RE = r"^\s*(staff\s+(report|presentation)|presentation|response to comments)"
drop_staff = ((sp.is_staff == 1) | (sp.role_long == "Planning Staff")
              | sp.comment.fillna("").str.match(STAFF_RE, case=False))
n_staff = int(drop_staff.sum())
sp = sp[~drop_staff]

# Sender addresses are not in the release, so there is no domain to show or
# filter on; city correspondence is already excluded upstream. Messages whose
# sender name never got cleaned keep their comment but are grouped per sender
# so they never pool into one fictitious person.
em["domain"] = None
em["unnamed"] = em.name_clean.isna()
em["name_clean"] = em.name_clean.fillna("(name not recorded)")
em["anon_key"] = "anon:" + em.sender_id.fillna("unknown").astype(str)
n_gov = 0

SIGN = {"+": "support", "-": "oppose", "=": "neutral"}
a = pd.DataFrame({
    "unnamed": False, "anon_key": None,
    "channel": "spoken", "name": sp.name_clean,
    "n": sp.commenter_id.fillna(sp["n"]),
    "id_parent": sp.id_parent, "date": sp.meeting_date, "year": sp.year,
    "role_long": sp.role_long, "position": sp.sign.fillna(sp.sign_imputed).map(SIGN),
    "text": sp.comment, "subject": None, "domain": None,
    "campaign": None, "campaign_name": None,
})
# Campaign grouping is computed in pipeline/build_emails.py and shipped on
# the release, so the site and the data cannot disagree about what counts as
# a campaign.
em["campaign_label"] = em["campaign"]

b = pd.DataFrame({
    "channel": "email", "name": em.name_clean,
    "n": em.commenter_id.fillna(em["n"]),
    "id_parent": em.id_parent, "date": em.meeting_date, "year": em.year,
    "role_long": None, "position": em.position, "text": em.body,
    "subject": em.subject, "domain": em.domain,
    "campaign": em.campaign, "campaign_name": em.campaign_label,
    "unnamed": em.unnamed, "anon_key": em.anon_key,
})
C = pd.concat([a, b], ignore_index=True)
C = C[(C.n.str.split().str.len() >= 2) | C.unnamed.fillna(False)]

# ------------------------------------------------------------- dedup
# One agenda item spanning several case suffixes (SHD/ENV/DNX/CUA/OFA) or
# sub-items (1a, 1b, 2a...) fans the same speaker list across every row, and
# 456 item slots are parsed twice under two section_groups. Anastasia
# Yovanopoulos speaking once on 30 Van Ness became 14 rows. Collapse to one
# comment per person per project per hearing per text.
pre = len(C)
C = C.drop_duplicates(["channel", "n", "id_parent", "date", "text"])
n_dedup = pre - len(C)

# ------------------------------------------------------- project titles
ADDR_LINE = re.compile(r"^\d{1,5}(\s*[-–]\s*\d{1,5})?\s+[A-Z0-9]")
INITIALS = re.compile(r"\b[A-Z]\.\s*[A-Z][a-z]+")


def _caps_share(s):
    letters = [c for c in s if c.isalpha()]
    return sum(c.isupper() for c in letters) / len(letters) if letters else 0


def clean_title(t):
    """Pull a display name out of the agenda item text.

    The minutes set item titles and addresses in caps on their own line,
    after the case number and the staff-contact parenthetical, so this works
    line by line — collapsing whitespace first destroys exactly the structure
    that identifies a title. A line is only accepted if it still reads like a
    title: predominantly uppercase, or starting with a street number. Without
    that gate every project resolves, but three quarters of them resolve to a
    mid-sentence fragment ("Street", "and would include"), and a wrong title
    is worse than an honest case number.
    """
    if not isinstance(t, str):
        return None
    for ln in t.split("\n"):
        ln = re.sub(r"\([^)]*\d{3}[^)]*\)", "", ln)      # (J. LAU: 415-...)
        ln = re.sub(r"\b\d{3,4}[-.]\d{3,6}\w*\b", "", ln)  # case numbers
        ln = re.sub(r"^\s*\d+[a-z]?\.\s*", "", ln).strip(" .,:;-–—/")
        if len(ln) < 8 or not re.search(r"[A-Za-z]{3}", ln):
            continue
        head = re.split(r"\s+[–—]\s+|\s+-\s+", ln)[0].strip(" .,:;-–—/")
        if len(head) < 8 or len(head.split()) < 2:
            continue
        if ":" in head or INITIALS.search(head):           # staff name leftovers
            continue
        if _caps_share(head) >= 0.85 or ADDR_LINE.match(head):
            return head.title() if head.isupper() else head
    return None


pmeta = (it[it.id_parent.notna()].sort_values("meeting_date")
         .groupby("id_parent").agg(title=("prj_project_name", "last"),
                                   addr=("site_address", "last"),
                                   action=("action_final", "last"),
                                   action_date=("meeting_date", "last"),
                                   text=("item_text", "first")))

def ptitle(i):
    if i not in pmeta.index:
        return str(i)
    r = pmeta.loc[i]
    for v in (r.title, r.addr):
        if pd.notna(v) and str(v).strip():
            return str(v)
    return clean_title(r.text) or str(i)

# ------------------------------------------------- identity resolution
# Resolved once, in pipeline/resolve_commenters.py, and shipped as
# commenter_id on the release. Recomputing it here is what let the
# repository and the site report different numbers of participants.
# commenter_id is already the key: the channel frames set "n" from it
n_merged = 0

# Case roles describe a relationship to one item, never a standing
# affiliation — same exclusion as rosters.PROPAGATABLE_ROLES.
CASE_ROLES = {"Project Team", "DR Team", "Legal", "Planning Staff", "Commissioner"}
_aff = C[C.role_long.notna() & ~C.role_long.isin(CASE_ROLES)]
roles = _aff.groupby("n").role_long.agg(lambda s: s.value_counts().index[0]).to_dict()
caserole = (C[C.role_long.isin(CASE_ROLES)].groupby(["n", "role_long"]).size()
            .reset_index(name="k").sort_values("k", ascending=False)
            .groupby("n").first().to_dict("index"))

# Spellings the evidence did not support merging were simply never unioned,
# so they remain separate participants. The tier is internal and never shown.
C["key"] = C["n"].where(~C.unnamed.fillna(False), C.anon_key)
C["cid"] = ["k%d" % i for i in range(len(C))]
C["comment_id"] = C["cid"]

CANON_DISPLAY = {}
for _role, _people in CURATED.items():
    for _canon in _people:
        CANON_DISPLAY[norm(_canon)] = _canon

people = C.groupby("key").agg(
    name=("name", lambda s: s.value_counts().index[0]), n_all=("channel", "size"),
    n_sp=("channel", lambda s: (s == "spoken").sum()),
    n_em=("channel", lambda s: (s == "email").sum()),
    n_proj=("id_parent", lambda s: s.dropna().nunique()),
    y0=("year", "min"), y1=("year", "max"))
people["name"] = [CANON_DISPLAY.get(k, nm) for k, nm in zip(people.index, people["name"])]
# a person page needs a name; the nameless 2024 senders stay on project pages
PP = people[(people.n_all >= 2) & ~people.index.astype(str).str.startswith("anon:")]
PP = PP.sort_values("n_all", ascending=False)
pid = {k: re.sub(r"[^a-z0-9-]", "-", k).strip("-") for k in PP.index}

proj = C[C.id_parent.notna()].groupby("id_parent").agg(
    n_all=("channel", "size"), n_sp=("channel", lambda s: (s == "spoken").sum()),
    n_em=("channel", lambda s: (s == "email").sum()),
    y0=("year", "min"), y1=("year", "max")).join(pmeta[["action", "action_date"]])
PR = proj.sort_values("n_all", ascending=False)

# ---------------------------------------------------------------- html
CSS = """
:root{--ink:#1F2A36;--muted:#5B6570;--line:#E4DFD6;--bg:#FBFAF8;--card:#fff;
--blue:#2A6FB5;--orange:#D9622B;--green:#2E7D4F;--red:#C23B32;--accent:#8C3A2B;
--grey:#9AA2AA}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:16px/1.55 -apple-system,BlinkMacSystemFont,"Helvetica Neue",Arial,sans-serif}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
header{background:var(--card);border-bottom:1px solid var(--line);padding:14px 0;
position:sticky;top:0;z-index:10}
.wrap{max-width:1060px;margin:0 auto;padding:0 16px}
header .wrap{display:flex;align-items:center;gap:20px;flex-wrap:wrap}
.brand{font-weight:700;color:var(--accent);font-size:15px}
nav a{color:var(--muted);font-size:14px;margin-left:16px}
h1{font-size:30px;margin:26px 0 4px;letter-spacing:-.3px}
h2{font-size:19px;margin:32px 0 12px;padding-bottom:6px;border-bottom:1px solid var(--line)}
h3{font-size:16px}
.sub{color:var(--muted);font-size:14px;margin:0 0 6px}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;color:var(--muted)}
.stats{display:flex;gap:10px;flex-wrap:wrap;margin:18px 0 6px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:8px;
padding:10px 16px;min-width:96px}
.stat b{display:block;font-size:22px}
.stat span{font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
table{width:100%;border-collapse:collapse;font-size:14px;background:var(--card);
border:1px solid var(--line);border-radius:8px;overflow:hidden}
th{text-align:left;font-size:10.5px;letter-spacing:.07em;text-transform:uppercase;
color:var(--muted);font-weight:600;padding:9px 12px;border-bottom:1px solid var(--line)}
td{padding:9px 12px;border-bottom:1px solid var(--line);vertical-align:top}
tr:last-child td{border-bottom:none}
input[type=search],input[type=text],textarea,select{width:100%;padding:11px 14px;
font-size:15px;border:1px solid var(--line);border-radius:8px;background:var(--card);
color:var(--ink);font-family:inherit}
.pill{display:inline-block;font-size:10.5px;padding:2px 7px;border-radius:20px;
border:1px solid var(--line);color:var(--muted);background:var(--card);white-space:nowrap}
.support{color:var(--green);font-weight:600}.oppose{color:var(--red);font-weight:600}
.neutral{color:var(--muted);font-weight:600}
.c{border-left:3px solid var(--line);padding:9px 0 9px 13px;margin:13px 0}
.c.email{border-left-color:var(--blue)}.c.spoken{border-left-color:var(--orange)}
.c .meta{font-size:12px;color:var(--muted);margin-bottom:3px}
.c .body{font-size:14px;white-space:pre-wrap}
.chan{font-size:10px;letter-spacing:.06em;text-transform:uppercase;font-weight:700}
.chan.spoken{color:var(--orange)}.chan.email{color:var(--blue)}
.note{background:#FFF8E8;border:1px solid #EADFBF;border-radius:8px;padding:11px 14px;
font-size:13px;color:#6B5A2E;margin:14px 0}
.tier{font-size:11px;padding:2px 8px;border-radius:20px;font-weight:600}
.tier.confirmed{background:#E4F1E8;color:#1F6B41}
.tier.probable{background:#FFF3DC;color:#8A6216}
.tier.unsupported{background:#F4E3E1;color:#9B3A30}
.grp{margin:20px 0;background:var(--card);border:1px solid var(--line);
border-radius:8px;padding:14px 18px}
.grp h3{margin:0 0 2px}
footer{margin:50px 0 30px;color:var(--muted);font-size:12.5px;text-align:center}
#hits{margin-top:10px}
#hits a{display:block;padding:9px 12px;border-bottom:1px solid var(--line);background:var(--card)}
.muted{color:var(--muted)}
a.more{font-size:13px;white-space:nowrap}
.c .body .full{display:block}
.bars{margin:6px 0 2px}
.barrow{display:flex;align-items:center;gap:9px;margin:5px 0;font-size:12.5px}
.barrow .lab{width:74px;color:var(--muted);text-align:right;flex:none}
.bar{flex:1;height:15px;border-radius:3px;overflow:hidden;display:flex;background:#F1EEE8}
.bar i{display:block;height:100%}
.bar .s{background:var(--green)}.bar .o{background:var(--red)}.bar .u{background:var(--grey)}
.barrow .num{width:150px;flex:none;color:var(--muted)}
.camp{background:#F3F6FA;border:1px solid #D8E3EF;border-radius:8px;
padding:10px 14px;margin:13px 0}
.camp summary{cursor:pointer;font-size:13.5px;color:#27527E;font-weight:600}
.hgrp{border:1px solid var(--line);border-radius:8px;background:var(--card);
padding:10px 16px;margin:10px 0}
.hgrp summary{cursor:pointer;font-size:14px}
.hgrp[open] summary{margin-bottom:6px;padding-bottom:6px;border-bottom:1px solid var(--line)}
.flag{display:inline-block;font-size:10px;font-weight:700;letter-spacing:.05em;
text-transform:uppercase;background:#E2ECF7;color:#27527E;border-radius:3px;padding:1px 5px}
.tl{margin:14px 0 2px}
.tl svg{display:block;width:100%;height:auto;overflow:visible}
.tl circle{transition:r .08s}
.tl circle:hover{stroke:#1F2A36;stroke-width:2}
.tl a{cursor:pointer}
.legend{font-size:11.5px;color:var(--muted);margin-top:3px}
.tlinfo{font-size:12.5px;color:var(--ink);min-height:1.3em;font-weight:600;margin-top:2px}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:4px}
form.fb label{display:block;font-size:13px;color:var(--muted);margin:12px 0 4px}
form.fb button{margin-top:14px;padding:10px 20px;border:none;border-radius:8px;
background:var(--accent);color:#fff;font-size:15px;cursor:pointer}
"""

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?<!\d)(\(?\d{3}\)?[-.\s]){1,2}\d{3}[-.\s]\d{4}(?!\d)")
BARE_DOMAIN_RE = re.compile(r"\S*@[\w-]+(\.[\w-]+)*\.[A-Za-z]{2,}")


def esc(x):
    return html.escape(str(x)) if pd.notna(x) else ""


def scrub(x):
    """Strip contact details before any comment text reaches a page."""
    if pd.isna(x):
        return ""
    t = EMAIL_RE.sub("[email removed]", str(x))
    t = BARE_DOMAIN_RE.sub("[email removed]", t)
    t = PHONE_RE.sub("[phone removed]", t)
    return html.escape(t)

def page(title, body, depth=0, noindex=False):
    up = "../" * depth
    robots = ('<meta name="robots" content="noindex,noarchive">'
              if noindex else "")
    return f"""<!doctype html><html lang=en><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>{robots}<style>{CSS}</style>
<header><div class=wrap><span class=brand>SF Planning Commission &middot; Public Comment</span>
<nav><a href="{up}index.html">Search</a>
<a href="{up}projects/index.html">Projects</a><a href="{up}data.html">Data</a>
<a href="{up}about.html">About</a></nav>
</div></header><div class=wrap>{body}</div>
<script>
function tlHover(ev,show){{
 var t=ev.target.closest&&ev.target.closest('[data-info]'); if(!t)return;
 var w=t.closest('.tl'); if(!w)return;
 var b=w.querySelector('.tlinfo'); if(b)b.textContent=show?t.getAttribute('data-info'):'';
}}
function showFull(a){{
 var b=a.parentNode;
 b.querySelector('.short').hidden=true;
 b.querySelector('.full').hidden=false;
 a.remove(); return false;
}}
function tlAll(open){{
 document.querySelectorAll('details.hgrp').forEach(function(d){{d.open=!!open}});
 return false;
}}
document.addEventListener('mouseover',function(e){{tlHover(e,true)}});
document.addEventListener('mouseout',function(e){{tlHover(e,false)}});
</script>
<footer>Parsed from public San Francisco Planning Commission records &middot;
compiled by <a href="https://alexandersahn.com/">Alexander Sahn</a> &middot;
<a href="{up}about.html">corrections welcome</a></footer></html>"""

def pos(p):
    return f'<span class="{p}">{p}</span>' if pd.notna(p) else '<span class=muted>—</span>'

def ramp(nsup, nopp):
    """Red - grey - green by share in favour; an even split stays neutral."""
    if nsup + nopp == 0:
        return "#9AA2AA"
    net = (nsup - nopp) / (nsup + nopp)
    base = (0x2E, 0x7D, 0x4F) if net >= 0 else (0xC2, 0x3B, 0x32)
    mid = (0x8A, 0x92, 0x99)
    k = abs(net)
    return "#%02X%02X%02X" % tuple(round(m + (b - m) * k) for m, b in zip(mid, base))


def tint(g):
    """Colour a count by how one-sided that channel's comment was."""
    s = int((g.position == "support").sum()); o = int((g.position == "oppose").sum())
    if s + o == 0:
        return "var(--ink)", ""
    return ramp(s, o), f"{s} support / {o} oppose"


def bars(rows):
    """Unused: replaced by tinted counts."""
    out = []
    for lab, g in (("in person", rows[rows.channel == "spoken"]),
                   ("email", rows[rows.channel == "email"])):
        if not len(g):
            continue
        s = int((g.position == "support").sum())
        o = int((g.position == "oppose").sum())
        u = len(g) - s - o
        t = len(g)
        out.append(
            f'<div class=barrow><span class=lab>{lab}</span>'
            f'<span class=bar><i class=s style="width:{100*s/t:.1f}%"></i>'
            f'<i class=o style="width:{100*o/t:.1f}%"></i>'
            f'<i class=u style="width:{100*u/t:.1f}%"></i></span>'
            f'<span class=num><b class=support>{s}</b> / <b class=oppose>{o}</b>'
            + (f' <span class=muted>/ {u} n.r.</span>' if u else "") + '</span></div>')
    if not out:
        return ""
    return ('<div class=bars>' + "".join(out) +
            '<div class=legend><span class=dot style="background:var(--green)"></span>support'
            '<span class=dot style="background:var(--red);margin-left:12px"></span>oppose'
            '<span class=dot style="background:var(--grey);margin-left:12px"></span>'
            'not recorded</div></div>')

TL_W, TL_L, TL_R = 760, 58, 20          # width, left gutter, right gutter


def tl_scale(lo, hi):
    """One x-scale shared by the comment timeline and the hearing track, so
    a dot and the hearing it relates to sit on the same vertical."""
    y0 = lo.year
    y1 = max(hi.year, y0 + 1)
    def x(ts):
        f = (ts.year + ts.dayofyear / 366 - y0) / (y1 - y0 + 1)
        return TL_L + f * (TL_W - TL_L - TL_R)
    return x, y0, y1


def tl_domain(rows, hearings=None):
    d = pd.to_datetime(rows.date, errors="coerce").dropna()
    hd = (pd.to_datetime(pd.Series(list(hearings)), errors="coerce").dropna()
          if hearings is not None else pd.Series([], dtype="datetime64[ns]"))
    if d.empty and hd.empty:
        return None
    lo = min([v for v in ([d.min()] if not d.empty else []) + ([hd.min()] if len(hd) else [])])
    hi = max([v for v in ([d.max()] if not d.empty else []) + ([hd.max()] if len(hd) else [])])
    return lo, hi


def timeline(rows, hearings=None, domain=None, mode="each"):
    """Every comment as a dot, coloured by position, linking to its text.

    All attributes are quoted: unquoted `stroke-width=1/>` parses as the value
    "1/" with no self-close, so everything after it nests inside and never
    renders.
    """
    dom = domain or tl_domain(rows, hearings)
    if dom is None:
        return ""
    hd = (pd.to_datetime(pd.Series(list(hearings)), errors="coerce").dropna()
          if hearings is not None else pd.Series([], dtype="datetime64[ns]"))
    x, y0, y1 = tl_scale(*dom)
    W, H = TL_W, 88
    POS = {"support": "#2E7D4F", "oppose": "#C23B32"}
    n_days = rows.date.nunique() or 1
    g = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg">',
         f'<line x1="{TL_L}" y1="70" x2="{W-TL_R}" y2="70" stroke="#D8D2C6" '
         f'stroke-width="1.5" />']
    step = max(1, round((y1 - y0 + 1) / 9))
    for yy in range(y0, y1 + 1, step):
        xx = x(pd.Timestamp(year=yy, month=1, day=1))
        g.append(f'<line x1="{xx:.1f}" y1="65" x2="{xx:.1f}" y2="70" stroke="#C9C2B6" />')
        g.append(f'<text x="{xx:.1f}" y="83" font-size="11" fill="#5B6570" '
                 f'text-anchor="middle">{yy}</text>')
    for ts in hd:
        xx = x(ts)
        g.append(f'<line x1="{xx:.1f}" y1="8" x2="{xx:.1f}" y2="64" stroke="#CFC8BA" '
                 f'stroke-dasharray="2,3" />')
    for ch, lab, cy in (("spoken", "in person", 24), ("email", "email", 48)):
        sub = rows[rows.channel == ch]
        g.append(f'<text x="52" y="{cy + 4}" font-size="11" fill="#5B6570" '
                 f'text-anchor="end">{lab}</text>')
        g.append(f'<line x1="{TL_L}" y1="{cy}" x2="{W-TL_R}" y2="{cy}" stroke="#F1EEE8" '
                 f'stroke-width="1" />')
        if mode == "byday":
            # one dot per hearing date: area by volume, hue by share in favour
            for dt, dg in sub.groupby("date", sort=True):
                ts = pd.to_datetime(dt, errors="coerce")
                if pd.isna(ts):
                    continue
                ns = int((dg.position == "support").sum())
                no = int((dg.position == "oppose").sum())
                r = min(13, 3.0 + 1.6 * (len(dg) ** .5))
                first = dg.iloc[0]
                share = (f"{round(100*ns/(ns+no))}% in favour" if ns + no
                         else "position not recorded")
                info = f"{esc(dt)} — {len(dg)} comments, {share} (click to read)"
                g.append(f'<a href="#c{first.cid}">'
                         f'<circle cx="{x(ts):.1f}" cy="{cy}" r="{r:.1f}" '
                         f'fill="{ramp(ns, no)}" fill-opacity="0.75" '
                         f'data-info="{info}"><title>{info}</title></circle></a>')
        else:
            # one dot per comment; no outline, so overlaps darken
            used = collections.Counter()
            for r_ in sub.itertuples():
                ts = pd.to_datetime(r_.date, errors="coerce")
                if pd.isna(ts):
                    continue
                xx = round(x(ts))
                k = used[xx]; used[xx] += 1
                dy = ((k % 3) - 1) * 4.0 if n_days > 1 else 0
                col = POS.get(r_.position, "#9AA2AA")
                info = (f"{esc(r_.date)} — "
                        f"{esc(r_.position) or 'position not recorded'} (click to read)")
                g.append(f'<a href="#c{r_.cid}">'
                         f'<circle cx="{xx}" cy="{cy + dy:.1f}" r="4.4" fill="{col}" '
                         f'fill-opacity="0.5" data-info="{info}">'
                         f'<title>{info}</title></circle></a>')
    g.append("</svg>")
    leg = ("dashed lines mark hearings &middot; " if len(hd) else "")
    return (f'<div class=tl>{"".join(g)}<div class=tlinfo></div>'
            f'<div class=legend>{leg}'
            f'<span class=dot style="background:#2E7D4F"></span>support'
            f'<span class=dot style="background:#C23B32;margin-left:12px"></span>oppose'
            f'<span class=dot style="background:#9AA2AA;margin-left:12px"></span>not recorded'
            + (' &middot; dot size = comments that day' if mode == "byday" else '')
            + f' &middot; click a dot to jump to the comment</div></div>')


ACTION_COL = {"approve": "#2E7D4F", "approve with conditions": "#2E7D4F",
              "disapprove": "#C23B32", "withdraw": "#C23B32",
              "continuance": "#C89A3C", "no action": "#9AA2AA"}


def hearing_track(hear, domain=None):
    """The project's hearings as a visual track, coloured by outcome.

    Labels used to sit above and below each marker, which collides badly once
    a project has more than a handful of hearings (the Housing Element has
    14). Date and action now live in the hover tooltip; only the first and
    last are labelled, where nothing can overlap.
    """
    h = (hear.dropna(subset=["meeting_date"])
             .drop_duplicates("meeting_date").sort_values("meeting_date"))
    if h.empty:
        return ""
    d = pd.to_datetime(h.meeting_date, errors="coerce")
    dom = domain or (d.min(), d.max())
    x, _y0, _y1 = tl_scale(*dom)
    W, H = TL_W, 52
    g = [f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg">',
         f'<line x1="{TL_L}" y1="22" x2="{W-TL_R}" y2="22" stroke="#E4DFD6" '
         f'stroke-width="2" />']
    n = len(h)
    for i_, (ts, r) in enumerate(zip(d, h.itertuples())):
        xx = x(ts)
        act = str(r.action_final) if pd.notna(r.action_final) else "no action recorded"
        col = ACTION_COL.get(str(r.action_final), "#5B6570")
        info = f'{ts.strftime("%d %b %Y")} — {html.escape(act)}'
        g.append(f'<circle cx="{xx:.1f}" cy="22" r="7" fill="{col}" '
                 f'class="hdot" data-info="{info}">'
                 f'<title>{info}</title></circle>')
        if i_ in (0, n - 1) and n > 1 and (x(d.max()) - x(d.min())) > 120:
            anchor = "start" if i_ == 0 else "end"
            g.append(f'<text x="{xx:.1f}" y="45" font-size="11" fill="#5B6570" '
                     f'text-anchor="{anchor}">{ts.strftime("%b %Y")}</text>')
        elif n == 1:
            g.append(f'<text x="{xx:.1f}" y="45" font-size="11" fill="#5B6570" '
                     f'text-anchor="middle">{ts.strftime("%b %Y")}</text>')
    g.append("</svg>")
    keys = "".join(f'<span class=dot style="background:{c}"></span>{k}&nbsp;&nbsp;'
                   for k, c in (("approved", "#2E7D4F"), ("continued", "#C89A3C"),
                                ("denied / withdrawn", "#C23B32")))
    return (f'<div class=tl>{"".join(g)}<div class=tlinfo></div>'
            f'<div class=legend>{keys}&middot; {n} hearings &middot; '
            f'hover a marker for the date and outcome</div></div>')


def packet_url(d):
    """The Commission Packet PDF this email was published in."""
    ts = pd.to_datetime(d, errors="coerce")
    if pd.isna(ts):
        return None
    return (f"https://citypln-m-extnl.sfgov.org/Commissions/CPC/"
            f"{ts.month}_{ts.day}_{ts.year}/Commission%20Packet/"
            f"{ts.strftime('%Y%m%d')}pre.pdf")


def comment_block(r, show_proj=True, depth=1, who=""):
    up = "../" * depth
    ch = r.channel
    head = f'{who}<span class="chan {ch}">{ch}</span> &middot; {r.date} &middot; {pos(r.position)}'
    if show_proj and pd.notna(r.id_parent):
        head += f' &middot; <a href="{up}projects/{esc(r.id_parent)}.html">{esc(ptitle(r.id_parent))}</a>'
    if pd.notna(r.campaign):
        head += ' &middot; <span class=flag>campaign email</span>'
    subj = f"<b>{scrub(r.subject)}</b><br>" if pd.notna(r.subject) and r.subject else ""
    full = scrub(r.text) if pd.notna(r.text) else ""
    if not full:
        body = "<i class=muted>no text recorded</i>"
    elif len(full) <= 460:
        body = full
    else:
        # the whole message, revealed in place rather than truncated away
        body = (f'<span class=short>{full[:420]}… </span>'
                f'<span class=full hidden>{full}</span>'
                f'<a href="#" class=more onclick="return showFull(this)">show more</a>')
    if ch == "email":
        src = packet_url(r.date)
        if src:
            head += (f' &middot; <a href="{src}" target="_blank" rel="noopener">'
                     f'source packet</a>')
    cid = getattr(r, "cid", "")
    return (f'<div class="c {ch}" id="c{cid}"><div class=meta>{head}</div>'
            f'<div class=body>{subj}{body}</div></div>')

# No pages for individual commenters. Their names still appear beside the
# comments they made on a project, which is how the minutes and packets
# already publish them, but the site does not assemble a per-person dossier:
# no page, no link, no search entry. Aggregating one named private
# individual's entire hearing history into a single addressable page is a
# different act from republishing the records themselves.

# ------------------------------------------------------------ project pages
for idp, p in PR.iterrows():
    rows = C[C.id_parent == idp].sort_values("date")
    t = ptitle(idp)
    hear = it[it.id_parent == idp].drop_duplicates(["meeting_date", "record_id"]).sort_values("meeting_date")
    tsp = tint(rows[rows.channel == "spoken"])
    tem = tint(rows[rows.channel == "email"])
    _dom = tl_domain(rows, hear.meeting_date.unique())
    body = [f"<h1>{esc(t)}</h1>",
            f"<p class=sub><span class=mono>{esc(idp)}</span>"
            + (f" &middot; {esc(pmeta.addr.get(idp))}" if pd.notna(pmeta.addr.get(idp)) else "")
            + "</p>",
            f"""<div class=stats>
<div class=stat><b>{int(p.n_all)}</b><span>comments</span></div>
<div class=stat><b style="color:{tsp[0]}" title="{tsp[1]}">{int(p.n_sp)}</b><span>in person</span></div>
<div class=stat><b style="color:{tem[0]}" title="{tem[1]}">{int(p.n_em)}</b><span>emails</span></div>
<div class=stat><b>{hear.meeting_date.nunique()}</b><span>hearings</span></div></div>""",
            timeline(rows, hear.meeting_date.unique(), domain=_dom, mode="byday"),
            "<h2>Hearings</h2>", hearing_track(hear, domain=_dom)]

    # campaign emails collapse into one block each
    camp = rows[rows.campaign.notna()]
    rest = rows[rows.campaign.isna()]
    if len(camp):
        body.append(f"<h2>Campaign emails ({len(camp)})</h2>")
        for cid, g in sorted(camp.groupby("campaign"), key=lambda kv: -len(kv[1])):
            nm = g.campaign_name.dropna()
            label = esc(nm.iloc[0]) if len(nm) else f"campaign {esc(cid)}"
            s = int((g.position == "support").sum()); o = int((g.position == "oppose").sum())
            body.append(
                f'<details class=camp><summary>{label} — {len(g)} emails '
                f'(<span class=support>{s}</span> / <span class=oppose>{o}</span>)</summary>'
                + "".join(comment_block(r, show_proj=False,
                                        who=f"{esc(r.name)} &middot; ")
                          for r in g.head(6).itertuples())
                + (f'<p class=sub>… and {len(g)-6} more</p>' if len(g) > 6 else "")
                + '</details>')
    # Every comment is rendered — no truncation. They are grouped by hearing
    # and collapsed, which keeps the DOM small enough to paint (the flat,
    # fully expanded version of this page was 4.8 MB and 91,000 px tall and
    # stalled the renderer) while making the hearing-by-hearing shape legible.
    body.append(f'<h2>Comments by hearing ({len(rest)})</h2>')
    body.append('<p class=sub><a href="#" onclick="return tlAll(1)">expand all</a>'
                ' &middot; <a href="#" onclick="return tlAll(0)">collapse all</a>'
                ' &middot; comments with recorded text are listed first</p>')
    for k, (dt, g) in enumerate(rest.groupby("date", sort=True)):
        ns = int((g.position == "support").sum())
        no = int((g.position == "oppose").sum())
        has_text = g[g.text.notna() & (g.text.astype(str).str.strip() != "")]
        no_text = g[~g.index.isin(has_text.index)]
        counts = (f'<span class=support>{ns}</span> / <span class=oppose>{no}</span>'
                  if ns + no else '<span class=muted>no positions recorded</span>')
        inner = []
        for r in list(has_text.itertuples()) + list(no_text.itertuples()):
            who = f"{esc(r.name)} &middot; "
            inner.append(comment_block(r, show_proj=False, who=who))
        body.append(
            f'<details class=hgrp{" open" if k == 0 else ""}>'
            f'<summary><b>{esc(dt)}</b> &middot; {len(g)} comments &middot; {counts}'
            f'</summary>{"".join(inner)}</details>')

    open(f"{OUT}/projects/{esc(idp)}.html", "w").write(page(t, "".join(body), 1))

# ------------------------------------------------------------ indexes
prows = "".join(
    f'<tr><td><a href="{esc(i)}.html">{esc(ptitle(i))}</a>'
    f'<br><span class=mono>{esc(i)}</span></td>'
    f'<td>{int(p.n_sp)}</td><td>{int(p.n_em)}</td>'
    f'<td>{int(p.y0)}–{int(p.y1)}</td><td>{esc(p.action)}</td></tr>'
    for i, p in PR.head(300).iterrows())
open(f"{OUT}/projects/index.html", "w").write(page("Projects",
    "<h1>Projects</h1><p class=sub>Ordered by comment volume. Showing 300 of "
    f"{len(PR)}.</p><table><tr><th>Project</th><th>In person</th><th>Emails</th>"
    "<th>Years</th><th>Last action</th></tr>" + prows + "</table>", 1))

def sstr(x):
    return "" if x is None or pd.isna(x) else str(x)

# projects only: names are not searchable
search = [{"t": ptitle(i), "s": str(i), "u": f"projects/{esc(i)}.html",
           "k": "project"} for i, p in PR.iterrows()]
json.dump(search, open(f"{OUT}/search.json", "w"), allow_nan=False)

_sy = C[C.channel == "spoken"].year.dropna()
_ey = C[C.channel == "email"].year.dropna()
_ay = C.year.dropna()
_span = lambda y: f"{int(y.min())}\u2013{int(y.max())}" if len(y) else ""

home = f"""<h1>Public comment at the Planning Commission</h1>
<input type=search id=q placeholder="Search a project, an address, or a case number — try Castro Theatre, Van Ness, 2022-005675" autocomplete=off>
<div id=hits></div>
<div class=stats>
<div class=stat><b>{len(C):,}</b><span>comments ({_span(_ay)})</span></div>
<div class=stat><b>{(C.channel=='spoken').sum():,}</b><span>in person ({_span(_sy)})</span></div>
<div class=stat><b>{(C.channel=='email').sum():,}</b><span>emails ({_span(_ey)})</span></div>
<div class=stat><b>{C.id_parent.nunique():,}</b><span>projects</span></div></div>
<div class=grp><h3><a href="projects/2022-005675.html">429 Castro St</a></h3>
<p class=sub>Three hearings, two continuances, the most-commented project in the data.</p></div>
<div class=grp><h3><a href="projects/2019-016230.html">Housing Element 2022 Update</a></h3>
<p class=sub>A citywide plan rather than a site — and the biggest organised email
campaigns in the data.</p></div>
<div class=grp><h3><a href="projects/index.html">Browse all projects</a></h3>
<p class=sub>Every project with public comment, ordered by volume.</p></div>
<script>
let D=[];fetch('search.json').then(r=>r.json()).then(d=>D=d);
const q=document.getElementById('q'),h=document.getElementById('hits');
q.addEventListener('input',()=>{{const v=q.value.toLowerCase().trim();
if(v.length<2){{h.innerHTML='';return}}
const m=D.filter(x=>(x.t+' '+x.s).toLowerCase().includes(v)).slice(0,12);
h.innerHTML=m.map(x=>`<a href="${{x.u}}"><b>${{x.t}}</b> <span class=pill>${{x.k}}</span>
<span class=muted style="font-size:12px"> ${{x.s}}</span></a>`).join('')||
'<div style="padding:10px" class=muted>no match</div>';}});
</script>"""
open(f"{OUT}/index.html", "w").write(page("SF Planning Commission Public Comment", home))

# No data download here. The Data tab links to the repository, which is the
# single published copy — the site's own export was a 13-column subset with
# its own commenter ids, so "download the data" meant two different things.

open(f"{OUT}/robots.txt", "w").write(
    "User-agent: *\n")
open(f"{OUT}/.nojekyll", "w").write("")
open(f"{OUT}/data.html", "w").write(page("Data", """<h1>Data</h1>
<div class=grp>
<h3><a href="https://github.com/alexandersahn/sf-planning-public-comment-data">sf-planning-public-comment-data</a></h3>
<p class=sub>Comments, agenda items with outcomes and votes, meetings, and the
pipeline that builds them.</p>
</div>"""))

open(f"{OUT}/about.html", "w").write(page("About", """<h1>About</h1>
<p class=sub style="max-width:680px;font-size:16px">This website collates and links
publicly available data from meeting minutes and informational packets of the San
Francisco Planning Commission. The data were gathered and cleaned by Alexander Sahn,
Assistant Professor of Political Science at UNC Chapel Hill.</p>

<h2>Papers using this data</h2>
<div class=grp>
<h3><a href="https://doi.org/10.1111/ajps.12900">Public Comment and Public Policy</a></h3>
<p class=sub>Alexander Sahn &middot; <i>American Journal of Political Science</i> 69(2),
2025, 685&ndash;700</p>
<p class=sub><a href="https://doi.org/10.1111/ajps.12900">doi:10.1111/ajps.12900</a></p>
</div>
<div class=grp>
<h3><a href="https://osf.io/vxpc5/files/qn3rx">Issue Accountability Among Public Meeting Commenters</a></h3>
<p class=sub>Alexander Sahn and Tyler Simko &middot; conditionally accepted,
<i>American Journal of Political Science</i></p>
<p class=sub><a href="https://osf.io/vxpc5/files/qn3rx">read the paper</a></p>
</div>

<h2>Corrections and suggestions</h2>
<div class=grp>
<form class=fb onsubmit="return false">
<label>Page this concerns (optional)</label>
<input type=text placeholder="https://…">
<label>Your suggestion or correction</label>
<textarea rows=5 placeholder="What is wrong, and what should it say?"></textarea>
<button>Submit on GitHub</button>
<p class=sub style="margin-top:12px">Submitting opens a pre-filled issue on the
project&rsquo;s GitHub repository, where it is tracked publicly and can be cited. A
GitHub account is required.</p>
</form>
</div>
"""))

print(f"built: {len(PP)} people, {len(PR)} projects, {n_merged} name spellings merged")
print(f"unified comments: {len(C):,} ({(C.channel=='spoken').sum():,} spoken, "
      f"{(C.channel=='email').sum():,} email)")
print(f"dropped: {n_staff:,} staff reports/presentations, {n_gov} .gov emails, "
      f"{n_dedup:,} duplicate rows from the item fan-out")
_cg = C[C.campaign.notna()].groupby("campaign").position.agg(
    lambda x: ((x == "support").any() and (x == "oppose").any()))
print(f"campaign emails: {int(C.campaign.notna().sum()):,} in "
      f"{C.campaign.nunique()} campaigns; internally mixed: {int(_cg.sum())}")
