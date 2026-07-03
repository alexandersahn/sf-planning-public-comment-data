"""Retry failed downloads from the manifest, slower, fixing known bad hosts."""

import csv
import time
from pathlib import Path

import requests

import scrape

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"

HOST_FIXES = {
    "commision.sfplanning.org": "commissions.sfplanning.org",
    "commissions.sfplanning.org4": "commissions.sfplanning.org",
    # sfgov.org 301s to www; go straight there to avoid the redirect hop
    "sfgov.org": "www.sfgov.org",
}


def main():
    rows = list(csv.DictReader(open(RAW / "manifest.csv")))
    session = requests.Session()
    session.headers.update(scrape.UA)
    n_fixed = n_fail = 0
    for r in rows:
        if not r["status"].startswith("error"):
            continue
        url = r["url"]
        for bad, good in HOST_FIXES.items():
            url = url.replace("//" + bad + "/", "//" + good + "/")
        dest = ROOT / r["file"]
        ok = False
        for attempt in range(4):
            try:
                resp = session.get(url, timeout=90)
                if resp.status_code == 425 or resp.status_code == 429:
                    time.sleep(10 * (attempt + 1))
                    continue
                resp.raise_for_status()
                dest.write_bytes(resp.content)
                ok = True
                break
            except Exception as e:  # noqa: BLE001
                err = str(e)
                time.sleep(5)
        if ok:
            r["status"] = "downloaded"
            n_fixed += 1
        else:
            r["status"] = f"error: {err[:80]}"
            n_fail += 1
            print("STILL FAILING:", url)
        time.sleep(2.5)
        if (n_fixed + n_fail) % 20 == 0:
            print(f"retried {n_fixed + n_fail}, ok {n_fixed}", flush=True)

    with open(RAW / "manifest.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"fixed {n_fixed}, still failing {n_fail}")


if __name__ == "__main__":
    main()
