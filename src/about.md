---
title: About
---

# About this tracker

Personal tracker for Lakewood-orbit and Lake Highlands sub-areas in Dallas. Built around a $800K–$1.1M turnkey buy box with strong Lakewood preference.

## Sub-areas tracked

**Tier S (Lakewood-side, prime focus):**
- Forest Hills (75218) — Woodrow feeder, lake-walkable
- Hollywood Heights / Santa Monica — conservation district, Woodrow
- M Streets / Greenland Hills — conservation district, Woodrow, Greenville-walkable

**Tier A (strong contenders):**
- Moss Farm — RISD, +26% YoY momentum
- Merriman Park Estates — RISD A- elementary, hot market (22 DOM)
- Casa Linda — best Lakewood-orbit value, Bryan Adams feeder

**Tier B (top-of-band buys):**
- Lake Highlands Estates — RISD, ~$1M median
- Old Lake Highlands — best $/sqft, slowest market = leverage, Bryan Adams

**Tier C (top-of-area, RISD optionality):**
- L Streets — RISD, but ~2x area median at this price
- Town Creek — RISD at lower entry

**Watch list:** Lochwood, Mockingbird Meadows, Lakewood Heights.

## Why these and not others

Lakewood proper ($1.6M median Feb 2026), Wilshire Heights ($1.5M), Junius Heights ($494K), Vickery Place ($1.1M and rising fast) all fail the buy-box fit test for different reasons. See `config/sub_areas.json` for the full reasoning.

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

- **Bounding boxes are approximate.** Real neighborhood polygons are irregular. Refine using DCAD GIS shapefiles when polygon precision matters. See `config/sub_areas.json` `bbox_disclaimer`.
- **Redfin CSV endpoint can fail.** If it returns HTML/captcha, the scraper logs an error and proceeds. Add a residential proxy (ScraperAPI, Bright Data) if it becomes flaky.
- **YoY appreciation samples can be thin.** A 47% YoY $/sqft jump in Hollywood Heights (small neighborhood) can mean three pricey closings, not a real trend. Always sanity-check against the 12-mo median.
- **DISD vs. RISD only matters in 2031+.** First child born this year would start kindergarten ~2031. Within a 5+ year hold, school zoning is a resale lever, not an operational concern.

## Tweaking the scoring

Edit weights in `pipeline/score.py`:

```python
WEIGHTS = {
  "lakewood_orbit": 0.30,  # turn this up to bias harder toward Lakewood-side
  "schools": 0.15,
  "price_fit": 0.20,
  "ppsf_vs_area": 0.15,
  "dom_leverage": 0.10,
  "vintage": 0.05,
  "lot_size": 0.05,
}
```

Then run `python -m pipeline.score` to regenerate the watchlist.
