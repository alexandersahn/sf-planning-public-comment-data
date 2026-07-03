"""Scrape SF Planning Commission meeting minutes.

Harvests all minutes links from the CPC hearing archives page and downloads
them to data/raw/. Sources:
  - 1998-2018: HTML pages on sfgov.org/sfplanningarchive
  - 2019-2026: PDFs on citypln-m-extnl.sfgov.org / commissions.sfplanning.org / S3

Produces data/raw/manifest.csv with one row per downloaded file.
"""

import csv
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, unquote

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
ARCHIVE_URL = "https://sfplanning.org/cpc-hearing-archives"
# Mirror of the pre-2015 sf-planning.org site (via the "Consolidated Hearings
# and CAC Archives 2014 to 1998" page). page=1000 is the minutes index.
MIRROR_BASE = ("https://sfplanning.s3.amazonaws.com/default/files/meetingarchive/"
               "planning_dept/sf-planning.org/")
MIRROR_MINUTES_INDEX = MIRROR_BASE + "index.aspx-page%3D1000.html"

MONTHS = ("january february march april may june july august september "
          "october november december "
          # typos that appear in archive link labels
          "janaury feburary spetember septemeber ocotber").split()
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (research; alexander.sahn@gmail.com)"}
DELAY = 0.4  # seconds between requests


def harvest_links():
    """Parse the archive page. Returns list of dicts with url, kind, label, row_date."""
    resp = requests.get(ARCHIVE_URL, headers=UA, timeout=60)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    records = []
    seen = set()
    # The page is organized as tables, one per year block. Rows: date | agenda | minutes | video...
    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if not cells:
                continue
            row_text = " ".join(c.get_text(" ", strip=True) for c in cells)
            for a in tr.find_all("a", href=True):
                href = urljoin(ARCHIVE_URL, a["href"])
                label = a.get_text(" ", strip=True)
                low = href.lower()
                is_minutes = (
                    "_min" in low.rsplit("/", 1)[-1]
                    or re.search(r"-minutes(-\d+)?$", low)
                    or "minutes" in label.lower()
                )
                if not is_minutes:
                    continue
                if href in seen:
                    continue
                seen.add(href)
                kind = "pdf" if low.endswith(".pdf") else "html"
                records.append(
                    {"url": href, "kind": kind, "label": label, "row_text": row_text[:200]}
                )
    return records


def _mirror_url(href):
    """Resolve a relative mirror href, %-encoding '=' to match S3 key names."""
    return MIRROR_BASE + href.replace("=", "%3D")


def harvest_mirror():
    """Crawl the 1998-2014 S3 mirror: minutes index -> year pages -> minutes pages.

    Year pages link either to per-month pages (early years, several meetings
    per document) or per-meeting pages (later years). Labels are month names
    or dates; nav links are excluded by label.
    """
    session = requests.Session()
    session.headers.update(UA)
    resp = session.get(MIRROR_MINUTES_INDEX, timeout=60)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    year_links = []
    for a in soup.find_all("a", href=True):
        label = a.get_text(strip=True)
        if re.fullmatch(r"(19|20)\d{2}", label) and "index.aspx-page" in a["href"]:
            year_links.append((label, _mirror_url(a["href"])))

    records = []
    seen = set()
    for year, yurl in year_links:
        time.sleep(DELAY)
        try:
            r = session.get(yurl, timeout=60)
            r.raise_for_status()
        except Exception as e:  # noqa: BLE001
            print(f"ERR year page {year}: {e}")
            continue
        ysoup = BeautifulSoup(r.text, "lxml")
        for a in ysoup.find_all("a", href=True):
            href = a["href"]
            label = a.get_text(strip=True)
            low_label = label.lower()
            looks_dateish = (
                any(low_label.startswith(m) for m in MONTHS)
                or re.match(r"\d{1,2}/\d{1,2}/\d{2,4}", low_label)
            )
            is_content = href.startswith("modules/") or (
                "index.aspx-page" in href and looks_dateish
            )
            if not (is_content and looks_dateish):
                continue
            url = _mirror_url(href)
            if url in seen:
                continue
            seen.add(url)
            records.append({
                "url": url, "kind": "html",
                "label": f"{label} ({year})", "row_text": f"mirror year {year}",
            })
    return records


def local_name(url, kind):
    tail = unquote(url.rstrip("/").rsplit("/", 1)[-1])
    tail = re.sub(r"[^A-Za-z0-9._-]", "_", tail)
    if kind == "html" and not tail.endswith((".html", ".htm")):
        tail += ".html"
    return tail


def download(records):
    session = requests.Session()
    session.headers.update(UA)
    manifest_path = RAW / "manifest.csv"
    rows = []
    for i, rec in enumerate(records):
        sub = RAW / ("pdf" if rec["kind"] == "pdf" else "html")
        dest = sub / local_name(rec["url"], rec["kind"])
        status = "cached"
        if not dest.exists() or dest.stat().st_size == 0:
            try:
                r = session.get(rec["url"], timeout=90)
                r.raise_for_status()
                dest.write_bytes(r.content)
                status = "downloaded"
            except Exception as e:  # noqa: BLE001
                status = f"error: {e}"
            time.sleep(DELAY)
        rows.append({**rec, "file": str(dest.relative_to(ROOT)), "status": status})
        if (i + 1) % 50 == 0:
            print(f"{i + 1}/{len(records)} done", flush=True)
    with open(manifest_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["url", "kind", "label", "row_text", "file", "status"])
        w.writeheader()
        w.writerows(rows)
    errs = [r for r in rows if r["status"].startswith("error")]
    print(f"Total: {len(rows)}, errors: {len(errs)}")
    for r in errs[:20]:
        print("ERR", r["url"], r["status"])


if __name__ == "__main__":
    recs = harvest_links() + harvest_mirror()
    # de-dup across sources
    dedup, seen = [], set()
    for r in recs:
        if r["url"] not in seen:
            seen.add(r["url"])
            dedup.append(r)
    recs = dedup
    print(f"harvested {len(recs)} minutes links "
          f"({sum(1 for r in recs if r['kind'] == 'pdf')} pdf, "
          f"{sum(1 for r in recs if r['kind'] == 'html')} html)")
    if "--dry-run" in sys.argv:
        for r in recs[:10]:
            print(r["kind"], r["url"])
    else:
        download(recs)
