"""Shared scraper utilities: polygon filtering, rate limiting, JSON snapshot writing."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

CONFIG_PATH = Path(__file__).parent.parent / "config" / "sub_areas.json"
DATA_ROOT = Path(__file__).parent.parent / "data"


@dataclass
class BBox:
    sw_lat: float
    sw_lng: float
    ne_lat: float
    ne_lng: float

    def contains(self, lat: float, lng: float) -> bool:
        return (
            self.sw_lat <= lat <= self.ne_lat
            and self.sw_lng <= lng <= self.ne_lng
        )


def point_in_ring(lat: float, lng: float, ring: list) -> bool:
    """Crossing-number (ray-casting) point-in-polygon test.

    `ring` is a list of [lng, lat] pairs. The ring may be open or closed;
    the wrap-around edge is always tested.
    """
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        lng_i, lat_i = ring[i][0], ring[i][1]
        lng_j, lat_j = ring[j][0], ring[j][1]
        # Does a horizontal ray at `lat` cross this edge?
        if (lat_i > lat) != (lat_j > lat):
            crossing_lng = lng_i + (lat - lat_i) * (lng_j - lng_i) / (lat_j - lat_i)
            if lng < crossing_lng:
                inside = not inside
        j = i
    return inside


@dataclass
class Polygon:
    """One or more rings with hole support, plus a bbox pre-filter.

    `parts` entries are (exterior_ring, [hole_ring, ...]) with coords as
    [lng, lat]. A rectangle is a poor model of a neighborhood; this lets a
    sub-area carry its true shape where one has been traced.
    """

    parts: list[tuple[list, list]]
    bbox: BBox

    def contains(self, lat: float, lng: float) -> bool:
        if not self.bbox.contains(lat, lng):
            return False
        for exterior, holes in self.parts:
            if point_in_ring(lat, lng, exterior) and not any(
                point_in_ring(lat, lng, hole) for hole in holes
            ):
                return True
        return False

    @property
    def exterior(self) -> list:
        """First exterior ring -- what the Redfin `poly` param needs."""
        return self.parts[0][0] if self.parts else []

    @classmethod
    def from_ring(cls, ring: list) -> "Polygon":
        lngs = [p[0] for p in ring]
        lats = [p[1] for p in ring]
        return cls(
            parts=[(ring, [])],
            bbox=BBox(min(lats), min(lngs), max(lats), max(lngs)),
        )


@dataclass
class SubArea:
    id: str
    name: str
    zip_codes: list[str]
    lakewood_orbit: float
    school_quality_score: int
    bbox: BBox
    raw: dict
    # Set when the config traces a real outline instead of a rectangle.
    polygon: Polygon | None = None

    def contains(self, lat: float, lng: float) -> bool:
        """Polygon containment when an outline exists, else bbox."""
        if self.polygon is not None:
            return self.polygon.contains(lat, lng)
        return self.bbox.contains(lat, lng)


def load_sub_areas(include_watch: bool = True) -> list[SubArea]:
    """Load sub-areas from the config file. Returns ordered list."""
    cfg = json.loads(CONFIG_PATH.read_text())
    out: list[SubArea] = []
    for entry in cfg["sub_areas"]:
        out.append(_to_sub_area(entry))
    if include_watch:
        for entry in cfg.get("watch_areas", []):
            out.append(_to_sub_area(entry))
    return out


def _to_sub_area(entry: dict) -> SubArea:
    polygon = Polygon.from_ring(entry["polygon"]) if entry.get("polygon") else None
    if bb := entry.get("bbox"):
        bbox = BBox(bb["sw_lat"], bb["sw_lng"], bb["ne_lat"], bb["ne_lng"])
    elif polygon is not None:
        # A traced outline carries its own extent; no need to restate it.
        bbox = polygon.bbox
    else:
        raise ValueError(f"Sub-area {entry.get('id')!r} needs a bbox or a polygon")
    return SubArea(
        id=entry["id"],
        name=entry["name"],
        zip_codes=entry["zip_codes"],
        lakewood_orbit=float(entry.get("lakewood_orbit", 0.0)),
        school_quality_score=int(entry.get("school_quality_score", 0) or 0),
        bbox=bbox,
        raw=entry,
        polygon=polygon,
    )


def assign_sub_area(lat: float | None, lng: float | None, areas: Iterable[SubArea]) -> str | None:
    """Return the first containing sub-area id, or None.

    Order matters: config lists specific neighborhoods before broader traced
    zones so a listing is tagged with the tightest area that holds it.
    """
    if lat is None or lng is None:
        return None
    for area in areas:
        if area.contains(lat, lng):
            return area.id
    return None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def write_snapshot(category: str, name: str, payload: dict | list) -> Path:
    """Write a dated JSON snapshot under data/<category>/.

    Snapshot file naming: data/<category>/<YYYY-MM-DD>_<name>.json
    Also writes data/<category>/latest_<name>.json for easy dashboard access.
    """
    out_dir = DATA_ROOT / category
    out_dir.mkdir(parents=True, exist_ok=True)
    dated = out_dir / f"{utc_today()}_{name}.json"
    latest = out_dir / f"latest_{name}.json"
    body = json.dumps(payload, indent=2, default=str)
    dated.write_text(body)
    latest.write_text(body)
    return dated


class RateLimiter:
    """Token-bucket-ish: minimum delay between calls."""

    def __init__(self, min_seconds: float):
        self.min_seconds = min_seconds
        self._last = 0.0

    def wait(self) -> None:
        elapsed = time.monotonic() - self._last
        if elapsed < self.min_seconds:
            time.sleep(self.min_seconds - elapsed)
        self._last = time.monotonic()


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}
