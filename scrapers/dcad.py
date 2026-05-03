"""DCAD parcel ETL.

DCAD (Dallas Central Appraisal District) publishes bulk data as zipped CSVs:
https://www.dallascad.org/dataproducts.aspx

Files of interest in the bundle:
  - APPRAISAL_INFO.CSV   (parcel-level appraised value, exemptions)
  - ACCOUNT_APPRL_YEAR.CSV (year-by-year appraisal history)
  - RES_DETAIL.CSV       (residential characteristics: sqft, year built, beds/baths)
  - ACCOUNT_INFO.CSV     (situs address, owner)
  - parcel.shp / .dbf    (GIS polygons via separate GIS bundle)

Texas is a non-disclosure state: DCAD has APPRAISED values, NOT sale prices.
Use this scraper for parcel characteristics, ownership, and tax history only.
Sale prices come from the Redfin scraper.

Usage:
  python -m scrapers.dcad           # full refresh
  python -m scrapers.dcad --dry-run # parse cached zip without re-downloading
"""

from __future__ import annotations

import argparse
import csv
import io
import logging
import sys
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

from .utils import (
    DATA_ROOT,
    DEFAULT_HEADERS,
    SubArea,
    load_sub_areas,
    utc_now_iso,
    write_snapshot,
)

LOG = logging.getLogger("dcad")

DCAD_BULK_URL = "https://www.dallascad.org/ViewPDFs/DCAD2024_CURRENT.ZIP"
CACHE_DIR = DATA_ROOT / ".cache" / "dcad"

# DCAD zip codes that overlap our screen — used to pre-filter the 800k-row file
SCREEN_ZIPS = {"75206", "75214", "75218", "75228", "75231", "75238", "75243"}


def download_bulk_zip(force: bool = False) -> Path:
    """Download (or reuse) the DCAD bulk zip."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out = CACHE_DIR / "dcad_current.zip"
    if out.exists() and not force:
        LOG.info("Using cached DCAD zip: %s", out)
        return out
    LOG.info("Downloading DCAD bulk: %s", DCAD_BULK_URL)
    req = Request(DCAD_BULK_URL, headers=DEFAULT_HEADERS)
    with urlopen(req, timeout=600) as resp, open(out, "wb") as fh:
        fh.write(resp.read())
    return out


def _read_member(zf: zipfile.ZipFile, name_substring: str) -> io.TextIOWrapper:
    for member in zf.namelist():
        if name_substring.lower() in member.lower():
            return io.TextIOWrapper(zf.open(member), encoding="latin-1", newline="")
    raise FileNotFoundError(f"Member matching {name_substring!r} not found in zip")


def parse_parcels(zip_path: Path, areas: list[SubArea]) -> list[dict]:
    """Parse DCAD bulk and return parcels filtered to the screen.

    Filters by zip first (cheap), then by sub-area assignment via address.
    Without GIS shapefiles, sub-area assignment defaults to zip-code overlap;
    refine with parcel.shp lookups when polygon precision is required.
    """
    parcels: list[dict] = []
    zip_to_areas: dict[str, list[str]] = {}
    for area in areas:
        for zc in area.zip_codes:
            zip_to_areas.setdefault(zc, []).append(area.id)

    with zipfile.ZipFile(zip_path) as zf:
        # Build address -> account index from ACCOUNT_INFO
        account_info: dict[str, dict] = {}
        with _read_member(zf, "ACCOUNT_INFO") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                zc_raw = (row.get("PROPERTY_ZIPCODE") or "").strip()[:5]
                if zc_raw not in SCREEN_ZIPS:
                    continue
                account_info[row["ACCOUNT_NUM"]] = row

        # Join with RES_DETAIL for sqft/year built
        res_detail: dict[str, dict] = {}
        with _read_member(zf, "RES_DETAIL") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                acct = row["ACCOUNT_NUM"]
                if acct in account_info:
                    res_detail[acct] = row

        # Join with APPRAISAL_INFO for current year value
        appraisal: dict[str, dict] = {}
        with _read_member(zf, "APPRAISAL_INFO") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                acct = row["ACCOUNT_NUM"]
                if acct in account_info:
                    appraisal[acct] = row

    for acct, info in account_info.items():
        zc = (info.get("PROPERTY_ZIPCODE") or "").strip()[:5]
        candidate_areas = zip_to_areas.get(zc, [])
        if not candidate_areas:
            continue
        det = res_detail.get(acct, {})
        appr = appraisal.get(acct, {})
        parcels.append(
            {
                "account_num": acct,
                "address": (info.get("STREET_NUM", "") + " " + info.get("STREET_NAME", "")).strip(),
                "city": info.get("PROPERTY_CITY", "").strip(),
                "zip": zc,
                "candidate_sub_areas": candidate_areas,
                "year_built": _safe_int(det.get("ACTUAL_YEAR_BUILT")),
                "sqft_living": _safe_int(det.get("TOT_LIVING_AREA_SF")),
                "lot_size_sqft": _safe_int(det.get("LAND_SF")),
                "beds": _safe_int(det.get("NUM_BEDROOMS")),
                "baths": _safe_float(det.get("NUM_FULL_BATHS")),
                "appraised_value_usd": _safe_int(appr.get("TOT_VAL")),
                "appraised_year": _safe_int(appr.get("APPRAISAL_YR")),
                "owner_name": info.get("OWNER_NAME1", "").strip(),
            }
        )
    return parcels


def _safe_int(v) -> int | None:
    try:
        return int(float(str(v).replace(",", ""))) if v not in (None, "", "0") else None
    except (ValueError, TypeError):
        return None


def _safe_float(v) -> float | None:
    try:
        return float(str(v).replace(",", "")) if v not in (None, "") else None
    except (ValueError, TypeError):
        return None


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Use cached zip if present")
    args = parser.parse_args()

    areas = load_sub_areas(include_watch=True)
    LOG.info("Loaded %d sub-areas", len(areas))

    zip_path = download_bulk_zip(force=not args.dry_run)
    parcels = parse_parcels(zip_path, areas)
    LOG.info("Filtered to %d parcels in screen zips", len(parcels))

    snapshot = {
        "as_of": utc_now_iso(),
        "source": "DCAD bulk",
        "source_url": DCAD_BULK_URL,
        "n_parcels": len(parcels),
        "sub_area_ids": [a.id for a in areas],
        "parcels": parcels,
    }
    out = write_snapshot("parcels", "dcad", snapshot)
    LOG.info("Wrote %s", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
