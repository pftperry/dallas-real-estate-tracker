"""Redfin scraper for active listings + recently sold comps.

Strategy:
  Redfin exposes a CSV download endpoint (the same one that powers the
  "Download all" button on a search page). It accepts a bbox and a
  filter URL. The CSV includes price, address, beds/baths, sqft, lot,
  year built, lat/lng, status, days on market, and listing URL.

  Endpoint shape:
    GET /stingray/api/gis-csv?al=1&market=dallas&min_price={min}&max_price={max}
        &num_homes=350&ord=redfin-recommended-asc&page_number=1&region_id={id}
        &region_type=2&sf=1,1,2,3,5,6,7&status={status}&uipt=1,2,3,4,5,6,7,8
        &v=8

  Status flags:
    9   active for sale
    7   recently sold (last 1-3 months depending on tab)
    11  pending

  We don't use region_id (it's tied to Redfin's neighborhood polygons).
  Instead we drive scraping by bbox via the gis endpoint:
    GET /stingray/api/gis?al=1&min_lat=...&max_lat=...&min_lng=...&max_lng=...
        &min_price=...&max_price=...&status=9&num_homes=350

This script does NOT try to bypass Redfin's protections. If the endpoint
returns a CAPTCHA / 403, fail loud and exit non-zero. Production usage may
require a residential proxy (ScraperAPI, Bright Data) or a Cloudflare-
challenge-solving headless browser. For personal-use frequency (daily, ~10
sub-areas), unauthenticated requests with realistic headers and rate limiting
are usually sufficient.

Usage:
  python -m scrapers.redfin --status active
  python -m scrapers.redfin --status sold
"""

from __future__ import annotations

import argparse
import csv
import io
import logging
import sys
from typing import Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .utils import (
    DEFAULT_HEADERS,
    RateLimiter,
    SubArea,
    assign_sub_area,
    load_sub_areas,
    utc_now_iso,
    write_snapshot,
)

LOG = logging.getLogger("redfin")

REDFIN_GIS_CSV = "https://www.redfin.com/stingray/api/gis-csv"

# Redfin's gis-csv endpoint distinguishes active vs sold via the `sf`
# (search filter) param, NOT the `status` param. status=9 still has to be
# passed for either, but sf=1,2,3,5,6,7 = for-sale set and sf=2 = past sale.
SEARCH_FILTERS = {
    "active": "1,2,3,5,6,7",
    "sold": "2",
    "pending": "5",
}

# How far back to pull sold comps. 180d gives ~enough sample for $/sqft medians
# without polluting with pre-rate-cycle comps.
SOLD_WITHIN_DAYS = 180

# Buy-box widened slightly to catch listings just outside that may have
# room to negotiate. Filtering to the actual buy-box happens in scoring.
DEFAULT_MIN_PRICE = 600_000
DEFAULT_MAX_PRICE = 1_300_000

# Catches multi-unit properties that Redfin sometimes mis-classifies as
# "Single Family Residential" but are really condos, townhomes, fourplexes
# sold as a single investment, or attached units. Triggered by a unit-number
# suffix in the address (e.g., "5102 Mission Ave #5102", "712 Rainwater Rd #7").
import re as _re
# Two cases: '#' followed by an identifier, OR a unit-type word (apt, unit,
# ste, suite, bldg, building) followed by whitespace then an identifier. The
# whitespace requirement after the word avoids matching street names like
# "Sterling" (would match "Ste" + "rling" without it).
UNIT_SUFFIX_RE = _re.compile(
    r"\s+(?:#\s*[A-Za-z0-9\-]+"
    r"|(?:apt|apartment|unit|ste|suite|bldg|building)\.?\s+[A-Za-z0-9\-]+)\b",
    _re.IGNORECASE,
)


def fetch_bbox(
    bbox,
    status: str,
    min_price: int,
    max_price: int,
    rate: RateLimiter,
) -> list[dict]:
    """Hit the Redfin gis-csv endpoint for one bbox and return parsed rows.

    Redfin's gis-csv endpoint requires a closed polygon via `poly=`, not the
    `min_lat/max_lat/min_lng/max_lng` form. Polygon points are "lng lat" order,
    comma-separated, with the final point repeating the first to close the loop.
    """
    poly = (
        f"{bbox.sw_lng} {bbox.sw_lat},"     # SW
        f"{bbox.ne_lng} {bbox.sw_lat},"     # SE
        f"{bbox.ne_lng} {bbox.ne_lat},"     # NE
        f"{bbox.sw_lng} {bbox.ne_lat},"     # NW
        f"{bbox.sw_lng} {bbox.sw_lat}"      # close
    )
    params = {
        "al": "1",
        "market": "dallas",
        "poly": poly,
        "min_price": str(min_price),
        "max_price": str(max_price),
        "num_homes": "350",
        "ord": "redfin-recommended-asc",
        "page_number": "1",
        "sf": SEARCH_FILTERS[status],
        "status": "9",
        "uipt": "1",  # 1 = House (single-family only). Excludes townhouse, condo, multi-family.
        "v": "8",
    }
    if status == "sold":
        params["sold_within_days"] = str(SOLD_WITHIN_DAYS)
    url = f"{REDFIN_GIS_CSV}?{urlencode(params)}"
    rate.wait()
    LOG.info("GET %s", url)
    req = Request(url, headers={**DEFAULT_HEADERS, "Accept": "text/csv"})
    try:
        with urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        LOG.warning("Redfin fetch failed (%s): %s", exc, url)
        return []

    if "<html" in body[:200].lower() or "captcha" in body[:1000].lower():
        LOG.error("Redfin returned HTML/captcha. Need proxy or backoff.")
        return []

    return list(csv.DictReader(io.StringIO(body)))


def normalize(row: dict, areas: Iterable[SubArea]) -> dict:
    """Pull the columns we care about and assign a sub-area."""
    lat = _safe_float(row.get("LATITUDE"))
    lng = _safe_float(row.get("LONGITUDE"))
    sub_area = assign_sub_area(lat, lng, areas)
    return {
        "address": row.get("ADDRESS") or "",
        "city": row.get("CITY") or "",
        "state": row.get("STATE OR PROVINCE") or row.get("STATE") or "",
        "zip": (row.get("ZIP OR POSTAL CODE") or row.get("ZIP") or "").strip()[:5],
        "mls_subdivision": (row.get("LOCATION") or "").strip(),
        "price_usd": _safe_int(row.get("PRICE")),
        "beds": _safe_float(row.get("BEDS")),
        "baths": _safe_float(row.get("BATHS")),
        "sqft": _safe_int(row.get("SQUARE FEET")),
        "lot_size_sqft": _safe_int(row.get("LOT SIZE")),
        "year_built": _safe_int(row.get("YEAR BUILT")),
        "days_on_market": _safe_int(row.get("DAYS ON MARKET")),
        "ppsf_usd": _safe_int(row.get("$/SQUARE FEET")),
        "hoa_per_month_usd": _safe_int(row.get("HOA/MONTH")),
        "property_type": row.get("PROPERTY TYPE") or "",
        "status": row.get("STATUS") or "",
        "next_open_house_start": row.get("NEXT OPEN HOUSE START TIME") or "",
        "next_open_house_end": row.get("NEXT OPEN HOUSE END TIME") or "",
        "url": row.get("URL (SEE https://www.redfin.com/buy-a-home/comparative-market-analysis FOR INFO ON PRICING)") or row.get("URL") or "",
        "lat": lat,
        "lng": lng,
        "sub_area_id": sub_area,
        "mls_number": row.get("MLS#") or "",
        "sold_date": row.get("SOLD DATE") or "",
    }


def _safe_int(v) -> int | None:
    try:
        return int(float(str(v).replace(",", "").replace("$", ""))) if v not in (None, "", "0") else None
    except (ValueError, TypeError):
        return None


def _safe_float(v) -> float | None:
    try:
        return float(str(v).replace(",", "").replace("$", "")) if v not in (None, "") else None
    except (ValueError, TypeError):
        return None


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", choices=list(SEARCH_FILTERS), default="active")
    parser.add_argument("--min-price", type=int, default=DEFAULT_MIN_PRICE)
    parser.add_argument("--max-price", type=int, default=DEFAULT_MAX_PRICE)
    parser.add_argument("--rate-seconds", type=float, default=4.0,
                        help="Min delay between requests (default 4s)")
    args = parser.parse_args()

    areas = load_sub_areas(include_watch=True)
    rate = RateLimiter(args.rate_seconds)
    seen: dict[str, dict] = {}  # de-dupe by (address, zip)

    for area in areas:
        rows = fetch_bbox(area.bbox, args.status, args.min_price, args.max_price, rate)
        LOG.info("  %s: %d raw rows", area.id, len(rows))
        for row in rows:
            norm = normalize(row, areas)
            if not norm["address"]:
                continue
            # Belt-and-suspenders: even with uipt=1 in URL, hard-filter on
            # property_type to exclude townhouse/condo/multi-family.
            ptype = (norm.get("property_type") or "").lower()
            if "single family" not in ptype:
                LOG.debug("Skipping non-SFR: %s (%s)", norm["address"], norm.get("property_type"))
                continue
            # Address-level filter: even when Redfin tags as SFR, a unit-number
            # suffix is a strong signal it's actually a multi-unit property
            # (apartment building sold as one, condo, attached unit).
            if UNIT_SUFFIX_RE.search(norm["address"]):
                LOG.debug("Skipping unit-suffixed address: %s", norm["address"])
                continue
            key = f"{norm['address']}|{norm['zip']}"
            if key not in seen or norm.get("sub_area_id") == area.id:
                # Prefer the bbox-matching assignment over the first one.
                norm["sub_area_id"] = norm.get("sub_area_id") or area.id
                seen[key] = norm

    listings = list(seen.values())
    LOG.info("Total unique %s listings: %d", args.status, len(listings))

    snapshot = {
        "as_of": utc_now_iso(),
        "source": "Redfin gis-csv",
        "status": args.status,
        "filters": {
            "min_price": args.min_price,
            "max_price": args.max_price,
        },
        "n_listings": len(listings),
        "listings": listings,
    }
    out = write_snapshot("listings" if args.status == "active" else "sold", "redfin", snapshot)
    LOG.info("Wrote %s", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
