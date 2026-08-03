---
title: About
---

# About this tracker

Personal tracker for Lakewood-orbit and Lake Highlands sub-areas in Dallas. Built around a **$750K–$1M, 3+ bed / 2+ bath** turnkey buy box, gated to homes zoned to **Mockingbird or Lakewood Elementary** or sitting inside a hand-drawn Lake Highlands zone.

## The eligibility gate

As of 2026-08-02, schools are a hard requirement rather than a 10% scoring weight. A listing must clear **all** of:

| Requirement | Rule |
|---|---|
| Price | $750,000–$1,000,000 |
| Bedrooms | 3 or more |
| Bathrooms | 2 or more |
| Location | Zoned to Mockingbird or Lakewood Elementary, **or** inside the drawn Lake Highlands zone |

There is no sqft floor. Beds and baths carry the size requirement.

Zoning is resolved **per address** from the listing's coordinates against the official Dallas ISD 2026-27 attendance polygons, cached in `config/school_zones.geojson`. Listings that fail are kept in the snapshot's `excluded` array with their reasons, and the ones that failed only on location are surfaced on the Watchlist as near misses ranked by distance to the boundary.

## Sub-areas tracked

**Fully inside a qualifying zone:**
- Hollywood Heights / Santa Monica — entire footprint is Lakewood (east) or Mockingbird (west). Conservation district.

**Partially zoned, so verify per address:**
- M Streets / Greenland Hills — Mockingbird covers part of it. Best price fit of any strong area at an $865K median. Conservation district, Greenville-walkable.
- Caruth Terrace — mostly Mockingbird, but the last snapshot's two listings both fell outside the zone.
- Vickery Place — northern portion Mockingbird; southern splits to Geneva Heights and Lipscomb and fails.
- Lakewood Hills — Lakewood covers the southern portion; the northern strip fails.
- Lakewood Heights — split across both qualifying zones, covering most of it.

**Qualifying zoning but above the $1M ceiling, so listings will be rare:**
- Lakewood proper ($1.5M median), Hillside ($1.3M), Wilshire Heights ($1.5M). Kept largely for their comp sets.

**Qualifying on geography only, via the drawn zone:**
- L Streets (drawn Lake Highlands zone) — RISD, so the elementary gate can never pass here. Bounded by Audelia Rd, Plano Rd, East Northwest Hwy, and a line just south of I-635.
- Lake Park Estates — Hexter-zoned, but its northwest corner falls inside the drawn zone.
- Lake Highlands Estates — RISD and mostly west of Audelia, so only its eastern edge qualifies.

**Watch list:** Mockingbird Meadows — about half its footprint is Mockingbird-zoned, which the old config did not reflect.

## Why these and not others

Eight areas were dropped on 2026-08-02. Six had **zero** qualifying area anywhere in their bounds, grid-tested at 41×41 points against the official boundaries: Forest Hills, Old Lake Highlands, Town Creek, Moss Farm, Merriman Park Estates and Lochwood. Casa Linda and Little Forest Hills each had a ~10% Lakewood-zoned sliver but were dropped by preference.

Forest Hills is worth calling out. The old config ranked it Tier S with a "Lakewood Elementary / Long / Wilson" feeder and `lakewood_orbit: 1.0`. Checked against the official DISD boundaries it is entirely **Hexter Elementary / Hill MS / Bryan Adams HS**, verified at four corners and all three of its live listings. The Lakewood zone's east edge is -96.7197 and Forest Hills begins at -96.717, so it lies wholly outside. This is exactly why the gate reads polygons instead of the `feeder_pattern` labels.

All eight are documented in `removed_2026_08_02` in `config/sub_areas.json` and recoverable from git history.

## Data sources

- **Redfin** — active listings + recently sold via the gis-csv endpoint, refreshed daily
- **DCAD** — parcel characteristics, ownership, tax history via bulk download, refreshed weekly
- **Configured medians** — Redfin and Homes.com market reports as of early 2026 (see `config/sub_areas.json` `notes`)

Texas is a non-disclosure state, so DCAD has appraised values, not sale prices. The Redfin scrape is the source of truth for actual transaction prices.

## Refresh cadence

- **Daily 06:00 UTC** — Redfin active listings + score watchlist
- **Weekly Sunday 06:00 UTC** — Redfin sold comps + DCAD parcels + scorecards
- **Monthly 1st 06:00 UTC** — full archive snapshot to `data/archive/`

## Caveats

- **Bounding boxes are approximate.** Real neighborhood polygons are irregular. They now only drive scraping and labeling, never eligibility, so the imprecision no longer affects who qualifies. See `config/sub_areas.json` `geometry_note`.
- **The drawn Lake Highlands zone is a reconstruction.** Traced from a hand-drawn map outline with its edges snapped to OpenStreetMap centerlines for Audelia Rd, Plano Rd and East Northwest Hwy. The north edge, tracking just south of I-635, is the softest of the four. If strong near misses cluster just past one edge, that edge is drawn too tight.
- **Zoning is coordinate-based.** Redfin lat/lng is rooftop-grade but not surveyed. Listings within 40m of an attendance boundary are flagged `near_zone_edge`; confirm those on DISD SchoolFinder before touring.
- **Only DISD boundaries are cached, because only DISD publishes them.** Richardson ISD has no public attendance-boundary service, only a third-party address-lookup app, and the national boundary survey is a decade out of date. The RISD feeder shown for the Lake Highlands areas is therefore orientation only, flagged `feeder_verified: false`. It gates nothing, since those areas qualify on geography rather than schools, but do not treat it as confirmed.
- **Redfin CSV endpoint can fail.** If it returns HTML/captcha, the scraper logs an error and proceeds. Add a residential proxy (ScraperAPI, Bright Data) if it becomes flaky.
- **YoY appreciation samples can be thin.** A 47% YoY $/sqft jump in Hollywood Heights (small neighborhood) can mean three pricey closings, not a real trend. Always sanity-check against the 12-mo median.
- **DISD vs. RISD only matters in 2031+.** First child born this year would start kindergarten ~2031. Within a 5+ year hold, school zoning is a resale lever, not an operational concern. That is the argument for keeping the drawn Lake Highlands zone in scope despite it failing the elementary gate.

## Tweaking the scoring

Edit weights in `pipeline/score.py`:

```python
WEIGHTS = {
    "ppsf_vs_peers": 0.30,  # the value signal: $/sqft vs size-matched sold comps
    "lot_size": 0.20,
    "dom_leverage": 0.15,   # longer on market = more negotiation room
    "vintage": 0.15,
    "schools": 0.10,        # zoning *confidence*, not quality
    "price_fit": 0.10,
}
```

Then run `python -m pipeline.score` to regenerate the watchlist.

The score ranks **the house, not the location**, because the gate already settled location and all three qualifying bases count equally. `lakewood_orbit` used to carry 30% here and was supplying 36% of the score's whole discriminating power; once the gate existed it double-charged the same preference, burying the drawn Lake Highlands zone by construction and penalizing Junius Heights for feeder uncertainty the gate now resolves. It is still reported per listing as context but no longer affects the number.

`price_fit` and `schools` stay small on purpose: the gate enforces both, so neither can move more than a point or two. If you want to bias back toward Lakewood-side proximity, the honest way is to add a small weight keyed on the *qualifying basis* rather than reviving the old 20-area orbit scale.

To change the gate itself rather than the ranking, edit `buy_box` in `config/sub_areas.json`. See the Tuning section of `README.md`.
