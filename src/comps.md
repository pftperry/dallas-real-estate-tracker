---
title: Comps explorer
---

```js
import L from "npm:leaflet";
```

# Comps explorer

Recently sold homes filtered to the screen. Use this to sanity-check what your buy box actually buys, anchor on transactions, and spot pricing anomalies.

```js
const sold = await FileAttachment("data/sold.json").json();
const config = await FileAttachment("data/sub_areas.json").json();
```

```js
const areaName = new Map([
  ...config.sub_areas.map(a => [a.id, a.name]),
  ...(config.watch_areas || []).map(a => [a.id, a.name])
]);
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

## Map of filtered comps

```js
const mapDiv = display(html`<div style="height: 480px; border-radius: 4px; border: 1px solid var(--theme-foreground-faintest);"></div>`);
```

```js
{
  const map = L.map(mapDiv, { scrollWheelZoom: true }).setView([32.853, -96.715], 12.3);
  L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
    attribution: '&copy; OpenStreetMap &copy; CARTO',
    maxZoom: 19,
    subdomains: "abcd"
  }).addTo(map);

  // Sub-area overlays
  const allAreas = [...config.sub_areas, ...(config.watch_areas || [])];
  for (const a of allAreas) {
    const bb = a.bbox;
    L.rectangle([[bb.sw_lat, bb.sw_lng], [bb.ne_lat, bb.ne_lng]], {
      color: "#6b7280", weight: 1, opacity: 0.4, fill: false, dashArray: "3,4"
    }).bindTooltip(a.name, { sticky: true }).addTo(map);
  }

  const ppsfValues = filtered.map(d => d.ppsf_usd).filter(Boolean);
  if (ppsfValues.length) {
    const dom = d3.extent(ppsfValues);
    const color = d3.scaleSequential(d3.interpolateRdYlGn).domain([dom[1], dom[0]]);
    for (const d of filtered) {
      if (d.lat == null || d.lng == null) continue;
      const popup = `
        <div style="font-size: 12px; line-height: 1.45">
          <b><a href="${d.url}" target="_blank" rel="noopener">${d.address}</a></b><br>
          Sold ${d.sold_date} for $${(d.price_usd/1000).toFixed(0)}k<br>
          ${d.sqft?.toLocaleString() ?? "—"} sqft &nbsp;·&nbsp; <b>$${d.ppsf_usd ?? "—"}/sqft</b><br>
          ${d.beds ?? "—"} bd / ${d.baths ?? "—"} ba &nbsp;·&nbsp; built ${d.year_built ?? "—"}<br>
          ${areaName.get(d.sub_area_id) ?? ""}
        </div>
      `;
      L.circleMarker([d.lat, d.lng], {
        radius: 6,
        fillColor: d.ppsf_usd ? color(d.ppsf_usd) : "#9ca3af",
        color: "#1f2937",
        weight: 0.5,
        fillOpacity: 0.85
      }).bindPopup(popup).addTo(map);
    }
  }
}
```

> **Key takeaways**
>
> - Color shows $/sqft *within* the current filter set. Red = high $/sqft, green = low. Use the filters above the map to narrow.
> - Marker clusters in your target sub-areas anchor your sense of market price. Click any marker for the Redfin sold page.
> - Dashed gray rectangles = sub-area bounding boxes; reference points only, not pixel-perfect.

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

> **Key takeaways**
>
> - Each dot = one recent sale. The cloud shape reveals the local price-size relationship.
> - Gaps in the cloud are price/size combos the market doesn't trade. If your target falls in a gap, comps will be thin and pricing harder to defend.
> - Sub-area color helps spot which areas trade at higher $/sqft for the same physical size — that's the location premium made visible.

## Comps table

Click any address to open the Redfin listing.

```js
Inputs.table(filtered, {
  columns: [
    "sub_area_id", "address", "sold_date", "price_usd", "ppsf_usd",
    "beds", "baths", "sqft", "lot_size_sqft", "year_built"
  ],
  header: {
    sub_area_id: "Sub-area",
    address: "Address",
    sold_date: "Sold",
    price_usd: "Price",
    ppsf_usd: "$/sqft",
    beds: "Bd",
    baths: "Ba",
    sqft: "Sqft",
    lot_size_sqft: "Lot",
    year_built: "Yr"
  },
  format: {
    sub_area_id: v => areaName.get(v) ?? v ?? "—",
    address: (v, i, data) => {
      const d = data[i];
      return d?.url ? html`<a href="${d.url}" target="_blank" rel="noopener">${v}</a>` : v;
    },
    price_usd: v => v ? `$${(v/1000).toFixed(0)}k` : "—",
    ppsf_usd: v => v ? `$${v}` : "—",
    sqft: v => v?.toLocaleString() ?? "—",
    lot_size_sqft: v => v?.toLocaleString() ?? "—"
  },
  rows: 50
})
```

> **Key takeaways**
>
> - Click any address for the Redfin sold page (full photos, listing history, last sale).
> - Sort by $/sqft to surface anomalies in either direction — both ends of the distribution deserve a closer look.
> - Cross-reference Sold date for recency. A $300/sqft comp from 6 months ago is less anchorable than one from last month, especially in a rate-sensitive market.
