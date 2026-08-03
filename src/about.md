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
- Caruth Terrace — mostly Mockingbird, though individual listings do fall outside the zone.
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

Nine areas were dropped. Six had **zero** qualifying area anywhere in their bounds, grid-tested at 41×41 points against the official boundaries: Forest Hills, Old Lake Highlands, Town Creek, Moss Farm, Merriman Park Estates and Lochwood. Casa Linda and Little Forest Hills each had a ~10% Lakewood-zoned sliver but were dropped by preference.

**Vickery Place** was dropped after its bounding box was corrected. The old box sat entirely inside the M Streets box, and since a listing is assigned to the first area containing it, Vickery Place had never received a single listing — an empty scorecard costing a scrape call every run. Its apparent 59% Mockingbird coverage was really measuring M Streets ground. Corrected to its true extent (verified from listing addresses: Belmont / Willis / Vickery Blvd at lat 32.8085–32.8231), it is 75% Geneva Heights with no qualifying area at all. Correcting it also fixed a costlier problem: the oversized M Streets box had been absorbing Geneva Heights homes and inflating that area's sold median from a true $391/sqft to $451, which made M Streets listings look ~15% better value than they were.

Forest Hills is worth calling out. The old config ranked it Tier S with a "Lakewood Elementary / Long / Wilson" feeder and `lakewood_orbit: 1.0`. Checked against the official DISD boundaries it is entirely **Hexter Elementary / Hill MS / Bryan Adams HS**, verified at four corners and all three of its live listings. The Lakewood zone's east edge is -96.7197 and Forest Hills begins at -96.717, so it lies wholly outside. This is exactly why the gate reads polygons instead of the `feeder_pattern` labels.

All nine are documented in `removed_2026_08_02` in `config/sub_areas.json` and recoverable from git history.

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
- **Scored output is regenerated, not stored.** `data/listings/` and `data/sold/` are committed and irreplaceable; `data/stats/` is derived from them and gitignored, since committing it collided with every CI run that landed while a branch was open. Both the ETL job and the deploy job rebuild it. A past watchlist is still recoverable from git history, but rebuilding one applies today's weights rather than the weights in force that day.
- **Redfin CSV endpoint can fail.** If it returns HTML/captcha, the scraper logs an error and proceeds. Add a residential proxy (ScraperAPI, Bright Data) if it becomes flaky.
- **YoY appreciation samples can be thin.** A 47% YoY $/sqft jump in Hollywood Heights (small neighborhood) can mean three pricey closings, not a real trend. Always sanity-check against the 12-mo median.
- **DISD vs. RISD only matters in 2031+.** First child born this year would start kindergarten ~2031. Within a 5+ year hold, school zoning is a resale lever, not an operational concern. That is the argument for keeping the drawn Lake Highlands zone in scope despite it failing the elementary gate.

## Tweaking the scoring

Edit weights in `pipeline/score.py`:

```python
WEIGHTS = {
    "lot_size": 0.30,        # land; 4,000 sqft scores 0, 12,000 scores 1
    "character": 0.25,       # pre-1945 best, 1966-90 worst, new build modest
    "ppsf_vs_peers": 0.20,   # value vs size-matched sold comps
    "bath_adequacy": 0.10,   # baths per bedroom
    "size": 0.10,            # raw sqft, secondary by choice
    "price_fit": 0.05,
}
```

Then run `python -m pipeline.score` to regenerate the watchlist.

The score ranks **the house, not the location**, and it is tuned for one archetype: a character home on a real lot at a fair price. Lot and period character lead; raw square footage is secondary, because the biggest houses in this band are new builds on subdivided 3,000 sqft lots.

Three things were removed from the score because they were actively misleading:

- **`lakewood_orbit`** carried 30% and supplied 36% of all discriminating power. Once the gate settled location it double-charged the same preference, burying the drawn Lake Highlands zone by construction and penalizing Junius Heights for feeder uncertainty the gate now resolves per address.
- **`dom_leverage`** was the single strongest correlate of the old score, so a house that had sat 114 days ranked first. It is a flag beside the score now, not part of it.
- **`schools`** is guaranteed by the gate, so ranking it again only docked Lake Highlands homes for qualifying on geography.

If you want Lakewood-side proximity to count for something again, the honest way is a small weight keyed on the *qualifying basis*, not a revival of the 20-area orbit scale.

To change the gate itself rather than the ranking, edit `buy_box` in `config/sub_areas.json`. See the Tuning section of `README.md`.
