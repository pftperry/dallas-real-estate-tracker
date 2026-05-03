---
title: Comps explorer
---

# Comps explorer

Recently sold homes filtered to the screen. Use this to sanity-check what your buy-box actually buys.

```js
const sold = await FileAttachment("../data/sold/latest_redfin.json").json().catch(() => ({listings: []}));
const config = await FileAttachment("../config/sub_areas.json").json();
```

```js
const areaName = new Map([
  ...config.sub_areas.map(a => [a.id, a.name]),
  ...(config.watch_areas || []).map(a => [a.id, a.name])
]);
```

```js
const all = sold.listings || [];
```

```js
const subAreaInput = Inputs.checkbox(
  [...new Set(all.map(d => d.sub_area_id).filter(Boolean))].sort(),
  { label: "Sub-area", value: [...new Set(all.map(d => d.sub_area_id).filter(Boolean))], format: id => areaName.get(id) ?? id }
);
const subAreaSel = view(subAreaInput);
```

```js
const priceMinInput = Inputs.number({ label: "Min price ($)", value: 600000, step: 25000 });
const priceMaxInput = Inputs.number({ label: "Max price ($)", value: 1300000, step: 25000 });
const priceMin = view(priceMinInput);
const priceMax = view(priceMaxInput);
```

```js
const filtered = all.filter(d =>
  subAreaSel.includes(d.sub_area_id)
  && (d.price_usd ?? 0) >= priceMin
  && (d.price_usd ?? 0) <= priceMax
);
```

<div class="grid grid-cols-3">
  <div class="card"><h2>Filtered comps</h2><span class="big">${filtered.length}</span></div>
  <div class="card"><h2>Median price</h2><span class="big">$${filtered.length ? (d3.median(filtered, d => d.price_usd) / 1000).toFixed(0) + "k" : "—"}</span></div>
  <div class="card"><h2>Median $/sqft</h2><span class="big">$${filtered.length ? Math.round(d3.median(filtered.filter(d => d.ppsf_usd), d => d.ppsf_usd) || 0) : "—"}</span></div>
</div>

## Price vs. sqft

```js
Plot.plot({
  x: { label: "Square feet", grid: true },
  y: { label: "Sale price", grid: true, tickFormat: d => "$" + (d/1000).toFixed(0) + "k" },
  color: { legend: true },
  marks: [
    Plot.dot(filtered, {
      x: "sqft",
      y: "price_usd",
      stroke: d => areaName.get(d.sub_area_id) ?? d.sub_area_id,
      r: 4,
      title: d => `${d.address}\n$${(d.price_usd/1000).toFixed(0)}k @ $${d.ppsf_usd}/sqft\n${d.sqft} sqft, ${d.year_built}\n${areaName.get(d.sub_area_id) ?? ""}`
    })
  ],
  height: 380
})
```

## Comps table

```js
Inputs.table(filtered.map(d => ({
  Sub_area: areaName.get(d.sub_area_id) ?? d.sub_area_id,
  Address: d.address,
  Sold: d.sold_date,
  Price: d.price_usd ? `$${(d.price_usd/1000).toFixed(0)}k` : "—",
  PPSF: d.ppsf_usd ? `$${d.ppsf_usd}` : "—",
  Beds: d.beds,
  Baths: d.baths,
  Sqft: d.sqft?.toLocaleString(),
  Lot: d.lot_size_sqft?.toLocaleString(),
  Year: d.year_built,
  Link: html`<a href="${d.url}" target="_blank">view</a>`
})), { rows: 50 })
```
