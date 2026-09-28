# San Francisco Planning Commission Public Comment

Who shows up to comment on land use in San Francisco, what they say, and what
the Commission decides.

Every public comment made to the San Francisco Planning Commission in
structured form — spoken testimony from the meeting minutes since 1998, and
written comment from the correspondence packets since 2017 — linked to the
project it concerns and to the Commission's eventual decision on that project.

**1,252 meetings · 25,560 agenda items · 73,002 comments · 28,421 commenters ·
January 1998 – March 2026**

Browse it at [alexandersahn.com/sf_commenter_data](https://alexandersahn.com/sf_commenter_data/).

## What you can do with it

Each comment carries a position — support, oppose, neutral — and the project
it concerns; each project carries the Commission's action and vote. So you can
ask who turns out for which kinds of project, whether opposition predicts
denial, how the composition of commenters shifted as the housing debate did,
and whether the people who write in are the same ones who show up in person.

## The data (`public/`)

| file | unit | contents |
|---|---|---|
| `comments.csv` | comment | who commented, what they said, their position, the project and hearing, and — for spoken comment — their role or organizational affiliation |
| `items.csv.gz` | agenda item | case number, full item text, staff recommendation, Commission action and vote, coded outcome, project attributes from DataSF, coordinates |
| `meetings.csv` | meeting | date, type, times, staff and commissioner attendance |
| `staff_tenure.csv` | staff member | Planning Department staff and when they served, 2011–2026 |
| `person_roster.csv` | commenter | organizational affiliations carried across a commenter's testimony, with the evidence for each |
| `name_crosswalk.csv` | name pair | name variants treated as the same person |
| `codebook.md` | — | every variable, and how each was derived |

`comments.csv` covers both channels; `channel` distinguishes them. Start with
`position`, `id_parent` and `channel`, and read the codebook before using the
polarity or affiliation columns, which come from sources of differing
reliability.

## Where it comes from

- **Spoken comment:** [SF Planning hearing archives](https://sfplanning.org/cpc-hearing-archives)
  — 2019–present PDFs, 2015–2018 sfgov.org archive pages, 1998–2014 via the
  mirrored legacy site.
- **Written comment:** the Commission Packet posted before each hearing, which
  reproduces the correspondence received. Parsed and coded for Sahn and Simko
  (below); the coded corpus ships as `data/reference/emails_coded.csv.gz`.
- **Projects and geocoding:** DataSF
  [Planning Department Records](https://data.sfgov.org/Economy-and-Community/Planning-Department-Records-Projects/qvu5-m3a2)
  and [Addresses with Units](https://data.sfgov.org/Geographic-Locations-and-Boundaries/Addresses-with-Units-Enterprise-Addressing-System/ramy-di5m).

`./update.sh` rebuilds everything from source.

## What to know before using it

**Positions come from three places.** The commission secretary's own +/−/=
marks, systematic from about 2005; a classifier trained on those marks, for
unsigned comments that have text; and LLM coding for written comment.
`position_source` says which, and they are not equally reliable.

**Written comment is matched to projects, not to hearings.** Emails arrive
before a hearing and items get continued, so a message is attached to its
project's first hearing on or after the packet date. Only 37% were heard on
the packet date itself.

**Names are not identities.** `commenter_id` merges spellings of the same
person conservatively — a name match is acted on only with corroborating
evidence, because the corpus contains genuine namesakes.

**No contact details are published.** Senders of written comment appear as a
salted digest, and addresses and phone numbers are redacted from comment text.

## Citing

Please cite the article and the dataset; see `CITATION.cff`.

> Sahn, Alexander. 2025. "Public Comment and Public Policy."
> *American Journal of Political Science* 69(2): 685–700.
> https://doi.org/10.1111/ajps.12900

This is not the replication archive for that article, which is at the
[AJPS Dataverse](https://doi.org/10.7910/DVN/WZOC7H). It is a successor build:
extended to the present, re-parsed, and corrected.

Written comment is from Sahn, Alexander, and Tyler Simko, "Issue
Accountability Among Public Meeting Commenters" (conditionally accepted,
*American Journal of Political Science*).

## License

Code: MIT. Data: CC BY 4.0. The underlying records are public documents of the
City and County of San Francisco.
