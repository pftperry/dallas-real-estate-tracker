"""Watchlist scoring engine.

Reads the latest active-listings snapshot and assigns each listing a 0-100
score based on:

  - geographic affinity (Lakewood-orbit weight from the sub-area config)
  - school quality (sub-area school_quality_score)
  - price fit vs. buy box (penalty for being above max, neutral inside, slight
    bonus for being mid-band)
  - $/sqft vs. sub-area median (avoid overpaying for the area)
  - days on market (longer = more leverage)
  - condition / vintage signal (turnkey via year built or post-renovation hint)
  - lot size (larger = better)

Outputs data/stats/latest_watchlist.json with a ranked list.
"""

from __future__ import annotations

import json
import logging
import statistics
import sys
from pathlib import Path

from scrapers.utils import DATA_ROOT, load_sub_areas, utc_now_iso, write_snapshot

LOG = logging.getLogger("score")

WEIGHTS = {
    "lakewood_orbit": 0.30,
    "schools": 0.15,
    "price_fit": 0.20,
    "ppsf_vs_area": 0.15,
    "dom_leverage": 0.10,
    "vintage": 0.05,
    "lot_size": 0.05,
}


def load_active_listings(sqft_min: int = 0) -> list[dict]:
    path = DATA_ROOT / "listings" / "latest_redfin.json"
    if not path.exists():
        LOG.warning("No active listings snapshot at %s", path)
        return []
    payload = json.loads(path.read_text())
    listings = payload.get("listings", [])
    if sqft_min:
        before = len(listings)
        listings = [li for li in listings if (li.get("sqft") or 0) >= sqft_min]
        LOG.info("Filtered <%d sqft: %d -> %d listings", sqft_min, before, len(listings))
    return listings


def compute_area_medians(listings: list[dict]) -> dict[str, float]:
    by_area: dict[str, list[int]] = {}
    for li in listings:
        sa = li.get("sub_area_id")
        ppsf = li.get("ppsf_usd")
        if sa and ppsf:
            by_area.setdefault(sa, []).append(ppsf)
    return {sa: statistics.median(vs) for sa, vs in by_area.items() if vs}


def score_listing(li: dict, area_meta: dict, area_ppsf_median: float | None, buy_box: dict) -> dict:
    sub_orbit = float(area_meta.get("lakewood_orbit", 0.0))
    school_score = float(area_meta.get("school_quality_score", 0)) / 10.0  # 0-1

    price = li.get("price_usd") or 0
    price_min = buy_box["price_min_usd"]
    price_max = buy_box["price_max_usd"]
    if price == 0:
        price_fit = 0.0
    elif price > price_max:
        # Linear penalty up to 20% over.
        overshoot = (price - price_max) / price_max
        price_fit = max(0.0, 1.0 - 5.0 * overshoot)
    elif price < price_min:
        # Below min often means small/condo. Neutral-low.
        undershoot = (price_min - price) / price_min
        price_fit = max(0.3, 1.0 - undershoot)
    else:
        # Mid-band slight bonus.
        mid = (price_min + price_max) / 2
        spread = (price_max - price_min) / 2
        price_fit = 1.0 - 0.2 * abs(price - mid) / spread

    ppsf = li.get("ppsf_usd") or 0
    if ppsf and area_ppsf_median:
        # Buying ~10% under area median = best. Above median penalized.
        ratio = ppsf / area_ppsf_median
        ppsf_vs = max(0.0, 1.2 - ratio) if ratio <= 1.2 else 0.0
    else:
        ppsf_vs = 0.5  # neutral when missing

    dom = li.get("days_on_market") or 0
    # Cap leverage benefit at 90 DOM.
    dom_leverage = min(1.0, dom / 90.0)

    yb = li.get("year_built") or 0
    if yb >= 2010:
        vintage = 1.0
    elif yb >= 1990:
        vintage = 0.7
    elif yb >= 1950:
        vintage = 0.5
    elif yb > 0:
        vintage = 0.3
    else:
        vintage = 0.4

    lot = li.get("lot_size_sqft") or 0
    if lot >= 12000:
        lot_size = 1.0
    elif lot >= 8000:
        lot_size = 0.7
    elif lot >= 5000:
        lot_size = 0.4
    elif lot > 0:
        lot_size = 0.2
    else:
        lot_size = 0.4

    raw = (
        WEIGHTS["lakewood_orbit"] * sub_orbit
        + WEIGHTS["schools"] * school_score
        + WEIGHTS["price_fit"] * price_fit
        + WEIGHTS["ppsf_vs_area"] * ppsf_vs
        + WEIGHTS["dom_leverage"] * dom_leverage
        + WEIGHTS["vintage"] * vintage
        + WEIGHTS["lot_size"] * lot_size
    )
    return {
        "score": round(raw * 100, 1),
        "components": {
            "lakewood_orbit": round(sub_orbit, 2),
            "schools": round(school_score, 2),
            "price_fit": round(price_fit, 2),
            "ppsf_vs_area": round(ppsf_vs, 2),
            "dom_leverage": round(dom_leverage, 2),
            "vintage": round(vintage, 2),
            "lot_size": round(lot_size, 2),
        },
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    cfg_path = Path(__file__).parent.parent / "config" / "sub_areas.json"
    cfg = json.loads(cfg_path.read_text())
    buy_box = cfg["buy_box"]
    area_lookup = {a["id"]: a for a in cfg["sub_areas"]}
    area_lookup.update({a["id"]: a for a in cfg.get("watch_areas", [])})

    areas = load_sub_areas(include_watch=True)  # noqa: F841 (load to validate config)

    sqft_min = int(buy_box.get("sqft_min") or 0)
    listings = load_active_listings(sqft_min=sqft_min)
    LOG.info("Scoring %d listings (sqft_min=%d)", len(listings), sqft_min)
    if not listings:
        write_snapshot("stats", "watchlist", {
            "as_of": utc_now_iso(),
            "n": 0,
            "listings": [],
            "note": "No active listings snapshot available. Run scrapers.redfin first.",
        })
        return 0

    area_medians = compute_area_medians(listings)

    scored = []
    for li in listings:
        sa = li.get("sub_area_id")
        if not sa or sa not in area_lookup:
            continue
        result = score_listing(li, area_lookup[sa], area_medians.get(sa), buy_box)
        scored.append({**li, "_score": result["score"], "_components": result["components"]})

    scored.sort(key=lambda r: r["_score"], reverse=True)
    snapshot = {
        "as_of": utc_now_iso(),
        "n": len(scored),
        "weights": WEIGHTS,
        "buy_box": buy_box,
        "area_ppsf_medians": area_medians,
        "listings": scored,
    }
    out = write_snapshot("stats", "watchlist", snapshot)
    LOG.info("Wrote %s with %d scored listings", out, len(scored))
    return 0


if __name__ == "__main__":
    sys.exit(main())
