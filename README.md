# Dallas Real Estate Tracker

Personal tracker for Lakewood-orbit and Lake Highlands sub-areas. Built around a $800K–$1.1M turnkey buy box with strong Lakewood-side preference.

## What this does

- **Daily** Scrapes active Redfin listings in 10 target sub-areas + 3 watch areas, scores them against your buy-box preferences, and writes a ranked watchlist.
- **Weekly** Scrapes recent sold comps, refreshes DCAD parcel data, and rebuilds the sub-area scorecards.
- **Static dashboard** Observable Framework site deployed to GitHub Pages — Watchlist, Sub-area scorecards, Comps explorer, $/sqft heat map.

## Quick start (local)

```bash
# Python 3.12+ for the scrapers
python -m scrapers.redfin --status active   # ~1 min, hits Redfin's gis-csv endpoint
python -m scrapers.redfin --status sold     # for comps
python -m pipeline.score                    # generates watchlist
python -m pipeline.aggregate                # generates scorecards

# Node 20+ for the dashboard
npm install
OBSERVABLE_BASE=/ npm run dev               # opens http://localhost:3000
```

DCAD bulk download is large (~1.5GB unzipped). Run sparingly:

```bash
python -m scrapers.dcad        # full download + parse
python -m scrapers.dcad --dry-run   # reuse cached zip
```

## Deploying

This repo is wired for GitHub Pages. After the first push, enable Pages in the repo settings:

1. **GitHub.com → repo → Settings → Pages**
2. **Source:** GitHub Actions
3. Trigger the first run: **Actions → ETL → Run workflow** (or wait for daily 06:00 UTC cron)
4. Site lives at `https://pftperry.github.io/dallas-real-estate-tracker/`

The workflow has two jobs:
- **etl** — runs scrapers, scores, aggregates, and commits JSON snapshots back to `data/`
- **build-and-deploy** — builds the Observable Framework site and publishes it to Pages

Permissions are set in `.github/workflows/etl.yml` (`contents: write`, `pages: write`, `id-token: write`); no extra secrets needed.

## Project layout

```
.github/workflows/etl.yml      # daily + weekly cron, GH Pages deploy
config/sub_areas.json          # 10 polygons + metadata + buy box
scrapers/
  utils.py                     # polygon filtering, rate limiting, snapshot writer
  dcad.py                      # DCAD bulk download + parcel filter
  redfin.py                    # Redfin gis-csv scraper (active/sold)
pipeline/
  score.py                     # watchlist scoring engine
  aggregate.py                 # sub-area scorecards
data/                          # JSON snapshots (committed; this is the time-series)
  listings/                    # active listings, dated + latest_*.json
  sold/                        # sold comps, dated + latest_*.json
  parcels/                     # DCAD parcels, dated + latest_*.json
  stats/                       # scored watchlist, scorecards, dated + latest_*.json
src/                           # Observable Framework dashboard
  index.md                     # Watchlist (default page)
  scorecards.md                # Sub-area scorecards
  comps.md                     # Comps explorer
  heatmap.md                   # $/sqft heat map
  about.md                     # Methodology + tier explanations
package.json
observablehq.config.js
requirements.txt
```

## Tuning

- **Buy box** — edit `config/sub_areas.json` `buy_box` to change min/max price.
- **Scoring weights** — edit `pipeline/score.py` `WEIGHTS`.
- **Sub-areas** — add/remove from `config/sub_areas.json`. Bounding boxes are approximate; refine using DCAD GIS shapefiles when polygon precision matters.

## Known limitations

- **Redfin scraping is fragile.** The gis-csv endpoint may rate-limit or captcha. If that happens, add a residential proxy (ScraperAPI, Bright Data) or run from a residential IP. The scraper logs and exits cleanly on failure rather than retrying blindly.
- **Bounding boxes are approximate.** A rectangle is not a neighborhood. For real polygons, plug DCAD GIS shapefiles into `scrapers/utils.assign_sub_area`.
- **Texas non-disclosure.** DCAD has appraised values, NOT sale prices. The Redfin scrape is the only source of actual transaction prices.
- **Thin samples.** Several sub-areas have YoY swings driven by 2-3 closings. Trust the 12-mo median, not the 30-day median, for direction.

## Why these sub-areas

See `src/about.md` for the full reasoning. Short version: Lakewood proper ($1.6M median) is out of band, so the screen targets the next-best-fit Lakewood-orbit pockets (Forest Hills, Hollywood Heights, M Streets, Casa Linda) plus the strongest RISD pockets (Moss Farm, Merriman Park Estates, Lake Highlands Estates).
