"""Sub-area scorecard aggregation.

Reads recent sold + active snapshots and produces per-sub-area stats:
  - active inventory count
  - sold count (last 30/90/365d if dates present)
  - median price, ppsf
  - DOM
  - turnover proxy (sold / active)

Outputs data/stats/latest_scorecards.json.
"""

from __future__ import annotations

import json
import logging
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scrapers.utils import DATA_ROOT, load_sub_areas, utc_now_iso, write_snapshot

LOG = logging.getLogger("aggregate")


def _load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text()).get("listings", [])


def _med(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _parse_date(s: str | None) -> datetime | None:
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(s.strip(), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    cfg = json.loads((Path(__file__).parent.parent / "config" / "sub_areas.json").read_text())
    area_lookup = {a["id"]: a for a in cfg["sub_areas"]}
    area_lookup.update({a["id"]: a for a in cfg.get("watch_areas", [])})

    actives = _load(DATA_ROOT / "listings" / "latest_redfin.json")
    solds = _load(DATA_ROOT / "sold" / "latest_redfin.json")

    by_area_active: dict[str, list[dict]] = defaultdict(list)
    by_area_sold: dict[str, list[dict]] = defaultdict(list)
    for li in actives:
        if sa := li.get("sub_area_id"):
            by_area_active[sa].append(li)
    for li in solds:
        if sa := li.get("sub_area_id"):
            by_area_sold[sa].append(li)

    now = datetime.now(timezone.utc)
    cutoff_30 = now - timedelta(days=30)
    cutoff_90 = now - timedelta(days=90)
    cutoff_365 = now - timedelta(days=365)

    scorecards = []
    for area_id, meta in area_lookup.items():
        a_list = by_area_active.get(area_id, [])
        s_list = by_area_sold.get(area_id, [])

        s_30 = [s for s in s_list if (d := _parse_date(s.get("sold_date"))) and d >= cutoff_30]
        s_90 = [s for s in s_list if (d := _parse_date(s.get("sold_date"))) and d >= cutoff_90]
        s_365 = [s for s in s_list if (d := _parse_date(s.get("sold_date"))) and d >= cutoff_365]

        scorecards.append({
            "id": area_id,
            "name": meta["name"],
            "tier": meta.get("tier", ""),
            "lakewood_orbit": meta.get("lakewood_orbit"),
            "school_district": meta.get("school_district"),
            "school_quality_score": meta.get("school_quality_score"),
            "config_median_12mo_usd": meta.get("median_sale_12mo_usd"),
            "config_yoy_pct": meta.get("yoy_appreciation_pct"),
            "active": {
                "n": len(a_list),
                "median_price_usd": _med([li["price_usd"] for li in a_list if li.get("price_usd")]),
                "median_ppsf_usd": _med([li["ppsf_usd"] for li in a_list if li.get("ppsf_usd")]),
                "median_dom_days": _med([li["days_on_market"] for li in a_list if li.get("days_on_market") is not None]),
            },
            "sold_30d": {
                "n": len(s_30),
                "median_price_usd": _med([s["price_usd"] for s in s_30 if s.get("price_usd")]),
                "median_ppsf_usd": _med([s["ppsf_usd"] for s in s_30 if s.get("ppsf_usd")]),
            },
            "sold_90d": {
                "n": len(s_90),
                "median_price_usd": _med([s["price_usd"] for s in s_90 if s.get("price_usd")]),
                "median_ppsf_usd": _med([s["ppsf_usd"] for s in s_90 if s.get("ppsf_usd")]),
            },
            "sold_365d": {
                "n": len(s_365),
                "median_price_usd": _med([s["price_usd"] for s in s_365 if s.get("price_usd")]),
                "median_ppsf_usd": _med([s["ppsf_usd"] for s in s_365 if s.get("ppsf_usd")]),
            },
            "turnover_proxy": (len(s_365) / max(1, len(a_list))) if a_list else None,
        })

    write_snapshot("stats", "scorecards", {
        "as_of": utc_now_iso(),
        "scorecards": scorecards,
    })
    LOG.info("Wrote scorecards for %d areas", len(scorecards))
    return 0


if __name__ == "__main__":
    sys.exit(main())
