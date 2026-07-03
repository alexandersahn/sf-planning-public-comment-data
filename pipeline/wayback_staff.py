"""Build a Planning Department staff panel over time from Wayback Machine
snapshots of the department's staff directory.

Eras / sources:
  A. 2011-2016  sf-planning.org/index.aspx?page=2744  ("Phone, Location &
     Hours" — carries the staff directory; names recovered from
     first.last@sfgov.org emails), quarterly.
  B. 2016-2019  sf-planning.org/staff-directory (same email extraction),
     quarterly.
  C. 2019-2026  sfplanning.org/staff-directory (paginated Drupal table:
     name / title+email cells; ?page=0..N archived), semiannual.

Pre-2011 staff have no archived directory; the minutes' own STAFF IN
ATTENDANCE rosters (parsed elsewhere) cover them.

Outputs:
  data/raw/staff_panel.csv       one row per (snapshot, name)
  data/processed/staff_tenure.csv  name, first_seen, last_seen, n_snapshots
"""

import csv
import html as html_mod
import re
import time
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"

UA = {"User-Agent": "research staff-panel builder (alexander.sahn@gmail.com)"}
WB = "http://web.archive.org/web/{ts}id_/{url}"
DELAY = 1.5

NON_PERSON = re.compile(
    r"(?i)^(pic|planning|cpc|commissions?|info|web|press|admin|reception|"
    r"records|zoning|preservation|environmental|permit|staff|office|hpc)")


def quarterly(start_year, start_q, end_year, end_q, step=3):
    dates = []
    y, m = start_year, start_q
    while (y, m) <= (end_year, end_q):
        dates.append(f"{y}{m:02d}15")
        m += step
        while m > 12:
            m -= 12
            y += 1
    return dates


def fetch(ts, url, session):
    try:
        r = session.get(WB.format(ts=ts, url=url), timeout=120)
        if r.status_code != 200:
            return None, None
        actual = None
        m = re.search(r"/web/(\d{8})", r.url)
        if m:
            actual = m.group(1)
        return r.text, actual
    except Exception:  # noqa: BLE001
        return None, None


def names_from_emails(html):
    # staff emails are often HTML-entity-obfuscated (&#112;&#105;...)
    html = html_mod.unescape(html)
    out = set()
    for em in set(re.findall(r"([\w\-]+\.[\w\-]+)@sfgov\.org", html)):
        first, _, last = em.partition(".")
        if (NON_PERSON.match(first) or NON_PERSON.match(last)
                or len(first) < 2 or len(last) < 2
                or any(ch.isdigit() for ch in em)):
            continue
        out.add((f"{first.capitalize()} {last.replace('-', '-').title()}", em + "@sfgov.org", ""))
    return out


def names_from_table(html):
    """Modern Drupal directory: rows of Name | Title+email | Division | ..."""
    soup = BeautifulSoup(html, "lxml")
    out = set()
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 2:
            continue
        name = re.sub(r"\s+", " ", tds[0].get_text(" ", strip=True)).strip()
        blob = tds[1].get_text(" ", strip=True)
        em = re.search(r"[\w\-.]+@sfgov\.org", blob)
        title = re.sub(r"[\w\-.]+@sfgov\.org.*", "", blob).strip()
        if 2 <= len(name.split()) <= 4 and name[0].isupper():
            out.add((name, em.group(0) if em else "", title[:60]))
    return out


def main():
    session = requests.Session()
    session.headers.update(UA)
    rows = []
    seen_snapshots = set()

    def record(source, ts_actual, found):
        for name, email, title in found:
            rows.append({"snapshot": ts_actual, "source": source,
                         "name": name, "email": email, "title": title})

    # --- Era A: aspx phone/staff page, quarterly 2011Q2-2016Q1
    for ts in quarterly(2011, 5, 2016, 2):
        html, actual = fetch(ts, "http://www.sf-planning.org/index.aspx?page=2744", session)
        time.sleep(DELAY)
        if not html or (actual, "aspx") in seen_snapshots:
            continue
        seen_snapshots.add((actual, "aspx"))
        found = names_from_emails(html)
        print(f"aspx {ts} -> {actual}: {len(found)} names", flush=True)
        record("aspx_2744", actual, found)

    # --- Era B: old staff-directory, quarterly 2016Q2-2019Q2
    for ts in quarterly(2016, 4, 2019, 4):
        html, actual = fetch(ts, "http://sf-planning.org/staff-directory", session)
        time.sleep(DELAY)
        if not html or (actual, "dir16") in seen_snapshots:
            continue
        seen_snapshots.add((actual, "dir16"))
        found = names_from_emails(html)
        print(f"dir16 {ts} -> {actual}: {len(found)} names", flush=True)
        record("staffdir_2016", actual, found)

    # --- Era C: modern paginated directory, semiannual 2019H2-2026
    for ts in quarterly(2019, 9, 2026, 3, step=6):
        found_all = set()
        actual0 = None
        empty = 0
        for page in range(0, 45):
            url = f"https://sfplanning.org/staff-directory?page={page}"
            html, actual = fetch(ts, url, session)
            time.sleep(DELAY)
            if not html:
                empty += 1
                if empty >= 2:
                    break
                continue
            got = names_from_table(html)
            if not got:
                empty += 1
                if empty >= 2:
                    break
                continue
            empty = 0
            if actual0 is None:
                actual0 = actual
            before = len(found_all)
            found_all |= got
            if len(found_all) == before and page > 0:
                break  # repeating content (past last page)
        print(f"dir19 {ts} -> {actual0}: {len(found_all)} names", flush=True)
        if found_all:
            record("staffdir_2019", actual0 or ts, found_all)

    with open(RAW / "staff_panel.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["snapshot", "source", "name", "email", "title"])
        w.writeheader()
        w.writerows(rows)

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["snapshot"].astype(str).str[:8], format="%Y%m%d")
    tenure = (df.groupby("name")
              .agg(first_seen=("date", "min"), last_seen=("date", "max"),
                   n_snapshots=("date", "nunique"),
                   email=("email", "first"), title=("title", "last"))
              .reset_index())
    tenure.to_csv(OUT / "staff_tenure.csv", index=False)
    print(f"panel rows: {len(df)}, unique staff: {len(tenure)}")


if __name__ == "__main__":
    main()
