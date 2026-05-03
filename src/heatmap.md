---
title: Map
---

```js
import L from "npm:leaflet";
```

# Map

Every recently sold home plotted on real streets. Markers color-graded by **$/sqft** (red = high, green = low). Sub-area rectangles are dashed gray overlays — your buy-box pockets.

> Where dispersion is highest = best fishing for mispriced listings. Tight clusters mean the market is "efficient" in that area; wide spread means anomalies live there.

```js
const sold = await FileAttachment("data/sold.json").json();
const config = await FileAttachment("data/sub_areas.json").json();
```

```js
const areaName = new Map([
  ...config.sub_areas.map(a => [a.id, a.name]),
  ...(config.watch_areas || []).map(a => [a.id, a.name])
]);
const points = (sold.listings || []).filter(d => d.lat && d.lng && d.ppsf_usd);
const ppsfDomain = d3.extent(points, d => d.ppsf_usd);
const ppsfColor = d3.scaleSequential(d3.interpolateRdYlGn).domain([ppsfDomain[1], ppsfDomain[0]]);
```

```js
const mapDiv = display(html`<div style="height: 640px; border-radius: 4px; border: 1px solid var(--theme-foreground-faintest);"></div>`);
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
      color: "#6b7280", weight: 1, opacity: 0.5, fill: false, dashArray: "3,4"
    }).bindTooltip(a.name, { sticky: true }).addTo(map);
  }

  for (const d of points) {
    const popup = `
      <div style="font-size: 12px; line-height: 1.45">
        <b><a href="${d.url}" target="_blank" rel="noopener">${d.address}</a></b><br>
        Sold ${d.sold_date}<br>
        $${(d.price_usd/1000).toFixed(0)}k &nbsp;·&nbsp; ${d.sqft?.toLocaleString() ?? "—"} sqft &nbsp;·&nbsp; <b>$${d.ppsf_usd}/sqft</b><br>
        ${d.beds ?? "—"} bd / ${d.baths ?? "—"} ba &nbsp;·&nbsp; built ${d.year_built ?? "—"}<br>
        ${areaName.get(d.sub_area_id) ?? ""}
      </div>
    `;
    L.circleMarker([d.lat, d.lng], {
      radius: 6,
      fillColor: ppsfColor(d.ppsf_usd),
      color: "#1f2937",
      weight: 0.5,
      fillOpacity: 0.85
    }).bindPopup(popup).addTo(map);
  }

  // Color legend in bottom right
  const legend = L.control({ position: "bottomright" });
  legend.onAdd = () => {
    const div = L.DomUtil.create("div", "info legend");
    div.style.background = "rgba(255,255,255,0.92)";
    div.style.padding = "6px 10px";
    div.style.fontSize = "11px";
    div.style.lineHeight = "1.5";
    div.style.borderRadius = "4px";
    div.style.boxShadow = "0 1px 4px rgba(0,0,0,0.15)";
    const grades = [
      Math.round(ppsfDomain[0]),
      Math.round((ppsfDomain[0] + ppsfDomain[1]) / 2),
      Math.round(ppsfDomain[1])
    ];
    div.innerHTML = `
      <b>$/sqft</b><br>
      ${grades.map(v => `<span style="display:inline-block;width:10px;height:10px;background:${ppsfColor(v)};margin-right:4px;border-radius:50%"></span>$${v}`).join("<br>")}
    `;
    return div;
  };
  legend.addTo(map);
}
```

> **Key takeaways**
>
> - Color shows $/sqft: red = high, green = low. Clusters of red surrounded by green = area heating up at the high end.
> - Isolated green markers in an otherwise hot area = potential undervalue. Pull the listing and check condition before assuming it's a deal.
> - Dashed gray rectangles = sub-area bounding boxes for orientation. Approximate.

## Dispersion ranking

Areas with the widest IQR (75th — 25th $/sqft) are where pricing is least efficient — and where you can find anomalies on either side.

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

> **Key takeaways**
>
> - **Highest IQR rows = best fishing ground for mispriced listings.** Wide spread means anomalies in both directions.
> - Lowest IQR = efficient market — list price is close to clearing price, less room to negotiate.
> - The optimal hunting area is high IQR plus your tier preference: pricing dispersion in a sub-area you actually want to live in.
