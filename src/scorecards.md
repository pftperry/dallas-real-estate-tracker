---
title: Sub-area scorecards
---

# Sub-area scorecards

Ten primary sub-areas plus three on the watch list. Sortable by any column.

```js
const card = await FileAttachment("../data/stats/latest_scorecards.json").json().catch(() => ({scorecards: []}));
const config = await FileAttachment("../config/sub_areas.json").json();
```

```js
const tierColor = { S: "#16a34a", A: "#2563eb", B: "#a16207", C: "#9333ea" };
```

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

## Inventory vs. turnover

Hover for sub-area. Bigger circles = more active inventory. Higher Y = more sold in last 90d.

```js
Plot.plot({
  x: { label: "Active inventory", grid: true },
  y: { label: "Sold (last 90d)", grid: true },
  marks: [
    Plot.dot(card.scorecards, {
      x: d => d.active.n,
      y: d => d.sold_90d.n,
      r: d => Math.sqrt(d.active.n + 1) * 4,
      fill: d => tierColor[d.tier] || "#666",
      stroke: "white",
      title: d => `${d.name}\nActive: ${d.active.n}\nSold 90d: ${d.sold_90d.n}\nMedian $: ${d.sold_90d.median_price_usd ?? "—"}`
    }),
    Plot.text(card.scorecards, { x: d => d.active.n, y: d => d.sold_90d.n, text: "name", dy: -12, fontSize: 10 })
  ],
  height: 400
})
```

## $/sqft by sub-area (last 90d sold)

```js
Plot.plot({
  marginLeft: 180,
  x: { label: "$/sqft (sold last 90d, median)", grid: true },
  y: { label: null },
  marks: [
    Plot.barX(
      card.scorecards.filter(c => c.sold_90d.median_ppsf_usd),
      {
        x: "sold_90d.median_ppsf_usd",
        y: "name",
        sort: { y: "x", reverse: true },
        fill: d => tierColor[d.tier] || "#666"
      }
    ),
    Plot.ruleX([0])
  ],
  height: 350
})
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
