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


@dataclass
class SubArea:
    id: str
    name: str
    zip_codes: list[str]
    lakewood_orbit: float
    school_quality_score: int
    bbox: BBox
    raw: dict


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
    bb = entry["bbox"]
    return SubArea(
        id=entry["id"],
        name=entry["name"],
        zip_codes=entry["zip_codes"],
        lakewood_orbit=float(entry.get("lakewood_orbit", 0.0)),
        school_quality_score=int(entry.get("school_quality_score", 0) or 0),
        bbox=BBox(bb["sw_lat"], bb["sw_lng"], bb["ne_lat"], bb["ne_lng"]),
        raw=entry,
    )


def assign_sub_area(lat: float | None, lng: float | None, areas: Iterable[SubArea]) -> str | None:
    """Return the first matching sub-area id by bbox containment, or None."""
    if lat is None or lng is None:
        return None
    for area in areas:
        if area.bbox.contains(lat, lng):
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
