---
title: Watchlist
toc: false
---

# Watchlist

Active listings ranked by buy-fit score. Score weights are tuned for Lakewood-orbit preference (30%), school quality (15%), price fit (20%), $/sqft vs. area (15%), DOM leverage (10%), vintage (5%), lot size (5%).

```js
const watchlist = await FileAttachment("../data/stats/latest_watchlist.json").json().catch(() => ({listings: [], as_of: null, n: 0}));
const subAreas = await FileAttachment("../config/sub_areas.json").json();
```

```js
const areaName = new Map([
  ...subAreas.sub_areas.map(a => [a.id, a.name]),
  ...(subAreas.watch_areas || []).map(a => [a.id, a.name])
]);
```

<div class="grid grid-cols-4">
  <div class="card"><h2>Active listings</h2><span class="big">${watchlist.n}</span></div>
  <div class="card"><h2>Top score</h2><span class="big">${watchlist.listings?.[0]?._score ?? "—"}</span></div>
  <div class="card"><h2>Buy box</h2><span class="big">$${(watchlist.buy_box?.price_min_usd / 1000) || 800}k–$${(watchlist.buy_box?.price_max_usd / 1000) || 1100}k</span></div>
  <div class="card"><h2>Last refresh</h2><span class="big">${watchlist.as_of?.slice(0, 10) ?? "no data"}</span></div>
</div>

## Top 30 by buy-fit score

```js
const top = (watchlist.listings || []).slice(0, 30);
```

```js
Inputs.table(top.map(li => ({
  Score: li._score,
  Sub_area: areaName.get(li.sub_area_id) ?? li.sub_area_id ?? "—",
  Address: li.address,
  Price: li.price_usd ? `$${(li.price_usd/1000).toFixed(0)}k` : "—",
  PPSF: li.ppsf_usd ? `$${li.ppsf_usd}` : "—",
  Beds: li.beds,
  Baths: li.baths,
  Sqft: li.sqft?.toLocaleString(),
  Lot: li.lot_size_sqft?.toLocaleString(),
  Year: li.year_built,
  DOM: li.days_on_market,
  Link: html`<a href="${li.url}" target="_blank">view</a>`
})), {
  rows: 30,
  format: { Score: x => html`<b>${x}</b>` }
})
```

## Score distribution

```js
Plot.plot({
  x: { label: "Score" },
  y: { label: "Listings" },
  marks: [
    Plot.rectY(watchlist.listings || [], Plot.binX({y: "count"}, {x: "_score", interval: 5, fill: "steelblue"})),
    Plot.ruleY([0])
  ],
  height: 200
})
```

## How the score works

| Component | Weight | What it measures |
|---|---:|---|
| Lakewood orbit | 30% | How "Lakewood" the sub-area feels (1.0 = Lakewood-side, 0.3 = deep LH) |
| Schools | 15% | Feeder pattern quality (Woodrow > RISD pockets > Bryan Adams) |
| Price fit | 20% | Inside buy box = full credit; over $1.1M = linear penalty |
| $/sqft vs. area | 15% | Bonus for buying ≤ area median; penalty for paying > 1.2x median |
| DOM leverage | 10% | Longer-on-market = more negotiation room |
| Vintage | 5% | Newer build = more turnkey |
| Lot size | 5% | Bigger lots win ties |

Tweak weights in `pipeline/score.py` and rerun `python -m pipeline.score`.
