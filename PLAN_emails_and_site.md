# Plan — add written (email) public comment to the dataset and publish a site

Goal: bring the SFPC email-comment data used in Sahn & Simko, *Issue Accountability
Among Public Commenters*, into this repository as a first-class release table, linked
to the existing minutes data **by meeting and by project**, and publish the whole thing
as a browsable GitHub Pages site.

Two comment channels, one dataset:

| channel | source | table | coverage |
|---|---|---|---|
| spoken testimony | meeting minutes (SPEAKERS blocks) | `public/comments.csv` | 1998-01 – 2026-03 |
| written testimony | Commission Packet PDFs (`*pre.pdf`) | same `comments.csv`, `channel = email` | 2017-08 – present |

---

## 1. What exists today

**In `prospective_threats/`** (Google Drive), the working chain is:

| stage | artifact | rows | notes |
|---|---|---|---|
| scrape | `code/scrape_emails/scrape.ipynb` | 263 packets | `https://citypln-m-extnl.sfgov.org/Commissions/CPC/{M_D_YYYY}/Commission%20Packet/{YYYYMMDD}pre.pdf` |
| parse | `code/scrape_emails/parse.ipynb` → `data/output_all_clean.csv`, `data/output_all_batch2.csv` | — | fields: `filename, email_from, name_from, email_to, name_to, email_cc, name_cc, subject, date, attachments, content` |
| clean | `code/01_clean_emails.R` | — | sender normalization, `meeting_date` from filename, regex `tone`, form-email flag |
| LLM code | `code/05_clean_gpt.R` → `data/intermediate/emails_gpt_cleaned.rds` | 11,113 × 44 | GPT-4o(-mini): `item_name`, `address`, `sponsor`, `position`, 13 topic dummies, `extra_topic` |
| forms | `data/intermediate/emails_with_forms.rds` | 11,641 × 47 | `form_id`, `is_form` (4,793), `form_name` |
| project link | `code/08_clean_congurence.R` → `data/intermediate/congruence_match.rds` | 10,278 × 55 | **carries `id_parent`**, `approved_immediately`, `approved_ever` |
| hand check | `data/intermediate/project_match_final_batch_codes.csv` | — | verified email → `project_id` |

Coverage of the linked file: **2017-08-31 – 2024-10-24**, 263 meeting dates,
825 unique projects, 7,472 unique sender addresses, 5,599 support / 4,679 oppose.

**In this repo**, `items.csv.gz` already carries `id_parent` (case number with the
entitlement suffix stripped) — the *same key* `08_clean_congurence.R` constructs.
The join is therefore already half-built.

Measured overlap against the current release:

- `id_parent`: **635 / 825** email projects (77%) appear in `items.csv.gz`.
- `meeting_date`: **261 / 263** email packet dates appear in `meetings.csv`
  (missing: 2021-05-13, 2021-07-15 — reconcile; likely special/cancelled hearings).
- Items heard in the email window (2017-08 – 2024-10): 5,516, of which 4,429 carry
  an `id_parent` and 2,278 are distinct projects.

The ~190 unmatched projects are the main data-quality task: expect a mix of
Non-Projects records (DataSF `y673-d69b`), legislation/PCA items with no `PRJ`
parent, and emails about projects heard on a different date than the packet.

**The packet date is usually not the hearing date.** Of the 1,865 distinct
(`meeting_date`, `id_parent`) pairs in the linked emails, only **684 (37%)** match an
agenda item heard at that exact meeting, while **1,558 (84%)** match the project at
*some* hearing. Continuances are the obvious driver: correspondence arrives for a
calendar the item then rolls off of. This settles the linkage design — the project link
is the durable one, and `item_id` must be *derived* (nearest hearing of that project on
or after the packet date), never an exact-date equality join.

---

## 2. Data model: one comment table, nested two ways

Everything hangs off a single long table of comments — spoken and written in
the same rows — carrying a foreign key to the project and a foreign key to
the person. A project page is that table grouped by `id_parent`; a person
page is the same table grouped by `commenter_id`. Neither view is primary and
neither needs its own store.

A fully flat table is the wrong way to do it, though: the channels share only
about a dozen fields, and 33 of the 63 columns would be permanently empty for
the 76,731 spoken rows (87% of the data). So the core stays narrow and each
channel keeps a thin extension keyed by `comment_id`.

**`public/comments.csv`** — the core. One row per comment, both channels.

| column | notes |
|---|---|
| `comment_id` | primary key |
| `channel` | `spoken` / `email` |
| `commenter_id` | → `commenters.csv` |
| `name_display` | resolved name as shown on the site |
| `id_parent`, `record_id` | project link |
| `item_id` | agenda item; derived for emails (§2b) |
| `meeting_date` | hearing the comment belongs to |
| `date` | when it was made — hearing date for spoken, sent date for email |
| `position` | support / oppose / neutral |
| `position_source` | `stenographer`, `model`, `role`, `llm` |
| `role_long`, `role_group`, `role_source` | affiliation, same vocabulary for both channels |
| `text` | the stenographer's summary, or the email body |
| `text_type` | `stenographer_summary` / `email_body` — different provenance, do not pool naively |
| `link_method` | how the project link was made |

**`public/comments_spoken.csv`** — keyed by `comment_id`: `speaker_order`,
`name_raw`, `title`, `role_title`, `organization`, `is_anonymous`,
`anon_gender`, `is_staff`, `is_commissioner`, `sign`, `sign_imputed`,
`sign_prob`, `sign_source`, `section`, `item_num`, `method`.

**`public/comments_email.csv`** — keyed by `comment_id`: `sender_email`,
`subject`, `sent_datetime`, `to_names`, `cc_names`, `is_form`, `form_id`,
`form_name`, `is_sponsor`, the 13 topic dummies, `extra_topic`, `n_topics`,
`packet_url`, `packet_page`, `item_lag_days`, `item_heard_as_calendared`.

**`public/commenters.csv`** — one row per person: `commenter_id`,
`display_name`, `channels`, `n_comments`, `n_spoken`, `n_emails`,
`n_projects`, `first_year`, `last_year`, `role_long`, `role_source`,
`match_tier`, `match_evidence`.

This drops the separate `commenter_links.csv` from the earlier draft — the
core table already carries `commenter_id` on every row, so the crosswalk is a
groupby, and the merge evidence lives on `commenters.csv`.

**This is a breaking change** to the published `comments.csv`, which today is
the spoken table with 24 columns. The alternative is to leave `comments.csv`
alone and add the core under a new name, at the cost of a schema nobody can
guess from the filenames. Recommend the clean break, documented in the
codebook next to the YIMBY split, since the dataset is new enough to have few
downstream users.

## 2b. Project and item linkage

Both channels resolve to `id_parent` (project) and `item_id` (agenda item) on
the core table, but they get there differently.

**Spoken** comments already carry `item_id` exactly — the stenographer
recorded them under a specific calendar item.

**Email** carries the project link from the LLM/hand match, and `item_id` is
*derived*: the project's first hearing on or after the packet date. The
packet date is usually not the hearing date — of 1,865 distinct
(`meeting_date`, `id_parent`) pairs, only 684 (37%) match an item heard that
day, while 1,558 (84%) match the project at some hearing, because items get
continued. Three columns record this on `comments_email.csv`:
`item_lag_days`, `item_heard_as_calendared`, and `link_method`
(`hand_verified` / `llm_case_number` / `llm_address` / `subject_regex` /
`unmatched`).

**`public/comment_item_links.csv`** — bridge, one row per
(`comment_id`, `item_id`), for the emails that concern several items at once
(housing element, Castro Theater, Great Highway). The core table holds the
primary link; this holds the rest, with `link_method` and `link_rank`.

Derived counts worth shipping on `items.csv.gz` so the site and users get them
for free: `n_spoken`, `n_emails`, `n_support`, `n_oppose`, `n_form`. Note the
existing per-item comment counts double-count when one project is heard under
several case records (§4a), so these must dedupe first.

### Affiliation from the sender's email domain

Tested against the 10,278 linked emails (2026-09). Every address parses to a
domain, but **76.1% are free webmail** and carry no signal. Of the 2,459 on
other domains, 1,137 are distinct and 809 appear exactly once, so the usable
yield is roughly 10–15% of emails. What comes back splits three ways:

| kind | examples (emails) | use |
|---|---|---|
| interest-group domains | housingactioncoalition.org (30), somapilipinas.org (16), unitehere2.org (15), castrocbd.org (15), spur.org (14), yimbylaw.org (14), chinatowncdc.org (13), yimbyaction.org (12) | feeds the same `role_long` taxonomy as spoken comment |
| project team / counsel | reubenlaw.com (35), zfplaw.com (34), cardellodesign.com (33), stevewilliamslaw.com (18), fbm.com (17), macyarchitecture.com (13) | `case_role`; note reubenlaw.com is Reuben & Junius, already in `LAW_FIRMS` in `assign_roles.py`, so the two channels agree |
| advocacy-platform relays | everyactioncustom.com (134), p2a.co (42), respondl.com (21), ujoin.co (13) | **not** affiliation — these are mass-email tools, so the domain is a direct mass-campaign flag that complements the LCS form detector |

Two cautions. Employer domains (berkeley.edu 39, ucsf.edu 19, siprep.org 13)
say where someone works, not their position on housing, and must not be read
as affiliation. Legacy ISP domains (sonic.net 27, mindspring.com 17,
prodigy.net 15, cpost.com 12) are free webmail in everything but name and
belong on the free list alongside gmail and yahoo.

So: worth building, as one signal among several rather than the primary one —
the email body and signature state affiliation more often than the domain
does. It should populate `role_long` / `role_source` on the email table using
the same vocabulary as `comments.csv`, with a distinct source value
(`email_domain`) so it can be switched off.

## 2a. The commenter as the primary entity

The goal is one source of participants across both channels, linked to
projects, with a site where you search a name or a project and can click
through to everything that person said. That makes the **person**, not the
comment, the top-level object — so identity resolution moves from a stretch
goal to the thing the whole design rests on.

### Feasibility, measured

Normalized exact-name matching between the two channels (2026-09):

- 23,438 spoken names with ≥2 tokens, 6,432 email sender names
- **737 names appear in both** (11.5% of email senders; 548 once spoken
  testimony is restricted to the 2017+ email era)

But exact name alone is not identity. Splitting those 737 by corroboration:

| tier | n | evidence |
|---|---|---|
| `confirmed` | **262** | the two channels share at least one project (`id_parent`) |
| `probable` | **236** | no shared project, but active within 2 years of each other |
| `unsupported` | **239** | no shared project, more than 2 years apart |

The unsupported tier is mostly namesakes, and obviously so: *john goldberg*
spoke in 1998 and emailed in 2023; *thomas smith* spoke in 1998, emailed in
2022; six more with gaps of 23–25 years. Separately, 141 of the 737 have a
surname appearing more than 20 times among spoken names — the corpus holds
`sue lee`, `john lee`, `paul lee`, `amy lee`, `carolyn lee`, `peter lee`,
`angelina lee`, `chelsea lee`, and treating a name match there as a person
match is close to a coin flip.

**So a naive merge would be wrong about a third of the time.** On a site
built around person pages that is the worst available failure: it invents a
profile asserting someone commented on projects they never touched, and it
does so about a named private individual. Misses are recoverable; false
merges are not.

### Identity model

Three tables, with the link kept explicit rather than baked into the
comment rows:

`commenters.csv` — one row per resolved person: `commenter_id`,
`display_name`, `channels` (spoken / email / both), `n_spoken`, `n_emails`,
`n_projects`, `first_year`, `last_year`, `role_long`, `role_source`,
`match_tier`.

`commenter_links.csv` — `commenter_id`, `channel`, `source_key`
(`name_clean` or sender address), `match_tier`, `evidence` (the shared
`id_parent`, or the year distance). Every merge is auditable and reversible.

`comments.csv` and `emails.csv` each gain `commenter_id`.

Matching rules:

1. **Within spoken** — the existing `name_crosswalk.csv`.
2. **Within email** — one address is one person. Two addresses sharing a
   name merge only with corroboration (38 names have >1 address).
3. **Across channels** — exact normalized name *plus* a shared project
   (`confirmed`), or a distinctive surname and activity within 2 years
   (`probable`). Everything else stays as two separate commenters.
4. **Never** merge on a high-frequency surname without a shared project.

Default the site and any headline statistic to `confirmed` + `probable`;
ship `unsupported` in the data flagged, never rendered as fact.

### Before this goes public

A person page is a different kind of artifact from a hearing transcript. The
city publishes documents; this publishes dossiers — everything one named
individual has said across 28 years, their affiliation, their email address,
sorted by project. That is a real change in exposure even though every
underlying record is a public document, and it is worth deciding
deliberately rather than by default. Four cheap mitigations that cost almost
nothing analytically:

- **Don't render email addresses on person pages.** Keep them in the
  downloadable tables; the page shows name, affiliation and activity.
- **Set a floor of 2 appearances for a person page.** 16,565 of 24,546 named
  speakers (67%) appear exactly once — a single trip to a microphone should
  not mint a permanent searchable profile, and the repeat participants are
  the analytically interesting ones anyway.
- **`noindex` on person pages**, so profiles of private individuals are not
  surfaced by search engines. Project and meeting pages stay indexable.
- **Show the match tier on the page**, so a `probable` link reads as an
  inference rather than a fact.

---

## 3. Pipeline work (`pipeline/`)

Port from R/notebooks to the existing Python pipeline so `update.sh` rebuilds
everything. New modules, mirroring the current naming:

1. **`fetch_packets.py`** — enumerate hearing dates from `meetings.csv` (already
   scraped) rather than the pasted-in table in `scrape.ipynb`; download
   `{YYYYMMDD}pre.pdf`; cache under `data/raw/packet/`; same throttling as `scrape.py`.
   Packets are large (many >100 MB) — store outside git, they are rebuildable.
2. **`parse_packets.py`** — port `parse.ipynb`: locate the public-correspondence
   section, split on email headers, emit the 11 raw fields + page provenance.
3. **`clean_emails.py`** — port `01_clean_emails.R`: sender normalization, dual-address
   splitting, `meeting_date`, regex tone as fallback, sender-name cleanup reusing
   `clean_names.py`.
   **Add a non-comment filter** the current chain lacks: the raw file contains Mayor's
   Press Office media advisories, internal staff traffic, and `@sfgov` correspondence.
   Drop or flag with `is_public_comment`.
4. **`detect_forms.py`** — port the LCS string-distance form detector (paper appendix);
   validate against the existing 4,793 flagged rows.
5. **`code_emails.py`** — LLM coding (position, topics, item name/address, sponsor).
   This introduces the repo's first model dependency at build time; make it cached and
   incremental (hash body → cached JSON in `data/processed/llm_cache/`) so a rebuild
   costs nothing and only new packets hit the API. Reuse the prompts from the paper
   appendix verbatim so the published codes stay comparable.
6. **`link_emails.py`** — the join. Priority order: hand-verified codes → case number
   in subject/body → LLM address match against `items.item_text` / DataSF project
   addresses → subject regex for the known mass campaigns. Emit the email rows of
   the core table, `comments_email.csv`, `comment_item_links.csv`, and an
   unmatched report to `data/validation/`.
7. **`finalize.py` / `make_figures.py`** — add email counts to `SUMMARY.md`, two new
   figures: emails per year by position (companion to `comments_by_year.png`), and
   written vs spoken volume per year.

Seed the first run by importing the existing hand-verified matches
(`project_match_final_batch_codes.csv`) and the existing LLM codes
(`emails_gpt_cleaned.rds`) rather than re-coding 11k emails — copy them into
`data/reference/` as CSV, and let `code_emails.py` only fill gaps.

**Extension to present:** the paper stops at 2024-10-24; the minutes release runs to
2026-03. ~70 additional packets to fetch, parse, and code. Do this after the port is
verified to reproduce the 11,641-row file.

---

## 4. The site (GitHub Pages)

Pages is not enabled on `alexandersahn/sf-planning-public-comment-data` yet. Enable it
on `main` → `/docs`, and generate `docs/` with a new `pipeline/build_site.py`
(pure Python + Jinja-free string templates; no JS build step, no CDN dependencies).

Pages:

- **`/`** — the README narrative, the four existing figures plus the two new email
  figures, headline counts, download links.
- **`/meetings/`** — index by year → **`/meetings/2023-03-16/`**: agenda in calendar
  order; per item, the staff recommendation, the commission action and vote, the
  spoken commenters with polarity, and the emails submitted for that item with
  position and body.
- **`/projects/`** — index → **`/projects/2021-012237/`**: every hearing the project
  appeared at, outcome at each, all spoken comments and all emails across those
  hearings, DataSF attributes (units, use, address), map pin.
- **`/people/`** — the search surface. Type a name, land on
  **`/people/<commenter_id>/`**: who they are, affiliation and how it was
  determined, then every project they engaged, each showing their spoken
  testimony and their emails together in date order with position. Repeat
  participants only (≥2 appearances), no email addresses rendered,
  `noindex`, match tier shown wherever two channels were joined.
- **`/data/`** — file table, codebook, licensing, citation, `update.sh` instructions.
- **`/about/`** — sources, method, the AJPS and accountability papers, caveats
  (imputed polarity, LLM-coded position, form emails).
- **Search** — one prebuilt JSON index covering commenter names, project
  addresses, project names and case numbers, served client-side; no server,
  no external library. This is the site's front door: a name or an address
  in the box, a person or project page out.

Scale: ~1,250 meeting pages and a project page for every `id_parent` with at least one
comment. Pre-rendered HTML keeps it dependency-free but adds tens of MB to the repo —
if that's unwelcome, publish `docs/` from a `gh-pages` branch instead of `main`.

Caveat to state on every project page: emails are submitted *before* the hearing and
are matched to projects by LLM plus hand review, so per-item email counts are an
estimate, not the city's own tally.

---

## 4a. What the prototype surfaced

A working generator (`build_site.py`, in the session scratchpad) produced 1,252 meeting
pages and 5,748 project pages from the real tables. Four things it exposed:

1. **The derived item link works.** 9,430 / 10,278 emails (92%) resolve to an `item_id`;
   3,612 (35%) were heard on the date they were submitted for. The 848 with no link are
   projects absent from `items.csv.gz`.
2. **Big project pages are unusable as flat HTML.** The Castro Theater page
   (`2022-005675`, 1,935 emails) is 4.8 MB and 91,000 px tall — the renderer stalls.
   Bodies must be paginated or lazy-loaded (ship the page with subject lines only and
   fetch bodies from a per-project JSON on expand).
3. **Project-level comment counts double-count.** A project heard once under several
   case records attaches the same testimony to each `item_id`: 490 Brannan St shows 96
   spoken comments (32 × ENX/OFA/VAR), Castro Theater 226 (113 × COA/CUA). Project pages
   and any `n_comments` column must dedupe on (meeting_date, speaker, comment).
4. **Meeting pages need both email views.** 693 emails were submitted for the 2022-12-01
   hearing, but the page shows 5, because the items were continued and the emails follow
   the project to its later hearing. Show "submitted for this hearing" *and* "attached to
   items heard today" as separate counts.

## 5. Sequence

0. Data cleaning on the spoken side, which the person view makes
   load-bearing: 123 duplicate `(item_id, speaker_order)` slots caused by the
   name splitter breaking on "/" (`Live/Work` → two speakers), 932 exact
   duplicate comment rows, 4,009 single-token names, and junk in
   `organization` (12 purely numeric values). Every one of these becomes a
   wrong person page if left alone.
1. Reconcile the two missing meeting dates and the 190 unmatched projects; decide the
   `link_method` hierarchy. *(analysis, no code)*
2. Port fetch → parse → clean → forms, reproducing `emails_with_forms.rds` (11,641 rows)
   as a regression test.
3. Import existing LLM codes + hand matches; build `link_emails.py`; ship
   the unified `public/comments.csv` + `comments_spoken.csv` +
   `comments_email.csv` + `commenters.csv` + codebook section + two figures.
   **This is the v1 release** — usable without any site.
4. Extend coverage 2024-11 → 2026-03 with `code_emails.py` running live.
5. Build `build_site.py`, enable Pages, publish.
6. Stretch: `commenter_id` bridge between written and spoken commenters.

## 6. Open items

- Packets are ~100 MB each × 300+ — confirm where raw PDFs live (not in git; `data/raw/`
  is already gitignored).
- LLM coding at build time means the "rules-only" property of this pipeline no longer
  holds for the email table. Document that in the codebook, and keep the cached codes
  committed so a rebuild without an API key still reproduces the release.
- Publishing verbatim bodies with sender addresses is your call and matches how the
  city posts the packets. Two things worth keeping out regardless: anything joining a
  commenter to the IRB-covered survey responses, and anything joining to the L2 voter
  file — those stay in `prospective_threats/`, as the current public release already
  does for demographics.
