# Codebook — San Francisco Planning Commission Public Comment Data, 1998–2026

Three related tables. `meetings.csv` (one row per commission meeting) →
`items.csv` (one row per agenda item; `item_id` is the key) →
`comments.csv` (one row per public comment; links to items via `item_id`).

Sources: San Francisco Planning Commission meeting minutes
(https://sfplanning.org/cpc-hearing-archives and the mirrored pre-2015 archive),
and DataSF *Planning Department Records – Projects* (`qvu5-m3a2`),
*Addresses with Units – EAS* (`ramy-di5m`).

## meetings.csv

| variable | description |
|---|---|
| meeting_date | date of the hearing (YYYY-MM-DD) |
| meeting_type | regular / special / joint (from the minutes header) |
| file | source document the meeting was parsed from |
| start_time, end_time | scheduled start and adjournment time (24h), where stated |
| n_items | agenda items parsed for this meeting |
| n_with_speakers | items with a SPEAKERS block |
| n_comments | public comments extracted for this meeting |
| source_url | URL of the source document |

## items.csv

Meeting/context: `item_id`, `meeting_date`, `meeting_type`, `file`, `source_url`,
`section_letter`, `section` (header as printed), `section_group` (normalized:
Regular Calendar, Consent Calendar, Discretionary Review, Items Proposed for
Continuance, General Public Comment, Public Comment, Administrative, …),
`item_num` (position on the calendar), `record_id` (Planning case number as
printed, e.g. `2015-009140DRP` or `97.669C`), `record_type` (entitlement type
inferred from the case-number suffix: CUA, DRP/DRM, ENV, VAR, PCA, MAP, COA, …),
`id_parent` (case number with the type suffix stripped; join key to project
records).

Minutes text: `item_text` (full agenda-item description), `prelim_rec`
(staff's Preliminary Recommendation), and the recorded blocks `SPEAKERS`,
`ACTION`, `AYES`, `NAYES`, `ABSENT`, `RECUSED`, `EXCUSED`, `MOTION`,
`RESOLUTION` (verbatim).

Outcome coding (ported from Sahn, *Public Comment and Public Policy*):

| variable | description |
|---|---|
| rec_clean / action_clean | keyword classification of the staff recommendation / commission action (approve, disapprove, continuance, adopt resolution, certify eir, uphold pmnd, withdraw, no action, …) |
| rec_dr / action_dr | discretionary-review direction: "dr" (take DR) or "no dr" |
| rec_conditions / action_conditions | 1 if conditions/modifications attached |
| rec_final / action_final | final categories: approve, approve with conditions, disapprove, continuance, no action, withdraw |
| rec_num / action_num | numeric coding: approve 2, approve w/ conditions 1, continuance & no action 0, disapprove & withdraw −1 |
| rec_action_diff | action_num − rec_num |

Keyword flags from the item text: `housing_kw`, `office_kw`, `commercial_kw`,
`demo_kw`, `new_construction_kw`, `adu_kw`.

Project attributes (prefix `prj_`, from DataSF Planning Department Records –
Projects, joined on `id_parent`): record id/status, project name/address,
block/lot, open/close dates, unit counts (net, affordable, existing, proposed),
change-of-use / additions / new-construction / demolition / ADU / legalization
flags, and proposed/existing square footage by use (residential, retail,
office, industrial PDR, medical, CIE), parking.

Location: `latitude`, `longitude`, `geo_source` (`parcel_centroid` = mean of
EAS address points on the project's block/lot; `address_point` = matched by
normalized project address). Coordinates are parcel-level, not exact building
footprints.

## comments.csv

One row per public comment, both channels: spoken testimony parsed from the
meeting minutes (1998–present) and written comment parsed from the hearing
packets (2017–2024). `channel` says which.

Fan-out duplicates are removed, not flagged: an agenda item spanning several
case numbers used to produce several item rows with the whole speaker list
attached to each, so one person speaking once appeared up to 14 times.

Columns that apply to one channel only are blank for the other. `position`
and `position_source` are the two that are safe to use across both — but a
stenographer's recorded `+` and a language model's reading of an email body
are different kinds of evidence, and `position_source` is how you tell them
apart.

| variable | description |
|---|---|
| comment_id | stable id; `s…` spoken, `e…` written |
| channel | `spoken` / `email` |
| position | support / oppose / neutral, harmonised across channels |
| position_source | `stenographer`, `model`, `role` (spoken) or `llm` (written) |
| sender_id | written comment only: salted digest of the sender's address. The addresses themselves are not published; this preserves linkage between messages from the same person |
| subject | written comment only |
| is_campaign, campaign | written comment only: near-identical messages from an organised letter-writing drive, and which drive |
| item_lag_days, item_heard_as_calendared | written comment only: emails arrive before a hearing and items get continued, so the item link is derived as the project's first hearing on or after the packet date. Only 37% were heard on the packet date itself |
| text | the stenographer's summary (spoken) or the message body (written). Email addresses and phone numbers are redacted |
| item_id | agenda item the comment was made on (key into items.csv) |
| meeting_date, record_id, section, item_num | context copied from the item |
| speaker_order | order within the item's speaker list |
| name_clean | cleaned speaker name (typos repaired, titles stripped; blank if anonymous or unrecoverable) |
| name_raw | name as printed in the minutes |
| title | honorific stripped from the name (Supervisor, Dr., Commissioner, …) |
| role_title | role/title recorded with the name ("Legislative aide to Sup. Peskin", "Project Architect", "Deputy City Attorney") — from "Name, Title" comma structures or "Name – Title" dashes |
| organization | organization recorded with the name ("Telegraph Hill Dwellers", "Calle 24") — comma segments that don't read as a role |
| is_anonymous | 1 if the minutes identify the speaker only generically ("Speaker", "(M) Speaker", "name unclear") |
| anon_gender | M/F when the stenographer marked an anonymous speaker's gender |
| is_staff | 1 if the speaker appears in the minutes' own "STAFF IN ATTENDANCE" roster (same meeting or any meeting, 1998–2026) or the 2022 Planning staff directory |
| is_commissioner | 1 if the speaker is listed among that meeting's "COMMISSIONERS PRESENT". **Always 0 in practice**: commissioners speak from the dais and are recorded in the MOTION and ACTION blocks, not in the SPEAKERS lists this table is built from. The column is kept so the filter `is_staff != 1 & is_commissioner != 1` stays correct if that ever changes |
| role_long | speaker role/interest-group classification (taxonomy from Sahn's AJPS pipeline, extended): Planning Staff, Commissioner, Supervisor's Office, Mayor's Office, City Agency, DR Team, Project Team, Legal, Neighborhood Association, Commercial Association, Tenant Association, Construction, Labor, YIMBY, Pro-Housing Advocacy, SPUR, Slow Growth, Anti-Displacement, Historic Preservation, Affordable Housing Developer, Religious, Social Services, Race/Immigration/LGBTQ Groups, Community Benefit District, Chamber of Commerce |
| role_source | how `role_long` was determined — see the note below. Values: `case_role`, `attendance`, `roster_curated`, `stated_org`, `stated_role_title`, `stated_comment`, `nhood_roster`, `lookup_role`, `roster_derived`, `manual` |
| role_group | coarse grouping of role_long: Planning Staff, Project Team, DR Team, Neighborhood Association, Business Groups, Housing Interest Groups, Pro-Development Interest Groups, Social Interest Groups, Inter-Governmental |

### How speakers are classified (`role_long`, `role_source`)

Rules are applied in this order, and `role_source` records which one fired:

| order | `role_source` | rule |
|---|---|---|
| 1 | `case_role` | phrases in the comment or role_title marking the speaker's relation to *this* item — project sponsor, architect, DR requestor, counsel |
| 2 | `attendance` | the meeting's own STAFF IN ATTENDANCE / commissioners-present roster |
| 3 | `roster_curated` | hand-collected organization membership (`pipeline/rosters.py`), from org team and board pages, current and archived |
| 4 | `stated_org`, `stated_role_title`, `stated_comment` | the speaker named an organization in this comment. Comment text is matched only at the start of the summary, where the stenographer records affiliation |
| 5 | `nhood_roster` | the city's registered neighborhood-group roster |
| 6 | `lookup_role` | the AJPS pipeline's name-level lookup |
| 7 | `roster_derived` | the speaker stated an affiliation in *other* comments, and this one falls inside that tenure window (below) |
| — | `manual` | the paper's name-level corrections, applied last and overriding the rest |

**Person-level propagation.** Most speakers name their organization in only
some appearances, which leaves the rest of their testimony unclassified. Step
7 carries a speaker's stated affiliation to their other comments, subject to
four guards: the name must have at least two tokens (single-token names such
as "Gloria" collide constantly); the modal role must account for at least 60%
of that speaker's stated labels; the comment must fall within four years of a
hearing where they did state it; and the name must not be on the Planning
staff roster. Speakers who fail these tests keep only their comment-level
labels. The applied roster ships as `person_roster.csv` (one row per speaker:
`name`, `role_long`, `n_stated`, `n_modal`, `agreement`, `year_lo`,
`year_hi`, `distinct_roles`), so every propagated label can be traced back to
the testimony it was inferred from. The full version, including entries that
were built but failed a guard, is written to
`data/validation/person_roster.csv` during the build.

Case roles (Project Team, DR Team, Legal) are never propagated — they
describe a relationship to one specific case, not a standing affiliation.

**Breaking change from earlier releases.** `YIMBY` previously covered the
YIMBY movement, the Housing Action Coalition and GrowSF together; by volume
it was mostly the Housing Action Coalition. `YIMBY` now means the movement
proper (SFBARF, SF YIMBY, YIMBY Action) and `Pro-Housing Advocacy` the rest.
Both sit in the `Pro-Development Interest Groups` role_group, so series built
on `role_group` are unaffected. A rule that classified any comment beginning
with the word "Density" as YIMBY was also removed; it was matching ordinary
commenters discussing density rather than any organization.
| sign | speaker polarity as recorded by the commission secretary: `+` support, `-` opposition, `=` neutral/unstated. Recorded systematically from ~2005 onward; missing in most earlier minutes |
| sign_imputed | model-imputed polarity for comments with no recorded sign (TF-IDF + logistic regression trained on the 45k stenographer-signed comments; held-out accuracy 0.92 at the 0.70-probability acceptance threshold; see data/validation/polarity_report.txt). Never overrides `sign` |
| sign_prob | model confidence for `sign_imputed` (only values ≥ 0.70 accepted) |
| sign_source | stenographer / role (implied by DR Team −, Project Team/Legal +) / model / blank |
| name_single | 1 if only a single name token was recorded (first or last name alone) |
| comment | the stenographer's summary of the comment (often a short phrase; not a transcript) |
| method | how the record was extracted (sign_lines, sign_inline, comma_list, dash_lines, tone_groups, re_pairs, name_colon, single, first_line_name, same_as_resolved, unparsed) |

Notes:

- `same_as_resolved` records are duplicated from a linked agenda item when the
  minutes said "SPEAKERS: Same as Item 9a" — the same person appears once per
  linked item, by design.
- Polarity (`sign`) is the stenographer's judgment, not the researcher's.
- 1998–2004 minutes usually list speaker names without polarity or comment
  summaries; those comments cannot be imputed either (no text).
- `staff_tenure.csv` is an ancillary panel of Planning Department staff built
  from Wayback Machine snapshots of the department's staff directory
  (quarterly 2011–2019, semiannual 2023–2026; the paginated 2019–2022
  directory was not deep-crawled by the Archive, so that window relies on the
  minutes' attendance rosters). Columns: name, first_seen, last_seen,
  n_snapshots, email, title. `is_staff` in comments.csv uses these tenure
  windows (±1 year) in addition to the per-meeting STAFF IN ATTENDANCE
  rosters and the 2022 directory.
- `name_crosswalk.csv` is an ancillary file for record linkage: every applied
  name merge (`status=applied`, with its rule) plus fuzzy near-duplicate pairs
  that were NOT merged (`status=candidate`, with edit distance, similarity
  ratio, and corpus frequencies). Downstream analyses such as voter-file
  matching can choose their own threshold for treating candidates as the same
  person.
