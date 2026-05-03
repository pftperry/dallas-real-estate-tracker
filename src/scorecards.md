---
title: Sub-area scorecards
---

# Sub-area scorecards

Ten primary sub-areas plus three on the watch list. Charts focus on the buyer's two real questions: *where does my $800K–$1.1M actually buy turnkey?* and *where do I have negotiation leverage?*

```js
const card = await FileAttachment("data/scorecards.json").json();
const config = await FileAttachment("data/sub_areas.json").json();
const sold = await FileAttachment("data/sold.json").json();
const watchlist = await FileAttachment("data/watchlist.json").json();
```

```js
const areaName = new Map([
  ...config.sub_areas.map(a => [a.id, a.name]),
  ...(config.watch_areas || []).map(a => [a.id, a.name])
]);
const tierColor = { S: "#16a34a", A: "#2563eb", B: "#a16207", C: "#9333ea" };
const buyBox = config.buy_box;
const soldRows = (sold.listings || []).filter(d => d.sub_area_id);
```

## What your buy box actually buys

Each dot is one sold home in the last 6 months. The shaded rectangle is your buy box ($${(buyBox.price_min_usd/1000).toFixed(0)}K–$${(buyBox.price_max_usd/1000).toFixed(0)}K, 1,200–4,000 sqft turnkey range). Areas where the dots cluster *inside* the rectangle are where you can transact without stretching.

```js
Plot.plot({
  marginLeft: 70,
  width: 900,
  height: 480,
  x: { label: "Square feet", grid: true, domain: [800, 5000] },
  y: { label: "Sale price", grid: true, tickFormat: d => "$" + (d/1000).toFixed(0) + "k", domain: [400000, 1500000] },
  color: { legend: true, label: "Sub-area" },
  marks: [
    Plot.rect([{x1: 1200, x2: 4000, y1: buyBox.price_min_usd, y2: buyBox.price_max_usd}],
      { x1: "x1", x2: "x2", y1: "y1", y2: "y2", fill: "#22c55e", fillOpacity: 0.10, stroke: "#16a34a", strokeOpacity: 0.4, strokeDasharray: "4,4" }),
    Plot.dot(soldRows.filter(d => d.price_usd && d.sqft), {
      x: "sqft",
      y: "price_usd",
      stroke: d => areaName.get(d.sub_area_id) ?? d.sub_area_id,
      r: 3.5,
      fillOpacity: 0.7,
      title: d => `${d.address}\n$${(d.price_usd/1000).toFixed(0)}k @ $${d.ppsf_usd}/sqft\n${d.sqft} sqft, built ${d.year_built}\n${areaName.get(d.sub_area_id) ?? ""}\nSold ${d.sold_date}`
    })
  ]
})
```

## Buy-box capture rate (last 6mo)

Share of recent sales that closed *inside* your $${(buyBox.price_min_usd/1000).toFixed(0)}K–$${(buyBox.price_max_usd/1000).toFixed(0)}K band. Higher = more buyer activity at your price point = more comps to anchor on, and faster signal when something prices wrong.

```js
const captureByArea = d3.rollups(
  soldRows,
  rows => {
    const total = rows.length;
    const inBox = rows.filter(r =>
      r.price_usd && r.price_usd >= buyBox.price_min_usd && r.price_usd <= buyBox.price_max_usd
    ).length;
    return {
      total,
      inBox,
      pct: total ? inBox / total : 0
    };
  },
  d => d.sub_area_id
).map(([id, v]) => ({
  id,
  name: areaName.get(id) ?? id,
  total: v.total,
  inBox: v.inBox,
  pct: v.pct,
  tier: config.sub_areas.find(a => a.id === id)?.tier ?? ""
})).sort((a, b) => b.pct - a.pct);
```

```js
Plot.plot({
  marginLeft: 200,
  width: 900,
  height: 360,
  x: { label: "Share of last-6mo sales in your buy box", percent: true, grid: true, domain: [0, 1] },
  y: { label: null },
  marks: [
    Plot.barX(captureByArea, {
      x: "pct",
      y: "name",
      sort: { y: "x", reverse: true },
      fill: d => tierColor[d.tier] || "#737373"
    }),
    Plot.text(captureByArea, {
      x: "pct",
      y: "name",
      text: d => `${(d.pct * 100).toFixed(0)}%  (${d.inBox}/${d.total})`,
      dx: 6,
      textAnchor: "start",
      fontSize: 11,
      fill: "currentColor"
    }),
    Plot.ruleX([0])
  ]
})
```

## $/sqft distribution by sub-area (last 6mo sold)

Boxes show the IQR — wider = more dispersion = more mispricing opportunities. The line in the middle is the median. Outliers as dots.

```js
Plot.plot({
  marginLeft: 200,
  width: 900,
  height: 420,
  x: { label: "$/sqft", grid: true },
  y: { label: null },
  marks: [
    Plot.boxX(soldRows.filter(d => d.ppsf_usd), {
      x: "ppsf_usd",
      y: d => areaName.get(d.sub_area_id) ?? d.sub_area_id,
      sort: { y: "x", reduce: "median", reverse: true },
      stroke: d => tierColor[config.sub_areas.find(a => a.id === d.sub_area_id)?.tier] || "#737373",
      fill: d => tierColor[config.sub_areas.find(a => a.id === d.sub_area_id)?.tier] || "#737373",
      fillOpacity: 0.15
    })
  ]
})
```

## Days-on-market distribution (active inventory)

Each dot is one active listing. Areas with dots far to the right have stale listings — that's where you have leverage. Areas with all dots near zero are competitive.

```js
const activeRows = (watchlist.listings || []).filter(d => d.sub_area_id && d.days_on_market != null);
```

```js
Plot.plot({
  marginLeft: 200,
  width: 900,
  height: 380,
  x: { label: "Days on market", grid: true, domain: [0, d3.max(activeRows, d => d.days_on_market) || 200] },
  y: { label: null },
  marks: [
    Plot.dot(activeRows, {
      x: "days_on_market",
      y: d => areaName.get(d.sub_area_id) ?? d.sub_area_id,
      sort: { y: "x", reduce: "median", reverse: true },
      stroke: d => tierColor[config.sub_areas.find(a => a.id === d.sub_area_id)?.tier] || "#737373",
      fill: d => tierColor[config.sub_areas.find(a => a.id === d.sub_area_id)?.tier] || "#737373",
      fillOpacity: 0.5,
      r: 4,
      title: d => `${d.address}\n$${(d.price_usd/1000).toFixed(0)}k\n${d.days_on_market} DOM`
    })
  ]
})
```

## YoY appreciation (config snapshot)

Trailing-12mo appreciation per area, from the config. Use as directional reference rather than precise truth — small areas can swing on 2-3 closings.

```js
const yoyData = [...config.sub_areas, ...(config.watch_areas || [])]
  .filter(a => a.yoy_appreciation_pct != null)
  .map(a => ({ name: a.name, pct: a.yoy_appreciation_pct, tier: a.tier ?? "" }));
```

```js
Plot.plot({
  marginLeft: 200,
  width: 900,
  height: 320,
  x: { label: "12-mo appreciation", percent: false, tickFormat: d => `${d.toFixed(0)}%`, grid: true },
  y: { label: null },
  marks: [
    Plot.barX(yoyData, {
      x: "pct",
      y: "name",
      sort: { y: "x", reverse: true },
      fill: d => d.pct >= 0 ? (tierColor[d.tier] || "#16a34a") : "#dc2626"
    }),
    Plot.ruleX([0])
  ]
})
```

## Sortable scorecard

```js
const rows = card.scorecards.map(c => ({
  Tier: c.tier || "—",
  Name: c.name,
  Lakewood_orbit: c.lakewood_orbit,
  Schools: `${c.school_district || ""} (${c.school_quality_score ?? "—"}/10)`,
  Active: c.active.n,
  Active_median_$: c.active.median_price_usd ? `$${(c.active.median_price_usd/1000).toFixed(0)}k` : "—",
  Active_DOM: c.active.median_dom_days ?? "—",
  Sold_30d: c.sold_30d.n,
  Sold_90d: c.sold_90d.n,
  Sold_90d_median_$: c.sold_90d.median_price_usd ? `$${(c.sold_90d.median_price_usd/1000).toFixed(0)}k` : "—",
  Sold_90d_PPSF: c.sold_90d.median_ppsf_usd ? `$${c.sold_90d.median_ppsf_usd}` : "—",
  Cfg_12mo_median_$: c.config_median_12mo_usd ? `$${(c.config_median_12mo_usd/1000).toFixed(0)}k` : "—",
  Cfg_YoY: c.config_yoy_pct != null ? `${c.config_yoy_pct.toFixed(1)}%` : "—"
}));
```

```js
Inputs.table(rows, { rows: 25 })
```

## Notes per sub-area

```js
const allAreas = [...config.sub_areas, ...(config.watch_areas || [])];
```

```js
html`<dl class="notes">${allAreas.map(a => html`
  <dt><b>${a.name}</b> <span class="muted">(${a.tier ? `Tier ${a.tier}` : "watch"})</span></dt>
  <dd>${a.notes || ""}</dd>
`)}</dl>`
```

<style>
.notes dt { margin-top: 0.5rem; }
.notes dd { margin-left: 1rem; color: var(--theme-foreground-muted); }
.muted { color: var(--theme-foreground-muted); font-weight: normal; font-size: 0.85em; }
</style>
