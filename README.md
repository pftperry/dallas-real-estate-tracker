# Dallas Real Estate Tracker

Personal tracker for Lakewood-orbit and Lake Highlands sub-areas. Built around a **$750K–$1M, 3+ bed / 2+ bath** turnkey buy box, gated to homes zoned to **Mockingbird or Lakewood Elementary** or sitting inside a hand-drawn Lake Highlands zone.

## What this does

- **Daily** Scrapes active Redfin listings in 12 target sub-areas + 1 watch area, applies a hard eligibility gate, scores the survivors, and writes a ranked watchlist.
- **Weekly** Scrapes recent sold comps, refreshes DCAD parcel data, and rebuilds the sub-area scorecards.
- **Static dashboard** Observable Framework site deployed to GitHub Pages — Watchlist, Sub-area scorecards, Comps explorer, $/sqft heat map.

## The eligibility gate

Added 2026-08-02. Schools went from a 10% scoring weight to a hard requirement. A listing must clear **all** of:

| Requirement | Rule |
|---|---|
| Price | $750,000–$1,000,000 |
| Bedrooms | `beds >= 3` |
| Bathrooms | `baths >= 2` |
| Location | Zoned to Mockingbird or Lakewood Elementary, **or** inside the drawn Lake Highlands zone (`l_streets`) |

There is **no sqft floor** — beds and baths carry the size requirement.

Zoning is resolved **per listing** from its lat/lng against official DISD attendance polygons, cached in `config/school_zones.geojson`. It is deliberately not read from the `feeder_pattern` strings in `config/sub_areas.json`, because those were wrong: the config called Forest Hills a Lakewood Elementary feeder and ranked it Tier S, but it is entirely **Hexter / Hill MS / Bryan Adams HS**, verified at four corners and every live listing. Trust `scrapers/school_zones.py`, not the labels.

The cache holds **all 135** district elementary zones, not just the two that qualify. That is what lets a rejected listing be reported honestly: with a two-zone cache, "in neither polygon" could not distinguish a Hexter address from a Richardson ISD one. Location failures now split into `wrong_elementary` (resolved to a real DISD zone that is not allowlisted, and the near-miss table names it) and `outside_disd`. `Zone.qualifies` is the separate allowlist question.

The allowlist is stated in two places: `buy_box.eligibility.elementary_allowlist` in the config, and `TARGET_ELEMENTARIES` in `scrapers/school_zones.py`. `pipeline/score.py` refuses to run if they disagree, so the dashboard cannot advertise one rule while the gate applies another.

Failed listings are not discarded silently. They are written to the `excluded` array in the watchlist snapshot with their reasons, so "why isn't this house on my list?" is always answerable, and the dashboard surfaces the ones that failed **only** on location as near misses ranked by distance to the boundary.

DISD redraws boundaries annually, typically late spring for the next school year. Re-pull after that lands:

```bash
python -m scrapers.school_zones --refresh
```

Spot-check any coordinate:

```bash
python -m scrapers.school_zones --check 32.8285 -96.7770
```

## Quick start (local)

```bash
# Python 3.12+ for the scrapers
python -m scrapers.redfin --status active   # ~1 min, hits Redfin's gis-csv endpoint
python -m scrapers.redfin --status sold     # for comps
python -m pipeline.score                    # applies the gate, then scores
python -m pipeline.aggregate                # generates scorecards

# Node 20+ for the dashboard
npm install
OBSERVABLE_BASE=/ npm run dev               # opens http://localhost:3000
```

On Windows the `python` alias may resolve to the Microsoft Store stub. Use `py` instead.

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
config/sub_areas.json          # sub-areas + metadata + buy box + eligibility gate
config/school_zones.geojson    # all 135 cached DISD elementary polygons (~1MB)
scrapers/
  utils.py                     # point-in-polygon, rate limiting, snapshot writer
  dcad.py                      # DCAD bulk download + parcel filter
  redfin.py                    # Redfin gis-csv scraper (active/sold)
  school_zones.py              # per-address elementary zoning lookup + --refresh
pipeline/
  score.py                     # eligibility gate, then watchlist scoring
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

- **Buy box / gate** — edit `config/sub_areas.json` `buy_box`. `price_min_usd`, `price_max_usd`, `beds_min`, `baths_min` are the numeric filters. Add `sqft_min` back if you want a size floor again. `eligibility.elementary_allowlist` controls which zones qualify, and `eligibility.focus_zone_allowlist` names the geographic escape hatches.
- **Adding a qualifying elementary** — add its exact `ELEM_DESC` to `TARGET_ELEMENTARIES` in `scrapers/school_zones.py` **and** to `eligibility.elementary_allowlist` in the config. No `--refresh` is needed: the whole district is already cached, so the new zone only has to be allowlisted. Both `--refresh` and `pipeline.score` fail loud on a name that does not exist or on the two lists disagreeing, rather than silently emptying the gate.
- **Redrawing a focus zone** — edit the `polygon` array on the area (`[lng, lat]` pairs, closed ring). Any area with a `polygon` uses true point-in-polygon containment instead of its bbox, and the dashboard draws it solid rather than dashed.
- **Scoring weights** — edit `pipeline/score.py` `WEIGHTS`.
- **Sub-areas** — add/remove from `config/sub_areas.json`. Order matters: `assign_sub_area` takes the first containing area, so list specific neighborhoods before broader zones. Bounding boxes are approximate and only drive scraping and labeling, never eligibility.

## Known limitations

- **Redfin scraping is fragile.** The gis-csv endpoint may rate-limit or captcha. If that happens, add a residential proxy (ScraperAPI, Bright Data) or run from a residential IP. The scraper logs and exits cleanly on failure rather than retrying blindly.
- **Bounding boxes are approximate.** A rectangle is not a neighborhood. They only drive scraping and labeling now, so this no longer affects who qualifies. For real outlines, add a `polygon` to the area or plug DCAD GIS shapefiles into `scrapers/utils.assign_sub_area`.
- **The drawn Lake Highlands zone is a reconstruction.** Traced from a hand-drawn map outline, with its four edges snapped to OpenStreetMap centerlines for Audelia Rd (-96.7179), Plano Rd (-96.7004) and East Northwest Hwy (32.8640). The north edge tracks just south of I-635 and is the softest of the four. If good near misses cluster just past one edge, that edge is drawn too tight.
- **Zoning is coordinate-based.** Redfin lat/lng is rooftop-grade but not surveyed. Listings within 40m of an attendance boundary get a `near_zone_edge` flag; confirm those on DISD SchoolFinder before touring. Sub-area *labels* in an old snapshot can also go stale after a config change, since they were assigned at scrape time — re-run the scraper to resync them. Eligibility always recomputes from coordinates, so it is never stale.
- **`lookup()` returning `None` means outside Dallas ISD.** All 135 district zones are cached, so a Hexter address returns the Hexter `Zone` with `qualifies == False`. Any caller gating on eligibility must check `.qualifies`, not just truthiness. Only DISD is cached, so RISD zoning is still unverified.
- **The cache is normalized, not byte-identical to the source.** Features are sorted by `SLN` and coordinates rounded to 6 decimal places (~11cm, far below listing-coordinate accuracy) so the committed file changes only when a boundary genuinely moves, instead of churning ~1MB on every weekly refresh.
- **Texas non-disclosure.** DCAD has appraised values, NOT sale prices. The Redfin scrape is the only source of actual transaction prices.
- **Thin samples.** Several sub-areas have YoY swings driven by 2-3 closings. Trust the 12-mo median, not the 30-day median, for direction.

## Why these sub-areas

See `src/about.md` for the full reasoning. Short version: the screen keeps areas that contain qualifying territory and drops the rest.

**Best fit** — Hollywood Heights is the standout: its entire footprint sits inside one of the two qualifying zones (split Lakewood east / Mockingbird west). M Streets is next, and has the best price fit of any Tier S area at an $865K median, comfortably mid-band.

**Kept but price-constrained** — Lakewood proper, Lakewood Hills, Lakewood Heights, Hillside and Wilshire Heights all have qualifying zoning but medians from $1.2M to $1.6M, above the $1M ceiling. Expect few listings; kept largely for the comp sets.

**Kept for geographic overlap only** — Lake Park Estates (Hexter-zoned, but its northwest corner falls in the drawn zone) and Lake Highlands Estates (RISD, only its eastern edge past Audelia qualifies).

**Dropped 2026-08-02** — Forest Hills, Old Lake Highlands, Town Creek, Moss Farm, Merriman Park Estates and Lochwood had zero qualifying area anywhere in their bounds under 41×41-point grid testing. Casa Linda and Little Forest Hills each had a ~10% Lakewood-zoned sliver but were dropped by preference. All are recoverable from `removed_2026_08_02` in the config and from git history.
