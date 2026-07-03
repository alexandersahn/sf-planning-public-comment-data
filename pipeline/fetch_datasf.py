"""Fetch project data from DataSF (Socrata API).

1. Planning Department Records - Projects (qvu5-m3a2) — replaces the deprecated
   SF Planning Permitting Data (kncr-c6jw) used in the original paper.
2. Addresses with Units - EAS (ramy-di5m) — used to build parcel (block/lot)
   centroids, since the new Projects dataset no longer carries lat/lon.

Outputs:
  data/raw/datasf_projects.csv
  data/raw/parcel_centroids.csv
"""

import io
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
PAGE = 50000


def fetch_all(resource, select=None, page=PAGE):
    frames = []
    offset = 0
    while True:
        params = {"$limit": page, "$offset": offset, "$order": ":id"}
        if select:
            params["$select"] = select
        r = requests.get(f"https://data.sfgov.org/resource/{resource}.csv",
                         params=params, timeout=300)
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text), low_memory=False)
        if df.empty:
            break
        frames.append(df)
        print(f"{resource}: fetched {offset + len(df)} rows", flush=True)
        if len(df) < page:
            break
        offset += page
        time.sleep(0.5)
    return pd.concat(frames, ignore_index=True)


def main():
    projects = fetch_all("qvu5-m3a2")
    projects.to_csv(RAW / "datasf_projects.csv", index=False)
    print("projects:", projects.shape)

    addr = fetch_all("ramy-di5m",
                     select="parcel_number,block,lot,address,latitude,longitude")
    addr = addr.dropna(subset=["latitude", "longitude"])
    cent = (addr.dropna(subset=["parcel_number"]).groupby("parcel_number")
            .agg(block=("block", "first"), lot=("lot", "first"),
                 latitude=("latitude", "mean"), longitude=("longitude", "mean"),
                 n_addresses=("latitude", "size"))
            .reset_index())
    cent.to_csv(RAW / "parcel_centroids.csv", index=False)
    print("parcel centroids:", cent.shape)

    # address-point lookup (base address without unit) for fallback geocoding
    pts = addr.dropna(subset=["address"]).copy()
    pts["address_key"] = (pts["address"].str.upper()
                          .str.replace(r"\s+", " ", regex=True).str.strip())
    apts = (pts.groupby("address_key")
            .agg(latitude=("latitude", "mean"), longitude=("longitude", "mean"))
            .reset_index())
    apts.to_csv(RAW / "address_points.csv", index=False)
    print("address points:", apts.shape)


if __name__ == "__main__":
    main()
