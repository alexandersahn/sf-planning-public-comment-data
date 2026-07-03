# San Francisco Planning Commission Public Comment Data, 1998–2026

Who speaks at land-use hearings, what they say, and what the Planning
Commission decides. This dataset parses **every San Francisco Planning
Commission meeting's minutes from January 1998 to the present** into
structured records: agenda items with staff recommendations and commission
actions, and each public comment with the speaker's name, recorded polarity
(support / oppose / neutral), the stenographer's summary of what they said,
and the speaker's role or organizational affiliation. Items are joined to
San Francisco Planning Department project records (unit counts, uses,
locations).

**Current coverage:** 1,252 meetings · 25,560 agenda items · 73,590 public
comments · 24,020 unique speakers · January 1998 – March 2026. Updated
periodically as new minutes are posted.

## Relationship to the AJPS article

This dataset extends and rebuilds the data used in:

> Sahn, Alexander. 2025. "Public Comment and Public Policy."
> *American Journal of Political Science* 69(2): 685–700.
> https://doi.org/10.1111/ajps.12900

**It is not the replication archive for that article** — the exact data and
code behind the published results are permanently archived at the
[AJPS Dataverse](https://doi.org/10.7910/DVN/WZOC7H). This repository is a
successor build: the time series runs through the present rather than March
2022, every meeting was re-scraped and re-parsed with a new pipeline, and
several errors in the original data were corrected along the way (duplicate
meetings, mis-dated minutes, and bullet-point continuation lines that were
counted as additional negative speakers). Analyses run on this dataset will
therefore differ — in most cases slightly, and in the case of
negative-comment counts noticeably — from the published replication data.
It also excludes the proprietary L2 voter-file variables (demographics,
addresses, registration) that appear in the article.

## The data (`public/`)

| file | unit | contents |
|---|---|---|
| `meetings.csv` | meeting | date, type, start/adjournment times, staff & commissioner attendance rosters, source URL |
| `items.csv.gz` | agenda item | section, case number & entitlement type, full item text, staff recommendation, commission action, votes, coded outcomes (approve / approve w. conditions / disapprove / continuance / withdraw / no action), project attributes from DataSF (units, uses, address), parcel coordinates |
| `comments.csv` | public comment | speaker name (raw + cleaned), title, role/organization, interest-group classification, polarity (stenographer-recorded, role-implied, or model-imputed — flagged by source), comment summary, extraction method |
| `staff_tenure.csv` | staff member | Planning Department staff panel from Wayback Machine directory snapshots, 2011–2026 |
| `name_crosswalk.csv` | name pair | applied and candidate name merges, for record linkage |
| `codebook.md` | — | full variable documentation |

`items.csv.gz` reads directly with `pandas.read_csv("items.csv.gz")` or
`readr::read_csv("items.csv.gz")`.

## Sources

- **Minutes:** [SF Planning CPC hearing archives](https://sfplanning.org/cpc-hearing-archives)
  (2019–present PDFs; 2015–2018 sfgov.org archive pages; 1998–2014 via the
  mirrored legacy site on S3).
- **Projects:** DataSF, [Planning Department Records – Projects](https://data.sfgov.org/Economy-and-Community/Planning-Department-Records-Projects/qvu5-m3a2).
- **Geocoding:** DataSF, [Addresses with Units – EAS](https://data.sfgov.org/Geographic-Locations-and-Boundaries/Addresses-with-Units-Enterprise-Addressing-System/ramy-di5m)
  (parcel centroids and address points; no commercial geocoder used).
- **Staff panel:** Wayback Machine snapshots of the Planning Department
  staff directory.

Polarity signs are the commission secretary's own +/−/= notations where
recorded (systematic from ~2005). For unsigned comments with text, a
classifier trained on the 45k stenographer-signed comments imputes polarity
(held-out accuracy 0.93 at the acceptance threshold); imputed values are in
separate columns and flagged by `sign_source`. See `public/codebook.md`.

## Rebuilding / updating

```bash
git clone <this repo> && cd <repo>
./update.sh          # incremental refresh: new minutes + fresh DataSF pulls
./update.sh --full   # additionally refreshes the Wayback staff panel
```

The pipeline (Python 3; see `requirements.txt`; `pdftotext` from poppler must
be on PATH) is fully deterministic and incremental — already-downloaded
minutes are cached in `data/raw/`, so a quarterly update only fetches new
hearings. Stages, each a documented script in `pipeline/`:

1. `scrape.py` / `retry_failed.py` — harvest and download all minutes
2. `fetch_datasf.py` — DataSF project records and EAS geocoding data
3. `build_items.py` — parse minutes into meetings / sections / items / vote blocks
4. `build_comments.py` + `clean_names.py` — split speaker lists; clean names
5. `build_projects.py` — outcome coding, DataSF join, geocoding
6. `wayback_staff.py` + `assign_roles.py` — staff panel; role / interest-group classification
7. `impute_polarity.py` — polarity model for unsigned comments
8. `finalize.py` — assemble `public/`

Every run writes coverage and quality reports to `data/validation/`
(parse coverage vs. the published data, extraction-method shares, every name
merge applied, classifier diagnostics, join rates).

## Citing

Please cite the AJPS article (above) and this dataset; see `CITATION.cff`.

## License

Code: MIT. Data: CC BY 4.0. The underlying minutes and administrative
records are public documents of the City and County of San Francisco.
