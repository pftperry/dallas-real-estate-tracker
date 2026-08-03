"""Per-address elementary attendance-zone lookup (Dallas ISD).

Why this exists: the `feeder_pattern` strings in `config/sub_areas.json` are
neighborhood-level shorthand and they are *not reliable*. DISD attendance
boundaries do not follow subdivision lines. Checked against the official
2026-27 boundaries, "Forest Hills" -- labeled a Lakewood Elementary feeder in
the config -- is actually zoned to Hexter. Several other sub-areas straddle two
zones. Any school gate applied at the sub-area level is therefore wrong in both
directions.

So the gate resolves zoning per listing, from the listing's own lat/lng, against
the official DISD polygons.

Source: Dallas ISD Data Hub, "Elementary Attendance Boundaries" feature service
(public, no auth). Each polygon carries the full feeder pattern: ELEM_DESC,
MIDDLE, HIGH.

  https://data-disd-gismaps.hub.arcgis.com/items/1098b9de81234d4d88e3750c97353a58

All 135 district elementary polygons are cached in `config/school_zones.geojson`
and committed, so scoring is a local point-in-polygon test -- no network call per
listing, works offline and in CI, and the committed file is an audit trail of
which boundary vintage a given watchlist was scored against.

Caching the whole district rather than only the two qualifying zones is what lets
a *rejected* listing be reported honestly. With a two-zone cache, "not in either
polygon" was indistinguishable between a Hexter address and a Richardson ISD
address, so the near-miss list could not say what a near miss was actually zoned
to without inventing it. Now it can: `lookup()` resolves any address in the
district, and `Zone.qualifies` is the separate question of whether that zone is on
the buy-box allowlist.

DISD redraws boundaries annually (typically late spring, for the next school
year). Re-pull after that lands:

  python -m scrapers.school_zones --refresh

The cache is normalized on write -- features sorted by SLN, coordinates rounded to
6 decimal places (~11cm, far finer than the rooftop accuracy of any listing
coordinate), no pretty-printing. That keeps the committed file byte-stable across
pulls, so the weekly refresh produces a diff only when a boundary genuinely moved
instead of a ~1MB churn from float jitter or feature reordering.

Spot-check a coordinate:

  python -m scrapers.school_zones --check 32.8285 -96.7770
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .utils import DEFAULT_HEADERS, BBox, Polygon

LOG = logging.getLogger("school_zones")

ZONES_PATH = Path(__file__).parent.parent / "config" / "school_zones.geojson"

DISD_BOUNDARY_QUERY = (
    "https://services.arcgis.com/RfrtTbYxQ8YIhjWT/arcgis/rest/services/"
    "Elementary_Attendance_Boundaries/FeatureServer/0/query"
)

# The only elementary zones that clear the buy-box school gate. Everything else
# in the district is cached too, but only to *report* zoning, never to pass it.
# Keep in sync with buy_box.eligibility.elementary_allowlist in
# config/sub_areas.json; score.py cross-checks the two at startup.
TARGET_ELEMENTARIES = (
    "Mockingbird Elementary School",
    "Lakewood Elementary School",
)

# Coordinate precision for the cached file. 6dp is ~11cm, well below the error
# in any listing coordinate, and rounding keeps repeat pulls byte-identical.
COORD_PRECISION = 6


@dataclass
class Zone:
    """One elementary attendance polygon plus its feeder pattern."""

    elementary: str
    middle: str
    high: str
    polygon: Polygon

    @property
    def short(self) -> str:
        """Display label: "Hexter Elementary School" -> "Hexter"."""
        return self.elementary.removesuffix(" Elementary School").strip() or self.elementary

    @property
    def qualifies(self) -> bool:
        """Whether this zone is on the buy-box allowlist."""
        return self.elementary in TARGET_ELEMENTARIES

    @property
    def feeder(self) -> str:
        """Full feeder pattern, e.g. "Lakewood / Long MS / Wilson HS"."""
        return f"{self.short} / {self.middle} MS / {self.high} HS"


def _feature_to_zone(feature: dict) -> Zone:
    props = feature.get("properties") or {}
    geom = feature.get("geometry") or {}
    gtype = geom.get("type")
    coords = geom.get("coordinates") or []

    if gtype == "Polygon":
        polygons = [coords]
    elif gtype == "MultiPolygon":
        polygons = coords
    else:
        raise ValueError(f"Unsupported geometry type for school zone: {gtype!r}")

    # Attendance zones are not always simply connected, so keep hole rings.
    parts = [(poly[0], list(poly[1:])) for poly in polygons if poly]
    lats = [pt[1] for exterior, _ in parts for pt in exterior]
    lngs = [pt[0] for exterior, _ in parts for pt in exterior]
    return Zone(
        elementary=props.get("ELEM_DESC") or "",
        middle=props.get("MIDDLE") or "",
        high=props.get("HIGH") or "",
        polygon=Polygon(
            parts=parts,
            bbox=BBox(min(lats), min(lngs), max(lats), max(lngs)),
        ),
    )


_ZONE_CACHE: list[Zone] | None = None


def load_zones(force: bool = False) -> list[Zone]:
    """Load and memoize the cached zone polygons."""
    global _ZONE_CACHE
    if _ZONE_CACHE is not None and not force:
        return _ZONE_CACHE
    if not ZONES_PATH.exists():
        raise FileNotFoundError(
            f"Missing {ZONES_PATH}. Run: python -m scrapers.school_zones --refresh"
        )
    payload = json.loads(ZONES_PATH.read_text())
    _ZONE_CACHE = [_feature_to_zone(f) for f in payload.get("features", [])]
    LOG.debug("Loaded %d school zones", len(_ZONE_CACHE))
    return _ZONE_CACHE


def qualifying_zones() -> list[Zone]:
    """The allowlisted zones only. Used for the gate and for boundary distances."""
    return [z for z in load_zones() if z.qualifies]


def lookup(lat: float | None, lng: float | None) -> Zone | None:
    """Return the DISD elementary Zone containing this point, or None.

    None now means genuinely outside Dallas ISD -- Richardson ISD, Highland Park,
    or beyond the district edge. A Hexter address returns the Hexter Zone with
    `qualifies == False`, which is the distinction the old two-zone cache could
    not make. Callers gating on eligibility must check `.qualifies`, not just
    truthiness.
    """
    if lat is None or lng is None:
        return None
    for zone in load_zones():
        if zone.polygon.contains(lat, lng):
            return zone
    return None


def _round_coords(node):
    """Recursively round a nested coordinate structure to COORD_PRECISION."""
    if node and isinstance(node[0], (int, float)):
        return [round(node[0], COORD_PRECISION), round(node[1], COORD_PRECISION)]
    return [_round_coords(child) for child in node]


def refresh() -> Path:
    """Re-download every DISD elementary attendance polygon."""
    params = {
        "where": "1=1",
        "outFields": "SLN,ELEM_DESC,MIDDLE,HIGH",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "geojson",
    }
    url = f"{DISD_BOUNDARY_QUERY}?{urlencode(params)}"
    LOG.info("GET %s", url)
    req = Request(url, headers={**DEFAULT_HEADERS, "Accept": "application/json"})
    with urlopen(req, timeout=120) as resp:
        body = resp.read().decode("utf-8", errors="replace")

    payload = json.loads(body)
    features = payload.get("features") or []
    found = {(f.get("properties") or {}).get("ELEM_DESC") or "" for f in features}

    # The allowlist is the gate. If a name on it is absent -- renamed school,
    # partial response, service change -- overwriting would silently make every
    # listing fail the school gate and the watchlist would just look "empty
    # today". Refuse instead, leaving the last good cache in place.
    missing = sorted(set(TARGET_ELEMENTARIES) - found)
    if missing:
        raise RuntimeError(
            f"DISD service returned {len(features)} zones but is missing {missing}. "
            "School names may have changed -- check the service and update "
            "TARGET_ELEMENTARIES before overwriting the cache."
        )
    if payload.get("exceededTransferLimit"):
        raise RuntimeError(
            "DISD service truncated the response (exceededTransferLimit). Page the "
            "query with resultOffset before overwriting the cache; a partial "
            "district would silently misreport zoning outside the returned set."
        )

    # Normalize so the committed file only changes when a boundary actually
    # moves. See the module docstring.
    for feature in features:
        geom = feature.get("geometry") or {}
        if geom.get("coordinates"):
            geom["coordinates"] = _round_coords(geom["coordinates"])
    features.sort(key=lambda f: (f.get("properties") or {}).get("SLN") or 0)
    payload["features"] = features

    ZONES_PATH.write_text(json.dumps(payload, separators=(",", ":"), sort_keys=True))
    size_mb = ZONES_PATH.stat().st_size / 1_048_576
    LOG.info("Wrote %s: %d zones, %.2f MB (%d qualifying: %s)",
             ZONES_PATH, len(features), size_mb, len(TARGET_ELEMENTARIES),
             ", ".join(sorted(TARGET_ELEMENTARIES)))
    return ZONES_PATH


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--refresh", action="store_true",
                        help="Re-download boundaries from the DISD feature service")
    parser.add_argument("--check", nargs=2, type=float, metavar=("LAT", "LNG"),
                        help="Resolve one coordinate and print the feeder pattern")
    args = parser.parse_args()

    if args.refresh:
        refresh()
        load_zones(force=True)

    if args.check:
        lat, lng = args.check
        zone = lookup(lat, lng)
        if zone is None:
            print(f"{lat},{lng} -> outside Dallas ISD entirely (RISD or another district)"
                  f"  [fails school gate]")
        elif zone.qualifies:
            print(f"{lat},{lng} -> {zone.feeder}  [QUALIFIES]")
        else:
            print(f"{lat},{lng} -> {zone.feeder}  [fails school gate: not on the allowlist]")
        return 0

    if not args.refresh:
        zones = load_zones()
        qualifying = [z for z in zones if z.qualifies]
        print(f"{len(zones)} DISD elementary zones cached, {len(qualifying)} qualifying:\n")
        for zone in qualifying:
            bb = zone.polygon.bbox
            print(f"  {zone.feeder}"
                  f"  (lat {bb.sw_lat:.4f}..{bb.ne_lat:.4f}, "
                  f"lng {bb.sw_lng:.4f}..{bb.ne_lng:.4f})")
        missing = sorted(set(TARGET_ELEMENTARIES) - {z.elementary for z in zones})
        if missing:
            print(f"\nWARNING: allowlisted but not in the cache: {missing}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
