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

| variable | description |
|---|---|
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
| is_commissioner | 1 if the speaker is listed among that meeting's "COMMISSIONERS PRESENT" |
| role_long | speaker role/interest-group classification (taxonomy from Sahn's AJPS pipeline): Planning Staff, Commissioner, Supervisor's Office, Mayor's Office, DR Team, Project Team, Legal, Neighborhood Association, Commercial Association, Tenant Association, Construction, YIMBY, SPUR, Slow Growth, Anti-Displacement, Affordable Housing Developer, Religious, Social Services, Race/Immigration/LGBTQ Groups, Community Benefit District, Chamber of Commerce. Sources, in precedence order: project-role phrases in the comment/role_title; attendance rosters; organization classification rules; the registered neighborhood-group roster; the author's name-level lookups and manual corrections |
| role_group | coarse grouping of role_long: Planning Staff, Project Team, DR Team, Neighborhood Association, Business Groups, Housing Interest Groups, Pro-Development Interest Groups, Social Interest Groups, Inter-Governmental |
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
