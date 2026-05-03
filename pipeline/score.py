"""Watchlist scoring engine.

Reads the latest active-listings snapshot and assigns each listing a 0-100
score based on:

  - geographic affinity (Lakewood-orbit weight from the sub-area config)
  - school quality (sub-area school_quality_score)
  - price fit vs. buy box (penalty for being above max, neutral inside, slight
    bonus for being mid-band)
  - $/sqft vs. peer comps (size-normalized: same sub-area + within +/-25% sqft)
  - days on market (longer = more leverage)
  - condition / vintage signal (turnkey via year built)
  - lot size (larger = better)

Plus a busy-street flag (off-score, surfaced separately) for addresses on
known Dallas arterials.

Outputs data/stats/latest_watchlist.json with a ranked list.

Weights aligned to deep-research review (2026-05): location 30%, price fit
20%, lot 10%, schools 10%, $/sqft vs peers 10%, DOM 10%, vintage 10%.
"""

from __future__ import annotations

import json
import logging
import math
import re
import statistics
import sys
from pathlib import Path

from scrapers.utils import DATA_ROOT, load_sub_areas, utc_now_iso, write_snapshot

LOG = logging.getLogger("score")

WEIGHTS = {
    "lakewood_orbit": 0.30,
    "price_fit": 0.20,
    "schools": 0.10,
    "ppsf_vs_peers": 0.10,
    "dom_leverage": 0.10,
    "vintage": 0.10,
    "lot_size": 0.10,
}

# Peer-comp window for size-normalized $/sqft comparison.
PEER_SQFT_WINDOW = 0.25  # +/- 25%
PEER_MIN_COUNT = 3       # need at least 3 peers; otherwise fall back to area median

# Dallas arterial / busy-street name patterns. Used as the cheap "address-on"
# check for listings whose street name itself is an arterial.
BUSY_STREET_PATTERNS = [
    r"\bGarland Rd\b",
    r"\bBuckner Blvd\b",
    r"\bSkillman St\b",
    r"\bSkillman$",
    r"\bAbrams Rd\b",
    r"\bAbrams$",
    r"\bMockingbird Ln\b",
    r"\bMockingbird$",
    r"\bNorthwest Hwy\b",
    r"\bNW Hwy\b",
    r"\bPlano Rd\b",
    r"\bWalnut Hill Ln\b",
    r"\bWalnut Hill$",
    r"\bForest Ln\b",
    r"\bGreenville Ave\b",
    r"\bAudelia Rd\b",
    r"\bAudelia$",
    r"\bRoyal Ln\b",
]
BUSY_STREET_RE = re.compile("|".join(BUSY_STREET_PATTERNS), re.IGNORECASE)

# Approximate Dallas arterial centerlines as (lat, lng) polylines.
# Used for proximity flagging -- catches homes that *back up to* an arterial
# even though the street address is on a quiet residential side street.
# Coordinates are eyeballed from cross-street intersections; threshold is
# generous (100m) so meter-level inaccuracy does not bite. Refine with OSM
# extracts when a tighter threshold matters.
ARTERIALS: dict[str, list[tuple[float, float]]] = {
    "Garland Rd": [
        (32.811, -96.770), (32.825, -96.755), (32.835, -96.738),
        (32.840, -96.715), (32.841, -96.700), (32.853, -96.685),
    ],
    "Buckner Blvd": [
        (32.795, -96.700), (32.825, -96.700), (32.852, -96.698),
        (32.880, -96.690),
    ],
    "Skillman St": [
        (32.815, -96.760), (32.840, -96.760), (32.860, -96.755),
        (32.885, -96.745), (32.910, -96.735),
    ],
    "Abrams Rd": [
        (32.815, -96.768), (32.840, -96.768), (32.860, -96.768),
        (32.885, -96.768), (32.910, -96.770),
    ],
    "Mockingbird Ln": [
        (32.836, -96.785), (32.838, -96.770), (32.840, -96.755),
        (32.842, -96.738), (32.844, -96.720), (32.846, -96.703),
    ],
    "Northwest Hwy": [
        (32.853, -96.785), (32.855, -96.770), (32.857, -96.755),
        (32.860, -96.738), (32.862, -96.720), (32.860, -96.700),
    ],
    "Plano Rd": [
        (32.840, -96.690), (32.870, -96.688), (32.900, -96.685),
    ],
    "Walnut Hill Ln": [
        (32.879, -96.785), (32.881, -96.770), (32.883, -96.755),
        (32.885, -96.738), (32.887, -96.720),
    ],
    "Forest Ln": [
        (32.910, -96.785), (32.911, -96.770), (32.912, -96.755),
        (32.913, -96.738), (32.914, -96.720),
    ],
    "Royal Ln": [
        (32.895, -96.785), (32.896, -96.770), (32.897, -96.755),
        (32.898, -96.738), (32.899, -96.720),
    ],
    "Audelia Rd": [
        (32.870, -96.722), (32.890, -96.722), (32.910, -96.722),
    ],
    "I-635 (LBJ Fwy)": [
        (32.918, -96.785), (32.918, -96.755), (32.918, -96.720),
        (32.918, -96.685),
    ],
}

# Distance threshold (meters) below which a listing is considered "backing
# up to" a busy street. 100m ~= one standard residential lot depth + a
# margin for coordinate inaccuracy.
BUSY_PROXIMITY_M = 100.0


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def _point_to_segment_m(plat: float, plng: float,
                        alat: float, alng: float,
                        blat: float, blng: float) -> float:
    """Approximate point-to-line-segment distance in meters using equirect projection."""
    cos_lat = math.cos(math.radians((alat + blat) / 2))
    px, py = plng * cos_lat, plat
    ax, ay = alng * cos_lat, alat
    bx, by = blng * cos_lat, blat
    dx, dy = bx - ax, by - ay
    seg_sq = dx * dx + dy * dy
    if seg_sq == 0:
        return _haversine_m(plat, plng, alat, alng)
    t = ((px - ax) * dx + (py - ay) * dy) / seg_sq
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t * dx, ay + t * dy
    # Convert closest point back to lat/lng for haversine
    return _haversine_m(plat, plng, cy, cx / cos_lat)


def nearest_arterial(lat: float | None, lng: float | None) -> tuple[str | None, float]:
    """Return (arterial_name, distance_meters) for the nearest arterial,
    or (None, inf) if lat/lng missing."""
    if lat is None or lng is None:
        return None, float("inf")
    best_name, best_d = None, float("inf")
    for name, waypoints in ARTERIALS.items():
        for i in range(len(waypoints) - 1):
            d = _point_to_segment_m(
                lat, lng,
                waypoints[i][0], waypoints[i][1],
                waypoints[i + 1][0], waypoints[i + 1][1],
            )
            if d < best_d:
                best_d, best_name = d, name
    return best_name, best_d


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


def load_sold_comps() -> list[dict]:
    path = DATA_ROOT / "sold" / "latest_redfin.json"
    if not path.exists():
        return []
    return json.loads(path.read_text()).get("listings", [])


def compute_area_medians(listings: list[dict]) -> dict[str, float]:
    by_area: dict[str, list[int]] = {}
    for li in listings:
        sa = li.get("sub_area_id")
        ppsf = li.get("ppsf_usd")
        if sa and ppsf:
            by_area.setdefault(sa, []).append(ppsf)
    return {sa: statistics.median(vs) for sa, vs in by_area.items() if vs}


def peer_ppsf_median(li: dict, sold_pool: list[dict], area_median: float | None) -> tuple[float | None, str]:
    """Return ($/sqft baseline, source label) for a listing.

    Looks for sold comps in the same sub-area within +/-25% of the listing's
    sqft. Falls back to area median if peer set is too small (<3).
    """
    target_sqft = li.get("sqft") or 0
    sa = li.get("sub_area_id")
    if not target_sqft or not sa:
        return area_median, "area_median"

    lo = target_sqft * (1 - PEER_SQFT_WINDOW)
    hi = target_sqft * (1 + PEER_SQFT_WINDOW)
    peers = [
        s["ppsf_usd"]
        for s in sold_pool
        if s.get("sub_area_id") == sa
        and s.get("ppsf_usd")
        and s.get("sqft")
        and lo <= s["sqft"] <= hi
    ]
    if len(peers) >= PEER_MIN_COUNT:
        return statistics.median(peers), f"peer_median (n={len(peers)})"
    return area_median, "area_median (peer set too small)"


def is_busy_street_address(address: str | None) -> bool:
    """Cheap check: does the street name itself match a known arterial?"""
    if not address:
        return False
    return bool(BUSY_STREET_RE.search(address))


def busy_street_assessment(li: dict) -> dict:
    """Return a dict describing busy-street exposure for one listing.

    Combines the address-on check and the proximity-to-centerline check.
    Either signal triggers the busy_street flag.
    """
    addr_match = is_busy_street_address(li.get("address"))
    nearest_name, nearest_d = nearest_arterial(li.get("lat"), li.get("lng"))
    proximity_match = nearest_d <= BUSY_PROXIMITY_M
    return {
        "busy_street": addr_match or proximity_match,
        "busy_address_on": addr_match,
        "busy_proximity": proximity_match,
        "nearest_arterial": nearest_name if nearest_d < 500 else None,
        "nearest_arterial_m": round(nearest_d) if nearest_d < 1_000_000 else None,
    }


def score_listing(
    li: dict,
    area_meta: dict,
    ppsf_baseline: float | None,
    ppsf_baseline_source: str,
    buy_box: dict,
) -> dict:
    sub_orbit = float(area_meta.get("lakewood_orbit", 0.0))
    school_score = float(area_meta.get("school_quality_score", 0)) / 10.0

    price = li.get("price_usd") or 0
    price_min = buy_box["price_min_usd"]
    price_max = buy_box["price_max_usd"]
    if price == 0:
        price_fit = 0.0
    elif price > price_max:
        overshoot = (price - price_max) / price_max
        price_fit = max(0.0, 1.0 - 5.0 * overshoot)
    elif price < price_min:
        undershoot = (price_min - price) / price_min
        price_fit = max(0.3, 1.0 - undershoot)
    else:
        mid = (price_min + price_max) / 2
        spread = (price_max - price_min) / 2
        price_fit = 1.0 - 0.2 * abs(price - mid) / spread

    ppsf = li.get("ppsf_usd") or 0
    if ppsf and ppsf_baseline:
        # Size-normalized: ratio < 1 = under-baseline (good); > 1.2 = penalty.
        ratio = ppsf / ppsf_baseline
        ppsf_vs = max(0.0, 1.2 - ratio) if ratio <= 1.2 else 0.0
    else:
        ppsf_vs = 0.5

    dom = li.get("days_on_market") or 0
    dom_leverage = min(1.0, dom / 90.0)

    yb = li.get("year_built") or 0
    if yb >= 2010:
        vintage = 1.0
    elif yb >= 1990:
        vintage = 0.75
    elif yb >= 1970:
        vintage = 0.55
    elif yb >= 1950:
        vintage = 0.4
    elif yb > 0:
        vintage = 0.25
    else:
        vintage = 0.4

    lot = li.get("lot_size_sqft") or 0
    if lot >= 14000:
        lot_size = 1.0
    elif lot >= 10000:
        lot_size = 0.85
    elif lot >= 8000:
        lot_size = 0.65
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
        + WEIGHTS["ppsf_vs_peers"] * ppsf_vs
        + WEIGHTS["dom_leverage"] * dom_leverage
        + WEIGHTS["vintage"] * vintage
        + WEIGHTS["lot_size"] * lot_size
    )
    busy = busy_street_assessment(li)
    # Soft penalty for busy-street exposure (address OR proximity to arterial).
    # Not a hard cut so a great listing in every other dimension can still rank.
    if busy["busy_street"]:
        raw -= 0.05  # 5-point hit
    return {
        "score": round(max(0.0, raw) * 100, 1),
        "busy_street": busy["busy_street"],
        "busy_address_on": busy["busy_address_on"],
        "busy_proximity": busy["busy_proximity"],
        "nearest_arterial": busy["nearest_arterial"],
        "nearest_arterial_m": busy["nearest_arterial_m"],
        "ppsf_baseline": ppsf_baseline,
        "ppsf_baseline_source": ppsf_baseline_source,
        "components": {
            "lakewood_orbit": round(sub_orbit, 2),
            "schools": round(school_score, 2),
            "price_fit": round(price_fit, 2),
            "ppsf_vs_peers": round(ppsf_vs, 2),
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

    areas = load_sub_areas(include_watch=True)  # noqa: F841 (validates config)

    sqft_min = int(buy_box.get("sqft_min") or 0)
    listings = load_active_listings(sqft_min=sqft_min)
    sold_pool = load_sold_comps()
    LOG.info("Scoring %d listings (sqft_min=%d, %d sold comps for peer baselines)",
             len(listings), sqft_min, len(sold_pool))
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
    busy_count = 0
    for li in listings:
        sa = li.get("sub_area_id")
        if not sa or sa not in area_lookup:
            continue
        baseline, source = peer_ppsf_median(li, sold_pool, area_medians.get(sa))
        result = score_listing(li, area_lookup[sa], baseline, source, buy_box)
        if result["busy_street"]:
            busy_count += 1
        scored.append({
            **li,
            "_score": result["score"],
            "_components": result["components"],
            "_busy_street": result["busy_street"],
            "_busy_address_on": result["busy_address_on"],
            "_busy_proximity": result["busy_proximity"],
            "_nearest_arterial": result["nearest_arterial"],
            "_nearest_arterial_m": result["nearest_arterial_m"],
            "_ppsf_baseline": result["ppsf_baseline"],
            "_ppsf_baseline_source": result["ppsf_baseline_source"],
        })

    LOG.info("Flagged %d listings on busy streets", busy_count)
    scored.sort(key=lambda r: r["_score"], reverse=True)
    snapshot = {
        "as_of": utc_now_iso(),
        "n": len(scored),
        "weights": WEIGHTS,
        "buy_box": buy_box,
        "area_ppsf_medians": area_medians,
        "n_busy_street": busy_count,
        "listings": scored,
    }
    out = write_snapshot("stats", "watchlist", snapshot)
    LOG.info("Wrote %s with %d scored listings", out, len(scored))
    return 0


if __name__ == "__main__":
    sys.exit(main())
