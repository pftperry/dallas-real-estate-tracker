---
title: $/sqft heat map
---

# $/sqft heat map

Where dispersion is highest = best fishing for mispriced listings. Tight clusters mean the market is "efficient" in that area; wide spread means anomalies live there.

```js
const sold = await FileAttachment("data/sold.json").json();
const config = await FileAttachment("data/sub_areas.json").json();
```

```js
const areaName = new Map([
  ...config.sub_areas.map(a => [a.id, a.name]),
  ...(config.watch_areas || []).map(a => [a.id, a.name])
]);
```

```js
const points = (sold.listings || []).filter(d => d.lat && d.lng && d.ppsf_usd);
```

## Geographic spread

```js
Plot.plot({
  projection: { type: "mercator", domain: { type: "MultiPoint", coordinates: points.map(d => [d.lng, d.lat]) } },
  color: { type: "linear", scheme: "viridis", legend: true, label: "$/sqft" },
  marks: [
    Plot.dot(points, {
      x: "lng",
      y: "lat",
      r: 5,
      fill: "ppsf_usd",
      stroke: "white",
      strokeWidth: 0.4,
      title: d => `${d.address}\n$${d.ppsf_usd}/sqft\n${areaName.get(d.sub_area_id) ?? ""}`
    })
  ],
  height: 600
})
```

## Dispersion ranking

Areas with the highest $/sqft variance are where you should hunt.

```js
const byArea = d3.group(points, d => d.sub_area_id);
const stats = [...byArea].map(([id, list]) => ({
  sub_area: areaName.get(id) ?? id,
  n: list.length,
  median: d3.median(list, d => d.ppsf_usd),
  p25: d3.quantile(list, 0.25, d => d.ppsf_usd),
  p75: d3.quantile(list, 0.75, d => d.ppsf_usd),
  iqr: d3.quantile(list, 0.75, d => d.ppsf_usd) - d3.quantile(list, 0.25, d => d.ppsf_usd)
})).sort((a, b) => (b.iqr || 0) - (a.iqr || 0));
```

```js
Inputs.table(stats.map(s => ({
  Sub_area: s.sub_area,
  N_sold: s.n,
  P25: s.p25 ? `$${Math.round(s.p25)}` : "—",
  Median: s.median ? `$${Math.round(s.median)}` : "—",
  P75: s.p75 ? `$${Math.round(s.p75)}` : "—",
  IQR: s.iqr ? `$${Math.round(s.iqr)}` : "—"
})))
```

## Box plot per area

```js
Plot.plot({
  marginLeft: 180,
  x: { label: "$/sqft", grid: true },
  y: { label: null },
  marks: [
    Plot.boxX(points, { x: "ppsf_usd", y: d => areaName.get(d.sub_area_id) ?? d.sub_area_id, sort: { y: "x", reduce: "median" } })
  ],
  height: 400
})
```
