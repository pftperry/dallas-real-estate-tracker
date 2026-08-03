"""Watchlist scoring engine.

Two stages, in this order:

1. HARD ELIGIBILITY GATE (2026-08-02). A listing must clear every one of:
     - price inside the buy box
     - beds >= beds_min, baths >= baths_min
     - the location gate: zoned to an allowlisted elementary (Mockingbird or
       Lakewood) OR inside an allowlisted focus zone (the drawn Lake Highlands
       outline)
   Failures never reach the watchlist. They are retained in the snapshot's
   `excluded` array with reasons, so "why isn't this house on my list?" is
   always answerable.

   Zoning is resolved from the listing's own lat/lng against the official DISD
   attendance polygons, NOT from the `feeder_pattern` strings in the config.
   Those strings were wrong for several sub-areas: "Forest Hills" was labeled a
   Lakewood Elementary feeder but is entirely Hexter.

2. SCORING, on survivors only, 0-100. Ranks the *house*, not the location,
   because the gate has already settled location:
     - $/sqft vs. peer comps, 30% (size-normalized: same sub-area, +/-25% sqft)
     - lot size, 20%
     - days on market, 15% (longer = more leverage)
     - condition / vintage signal, 15% (turnkey via year built)
     - school confidence, 10% (verified DISD zoning vs. geography-only)
     - price position within the band, 10%

   Geographic affinity (lakewood_orbit) was removed from the score in 2026-08;
   see the WEIGHTS comment for why. It is still reported per listing as context.

Plus two off-score flags surfaced separately: busy-street exposure, and
near_zone_edge for listings close enough to an attendance boundary that the
rooftop coordinate cannot settle which side they are on.

Outputs data/stats/latest_watchlist.json with a ranked list.

Weights: $/sqft vs peers 30%, lot 20%, DOM 15%, vintage 15%, schools 10%,
price fit 10%. Supersedes the 2026-05 set, which put 30% on Lakewood-orbit.
"""

from __future__ import annotations

import json
import logging
import math
import re
import statistics
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from scrapers.school_zones import TARGET_ELEMENTARIES
from scrapers.school_zones import load_zones as load_school_zones
from scrapers.school_zones import lookup as lookup_school_zone
from scrapers.school_zones import qualifying_zones
from scrapers.utils import (
    DATA_ROOT,
    Polygon,
    load_sub_areas,
    utc_now_iso,
    write_snapshot,
)

LOG = logging.getLogger("score")

# Rebalanced 2026-08-03, when the hard gate made the old weights incoherent.
#
# `lakewood_orbit` used to carry 30% and, measured against the eligible set, was
# supplying 36% of all the score's discriminating power -- more than double any
# other component. That was correct when the screen spanned 20 areas and location
# was the main open question. It is wrong now: the gate already decides location,
# and the three accepted bases (Mockingbird zoning, Lakewood zoning, the drawn
# Lake Highlands zone) are an OR, so re-penalising one of them in the ranking
# charges the same preference twice. It buried the drawn zone in the bottom four
# ranks by construction, and it docked Junius Heights 13.5 points for "feeder
# uncertainty" that the per-address gate now resolves outright.
#
# So location leaves the score entirely. What remains ranks the *house*, on the
# premise that anything being ranked has already cleared the location test. The
# one location signal kept is `schools`, which distinguishes verified DISD zoning
# from geography-only qualification -- a real difference in confidence, worth a
# point rather than eighteen.
#
# `price_fit` drops to 10% because the gate enforces the band, leaving it nearly
# constant (a 3.8-point spread across the eligible set). `ppsf_vs_peers` rises to
# 30% and its formula is widened below: it is the actual value signal and was
# contributing 3.5 points.
WEIGHTS = {
    "ppsf_vs_peers": 0.30,
    "lot_size": 0.20,
    "dom_leverage": 0.15,
    "vintage": 0.15,
    "schools": 0.10,
    "price_fit": 0.10,
}

# Peer-comp window for size-normalized $/sqft comparison.
PEER_SQFT_WINDOW = 0.25  # +/- 25%
PEER_MIN_COUNT = 3       # need at least 3 peers; otherwise fall back to area median

# $/sqft scoring band, as a ratio to the peer baseline. Symmetric +/-25%: at 0.75
# (a quarter under peers) full credit, at 1.00 (on baseline) neutral 0.5, at 1.25
# no credit. The old rule was max(0, 1.2 - ratio), which produced a 0.00-0.35
# output range on real data -- a 10%-weighted component that could only ever move
# 3.5 points, and which collapsed to zero for everything above 1.2x, discarding
# the distinction between "slightly over peers" and "wildly over".
PPSF_RATIO_BEST = 0.75
PPSF_RATIO_WORST = 1.25

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
# Most of these are still eyeballed from cross-street intersections; the 100m
# threshold is generous so meter-level inaccuracy does not bite.
#
# 2026-08-02: Audelia, Plano Rd, Walnut Hill and the east end of Northwest Hwy
# were replaced with OpenStreetMap centerlines. The old guesses put Plano Rd
# ~1.1km east of the real road and Audelia ~400m west, which mattered once the
# drawn Lake Highlands zone made those two roads its boundaries: the phantom
# Audelia line ran through the middle of the L Streets, flagging quiet interior
# homes, while real Plano Rd frontage was never flagged at all.
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
    # East end (lng -96.735 eastward) from OSM; west of that still eyeballed.
    "Northwest Hwy": [
        (32.853, -96.785), (32.855, -96.770), (32.857, -96.755),
        (32.8590, -96.7330), (32.8630, -96.7150), (32.8643, -96.7050),
        (32.8642, -96.6950),
    ],
    # OSM: essentially straight north-south at lng -96.7004.
    "Plano Rd": [
        (32.8642, -96.7004), (32.8800, -96.7004), (32.9000, -96.7004),
        (32.9166, -96.7005),
    ],
    # OSM: flat at lat ~32.8789 across this whole band.
    "Walnut Hill Ln": [
        (32.879, -96.785), (32.879, -96.770), (32.8788, -96.7350),
        (32.8789, -96.7200), (32.8790, -96.7050), (32.8789, -96.6943),
    ],
    "Forest Ln": [
        (32.910, -96.785), (32.911, -96.770), (32.912, -96.755),
        (32.913, -96.738), (32.914, -96.720),
    ],
    "Royal Ln": [
        (32.895, -96.785), (32.896, -96.770), (32.897, -96.755),
        (32.898, -96.738), (32.899, -96.720),
    ],
    # OSM: essentially straight north-south at lng -96.7179.
    "Audelia Rd": [
        (32.8617, -96.7179), (32.8800, -96.7179), (32.9000, -96.7174),
        (32.9256, -96.7178),
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

# Redfin lat/lng is rooftop-grade but not surveyed. Within this distance of an
# attendance boundary, the coordinate cannot settle which side a house is on,
# so the zoning call needs a manual check on DISD SchoolFinder before touring.
ZONE_EDGE_NEAR_M = 40.0


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


def load_focus_zones(cfg: dict) -> dict[str, Polygon]:
    """Build {zone_id: Polygon} for every zone on the eligibility allowlist.

    Raises if an allowlisted id is missing or has no traced polygon. A silent
    empty result here would quietly drop the geographic half of the gate and
    make every Lake Highlands listing fail, so this fails loud instead.
    """
    allow = list(cfg["buy_box"]["eligibility"].get("focus_zone_allowlist") or [])
    by_id = {e["id"]: e for e in cfg["sub_areas"] + cfg.get("watch_areas", [])}
    zones: dict[str, Polygon] = {}
    problems: list[str] = []
    for zone_id in allow:
        entry = by_id.get(zone_id)
        if entry is None:
            problems.append(f"{zone_id!r} is not a configured area")
        elif not entry.get("polygon"):
            problems.append(f"{zone_id!r} has no polygon (a bbox is not enough for a focus zone)")
        else:
            zones[zone_id] = Polygon.from_ring(entry["polygon"])
    if problems:
        raise ValueError("Bad focus_zone_allowlist: " + "; ".join(problems))
    return zones


def _min_dist_to_polygon_edge_m(lat: float, lng: float, polygon: Polygon) -> float:
    """Shortest distance from a point to any ring segment of a polygon."""
    best = float("inf")
    for exterior, holes in polygon.parts:
        for ring in [exterior, *holes]:
            n = len(ring)
            for i in range(n):
                a_lng, a_lat = ring[i][0], ring[i][1]
                b_lng, b_lat = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
                d = _point_to_segment_m(lat, lng, a_lat, a_lng, b_lat, b_lng)
                if d < best:
                    best = d
    return best


def nearest_gate_boundary(lat: float | None, lng: float | None,
                          focus_zones: dict[str, Polygon]) -> tuple[float, str | None]:
    """Return (metres, label) for the nearest eligibility boundary.

    Small distances mean the in/out call is coordinate-noise sensitive, whether
    the listing landed inside (verify before trusting it) or outside (a near miss
    worth a manual look). The label says *which* qualifying area is nearest,
    which is the useful thing for a near miss: "65m from Mockingbird" is
    actionable in a way that a bare distance is not.

    Note this deliberately does NOT report what a failing listing is actually
    zoned to. Only the two allowlisted polygons are cached, so that is unknown
    here, and guessing it would be inventing data.

    Slightly conservative by design: Mockingbird and Lakewood are adjacent along
    part of their border, so a house near that shared line gets flagged even
    though both sides qualify and its eligibility is not actually in doubt.
    Distinguishing that would need the neighbouring zone's polygon. Over-flagging
    costs one lookup; under-flagging would put an unverified claim on the list.
    """
    if lat is None or lng is None:
        return float("inf"), None
    best, label = float("inf"), None
    # Only allowlisted zones, not all 135. Distance to the Hexter boundary says
    # nothing about eligibility.
    for zone in qualifying_zones():
        d = _min_dist_to_polygon_edge_m(lat, lng, zone.polygon)
        if d < best:
            best, label = d, zone.short
    for zone_id, polygon in focus_zones.items():
        d = _min_dist_to_polygon_edge_m(lat, lng, polygon)
        if d < best:
            best, label = d, zone_id
    return best, label


def location_gate(li: dict, focus_zones: dict[str, Polygon]) -> dict:
    """Resolve the location half of the gate for one listing.

    Passes on either basis: allowlisted elementary zoning, or containment in an
    allowlisted focus zone. Zoning wins when both apply, since it is the
    stronger claim.

    The resolved zone is recorded whether or not it qualifies, so a rejected
    listing can report what it is actually zoned to rather than a bare "failed".
    `elementary is None` means outside Dallas ISD altogether.
    """
    lat, lng = li.get("lat"), li.get("lng")
    result = {
        "pass": False,
        "basis": None,
        "elementary": None,
        "elementary_short": None,
        "middle": None,
        "high": None,
        "feeder": None,
        "focus_zone": None,
    }
    if lat is None or lng is None:
        result["basis"] = "no_coordinates"
        return result

    zone = lookup_school_zone(lat, lng)
    if zone is not None:
        # Recorded for reporting even when it fails the allowlist.
        result.update(
            {
                "elementary": zone.elementary,
                "elementary_short": zone.short,
                "middle": zone.middle,
                "high": zone.high,
                "feeder": zone.feeder,
            }
        )
        if zone.qualifies:
            result.update({"pass": True, "basis": "elementary_zone"})
            return result

    for zone_id, polygon in focus_zones.items():
        if polygon.contains(lat, lng):
            result.update({"pass": True, "basis": "focus_zone", "focus_zone": zone_id})
            return result

    result["basis"] = "outside_disd" if zone is None else "wrong_elementary"
    return result


def hard_filter(li: dict, buy_box: dict, loc: dict) -> list[str]:
    """Return the list of reasons this listing is ineligible. Empty == eligible.

    Missing beds/baths/price counts as a failure rather than a pass: an
    unverifiable listing should surface in `excluded` for a manual look, not
    slip onto the watchlist unchecked.
    """
    fails: list[str] = []

    price = li.get("price_usd")
    lo, hi = buy_box["price_min_usd"], buy_box["price_max_usd"]
    if not price:
        fails.append("price_missing")
    elif price < lo:
        fails.append(f"price_below_min (${price:,} < ${lo:,})")
    elif price > hi:
        fails.append(f"price_above_max (${price:,} > ${hi:,})")

    for field, minimum, label in (
        ("beds", buy_box.get("beds_min"), "beds"),
        ("baths", buy_box.get("baths_min"), "baths"),
    ):
        if minimum is None:
            continue
        value = li.get(field)
        if value is None:
            fails.append(f"{label}_missing")
        elif value < minimum:
            fails.append(f"{label}_below_min ({value:g} < {minimum:g})")

    sqft_min = buy_box.get("sqft_min")
    if sqft_min:
        sqft = li.get("sqft")
        if not sqft:
            fails.append("sqft_missing")
        elif sqft < sqft_min:
            fails.append(f"sqft_below_min ({sqft:,} < {sqft_min:,})")

    if not loc["pass"]:
        if loc["basis"] == "no_coordinates":
            fails.append("location_unverifiable (no coordinates)")
        elif loc["basis"] == "wrong_elementary":
            # Now that the whole district is cached, say which zone it is.
            fails.append(f"wrong_elementary (zoned {loc['elementary_short']}, "
                         "not Mockingbird/Lakewood, and not in a focus zone)")
        else:
            fails.append("outside_disd (Richardson ISD or another district, "
                         "and not in a focus zone)")
    return fails


def load_active_listings(sqft_min: int = 0) -> tuple[list[dict], str | None]:
    """Return (listings, when_they_were_scraped).

    The scrape timestamp is carried through deliberately. Scoring can be re-run
    at any time against an old snapshot, so stamping the watchlist only with
    "now" would present stale inventory as current on the dashboard.
    """
    path = DATA_ROOT / "listings" / "latest_redfin.json"
    if not path.exists():
        LOG.warning("No active listings snapshot at %s", path)
        return [], None
    payload = json.loads(path.read_text())
    listings = payload.get("listings", [])
    if sqft_min:
        before = len(listings)
        listings = [li for li in listings if (li.get("sqft") or 0) >= sqft_min]
        LOG.info("Filtered <%d sqft: %d -> %d listings", sqft_min, before, len(listings))
    return listings, payload.get("as_of")


def _stale_days(scraped_at: str | None) -> int | None:
    """Age of the listings snapshot in whole days, or None if unknown."""
    if not scraped_at:
        return None
    try:
        when = datetime.strptime(scraped_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return max(0, (datetime.now(timezone.utc) - when).days)


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
    loc: dict,
) -> dict:
    sub_orbit = float(area_meta.get("lakewood_orbit", 0.0))

    # School credit comes from the *resolved* zone, not the sub-area's
    # school_quality_score. Those config numbers were derived from feeder_pattern
    # strings that turned out to be wrong in several areas. Everything scored
    # here has already passed the gate, so this only separates the two bases:
    # confirmed Mockingbird/Lakewood zoning outranks "inside the drawn zone",
    # where RISD zoning is real but unverified against official boundaries.
    if loc.get("basis") == "elementary_zone":
        school_score = 1.0
    elif loc.get("basis") == "focus_zone":
        school_score = 0.9
    else:
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
        # Size-normalized, linear across the band, clamped at both ends so a
        # listing far above peers still scores 0 rather than going negative.
        ratio = ppsf / ppsf_baseline
        span = PPSF_RATIO_WORST - PPSF_RATIO_BEST
        ppsf_vs = min(1.0, max(0.0, (PPSF_RATIO_WORST - ratio) / span))
    else:
        # No baseline (thin peer set, missing $/sqft): neutral, same as on-baseline.
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

    # Note lakewood_orbit is deliberately absent: see the WEIGHTS comment. It is
    # still reported in components below as neighborhood context, but it no longer
    # moves the score.
    raw = (
        WEIGHTS["ppsf_vs_peers"] * ppsf_vs
        + WEIGHTS["lot_size"] * lot_size
        + WEIGHTS["dom_leverage"] * dom_leverage
        + WEIGHTS["vintage"] * vintage
        + WEIGHTS["schools"] * school_score
        + WEIGHTS["price_fit"] * price_fit
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


def _fallback_area_meta(loc: dict) -> dict:
    """Stand-in metadata for a listing that passed the gate but sits outside
    every configured sub-area bbox.

    This happens when a sub-area is removed from the config while an older
    snapshot still carries its tag, or when Redfin returns a listing just
    outside the scraped rectangle. The gate is authoritative and runs off
    lat/lng, so such a listing must not be dropped just because its label is
    unknown. Orbit is inferred from how it qualified.
    """
    return {
        "name": "(unmapped)",
        "lakewood_orbit": 0.9 if loc.get("basis") == "elementary_zone" else 0.4,
        "school_quality_score": 0,
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    cfg_path = Path(__file__).parent.parent / "config" / "sub_areas.json"
    cfg = json.loads(cfg_path.read_text())
    buy_box = cfg["buy_box"]
    area_lookup = {a["id"]: a for a in cfg["sub_areas"]}
    area_lookup.update({a["id"]: a for a in cfg.get("watch_areas", [])})

    load_sub_areas(include_watch=True)  # validates config geometry
    focus_zones = load_focus_zones(cfg)
    all_zones = load_school_zones()
    gate_zones = qualifying_zones()

    # The allowlist lives in two places -- the config documents it, score.py acts
    # on scrapers.school_zones.TARGET_ELEMENTARIES. Drift between them would mean
    # the dashboard advertises one rule while the gate applies another, so refuse
    # to run rather than mislead.
    configured = set(buy_box["eligibility"].get("elementary_allowlist") or [])
    if configured != set(TARGET_ELEMENTARIES):
        raise ValueError(
            "elementary_allowlist in config/sub_areas.json does not match "
            "TARGET_ELEMENTARIES in scrapers/school_zones.py.\n"
            f"  config only:  {sorted(configured - set(TARGET_ELEMENTARIES))}\n"
            f"  module only:  {sorted(set(TARGET_ELEMENTARIES) - configured)}\n"
            "Update both, then re-run scrapers.school_zones --refresh."
        )
    if not gate_zones:
        raise ValueError(
            f"None of {sorted(TARGET_ELEMENTARIES)} are present in the "
            f"{len(all_zones)}-zone cache. Run scrapers.school_zones --refresh."
        )

    LOG.info(
        "Gate: $%(lo)s-$%(hi)s, >=%(bd)s bd / >=%(ba)s ba, zoned [%(z)s] or inside [%(f)s]",
        {
            "lo": f"{buy_box['price_min_usd']:,}",
            "hi": f"{buy_box['price_max_usd']:,}",
            "bd": buy_box.get("beds_min"),
            "ba": buy_box.get("baths_min"),
            "z": ", ".join(z.short for z in gate_zones),
            "f": ", ".join(focus_zones),
        },
    )
    LOG.info("Zoning resolved against %d cached DISD elementary zones", len(all_zones))

    sqft_min = int(buy_box.get("sqft_min") or 0)
    listings, listings_as_of = load_active_listings(sqft_min=sqft_min)
    stale_days = _stale_days(listings_as_of)
    sold_pool = load_sold_comps()
    LOG.info("Read %d active listings scraped %s (%d sold comps for peer baselines)",
             len(listings), listings_as_of or "at an unknown time", len(sold_pool))
    if stale_days is not None and stale_days >= 7:
        LOG.warning("Listings snapshot is %d days old. Run scrapers.redfin --status active "
                    "for current inventory; the watchlist below describes that older market.",
                    stale_days)
    if not listings:
        write_snapshot("stats", "watchlist", {
            "as_of": utc_now_iso(),
            "listings_as_of": listings_as_of,
            "n": 0,
            "listings": [],
            "note": "No active listings snapshot available. Run scrapers.redfin first.",
        })
        return 0

    # Peer baselines are drawn from the full pool, before the gate: a $1.3M
    # neighbor is still a valid $/sqft comp even though it can never be a buy.
    area_medians = compute_area_medians(listings)

    scored: list[dict] = []
    excluded: list[dict] = []
    reason_counts: Counter[str] = Counter()
    busy_count = 0
    near_edge_count = 0
    unmapped_count = 0

    for li in listings:
        loc = location_gate(li, focus_zones)
        fails = hard_filter(li, buy_box, loc)
        edge_m, edge_zone = nearest_gate_boundary(li.get("lat"), li.get("lng"), focus_zones)
        near_edge = edge_m <= ZONE_EDGE_NEAR_M

        if fails:
            # Bucket by reason kind, not the value-laden message, so the
            # histogram stays readable.
            for reason in fails:
                reason_counts[reason.split(" (")[0]] += 1
            excluded.append({
                "address": li.get("address"),
                "url": li.get("url"),
                "sub_area_id": li.get("sub_area_id"),
                "price_usd": li.get("price_usd"),
                "beds": li.get("beds"),
                "baths": li.get("baths"),
                "sqft": li.get("sqft"),
                # What it IS zoned to (None = outside Dallas ISD), versus which
                # qualifying area is nearest. Two different questions, both useful
                # on the near-miss list.
                "elementary": loc["elementary"],
                "elementary_short": loc["elementary_short"],
                "feeder": loc["feeder"],
                "_nearest_gate_zone": edge_zone,
                "_exclusion_reasons": fails,
                "_near_zone_edge": near_edge,
                "_zone_edge_m": round(edge_m) if edge_m != float("inf") else None,
            })
            continue

        sa = li.get("sub_area_id")
        area_meta = area_lookup.get(sa)
        if area_meta is None:
            area_meta = _fallback_area_meta(loc)
            unmapped_count += 1
        baseline, source = peer_ppsf_median(li, sold_pool, area_medians.get(sa))
        result = score_listing(li, area_meta, baseline, source, buy_box, loc)
        if result["busy_street"]:
            busy_count += 1
        if near_edge:
            near_edge_count += 1
        scored.append({
            **li,
            "_score": result["score"],
            "_components": result["components"],
            "_eligible_basis": loc["basis"],
            "_elementary": loc["elementary"],
            "_elementary_short": loc["elementary_short"],
            "_middle": loc["middle"],
            "_high": loc["high"],
            "_feeder": loc["feeder"],
            "_focus_zone": loc["focus_zone"],
            "_near_zone_edge": near_edge,
            "_zone_edge_m": round(edge_m) if edge_m != float("inf") else None,
            "_nearest_gate_zone": edge_zone,
            "_unmapped_sub_area": area_meta.get("name") == "(unmapped)",
            "_busy_street": result["busy_street"],
            "_busy_address_on": result["busy_address_on"],
            "_busy_proximity": result["busy_proximity"],
            "_nearest_arterial": result["nearest_arterial"],
            "_nearest_arterial_m": result["nearest_arterial_m"],
            "_ppsf_baseline": result["ppsf_baseline"],
            "_ppsf_baseline_source": result["ppsf_baseline_source"],
        })

    basis_counts = Counter(r["_eligible_basis"] for r in scored)
    LOG.info("Gate: %d of %d eligible (%s)", len(scored), len(listings),
             ", ".join(f"{k}={v}" for k, v in basis_counts.most_common()) or "none")
    for reason, n in reason_counts.most_common():
        LOG.info("  excluded %3d  %s", n, reason)
    if near_edge_count:
        LOG.info("%d eligible listings sit within %.0fm of a zone edge -- confirm on "
                 "DISD SchoolFinder before touring", near_edge_count, ZONE_EDGE_NEAR_M)
    if unmapped_count:
        LOG.warning("%d eligible listings fell outside every configured sub-area bbox "
                    "and were scored with fallback metadata", unmapped_count)
    LOG.info("Flagged %d eligible listings on busy streets", busy_count)

    scored.sort(key=lambda r: r["_score"], reverse=True)
    excluded.sort(key=lambda r: (r.get("price_usd") or 0))
    snapshot = {
        "as_of": utc_now_iso(),
        "listings_as_of": listings_as_of,
        "listings_age_days": stale_days,
        "n": len(scored),
        "n_screened": len(listings),
        "n_excluded": len(excluded),
        "weights": WEIGHTS,
        "buy_box": buy_box,
        "eligible_by_basis": dict(basis_counts),
        "exclusion_reason_counts": dict(reason_counts.most_common()),
        "zoning_source": buy_box["eligibility"]["zoning_source"],
        "area_ppsf_medians": area_medians,
        "n_busy_street": busy_count,
        "n_near_zone_edge": near_edge_count,
        "listings": scored,
        "excluded": excluded,
    }
    out = write_snapshot("stats", "watchlist", snapshot)
    LOG.info("Wrote %s: %d eligible, %d excluded", out, len(scored), len(excluded))
    return 0


if __name__ == "__main__":
    sys.exit(main())
