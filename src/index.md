---
title: Watchlist
toc: false
---

```js
import L from "npm:leaflet";
```

# Watchlist

Active listings ranked by buy-fit score. Score weights are tuned for Lakewood-orbit preference (30%), school quality (15%), price fit (20%), $/sqft vs. area (15%), DOM leverage (10%), vintage (5%), lot size (5%).

```js
const watchlist = await FileAttachment("data/watchlist.json").json();
const subAreas = await FileAttachment("data/sub_areas.json").json();
```

```js
const areaName = new Map([
  ...subAreas.sub_areas.map(a => [a.id, a.name]),
  ...(subAreas.watch_areas || []).map(a => [a.id, a.name])
]);
const ppsfColor = d3.scaleLinear()
  .domain([-0.25, 0, 0.25])
  .range(["#16a34a", "#737373", "#dc2626"])
  .clamp(true);
```

<div class="grid grid-cols-4">
  <div class="card"><h2>Active listings</h2><span class="big">${watchlist.n}</span></div>
  <div class="card"><h2>Top score</h2><span class="big">${watchlist.listings?.[0]?._score ?? "—"}</span></div>
  <div class="card"><h2>Buy box</h2><span class="big">$${(watchlist.buy_box?.price_min_usd / 1000) || 800}k–$${(watchlist.buy_box?.price_max_usd / 1000) || 1100}k</span></div>
  <div class="card"><h2>Last refresh</h2><span class="big">${watchlist.as_of?.slice(0, 10) ?? "no data"}</span></div>
</div>

## Top 30 by buy-fit score

Click any address to open the Redfin listing. $/sqft is colored red→gray→green based on percent over/under the sub-area median (hover for the number).

```js
const top = (watchlist.listings || []).slice(0, 30);
```

```js
Inputs.table(top, {
  columns: [
    "_score", "sub_area_id", "address", "price_usd", "ppsf_usd",
    "beds", "baths", "sqft", "lot_size_sqft", "year_built", "days_on_market"
  ],
  header: {
    _score: "Score",
    sub_area_id: "Sub-area",
    address: "Address",
    price_usd: "Price",
    ppsf_usd: "$/sqft",
    beds: "Bd",
    baths: "Ba",
    sqft: "Sqft",
    lot_size_sqft: "Lot",
    year_built: "Yr",
    days_on_market: "DOM"
  },
  format: {
    _score: v => html`<b>${v}</b>`,
    sub_area_id: v => areaName.get(v) ?? v ?? "—",
    address: (v, i, data) => {
      const li = data[i];
      return li?.url
        ? html`<a href="${li.url}" target="_blank" rel="noopener">${v}</a>`
        : v;
    },
    price_usd: v => v ? `$${(v/1000).toFixed(0)}k` : "—",
    ppsf_usd: (v, i, data) => {
      if (!v) return "—";
      const li = data[i];
      const median = watchlist.area_ppsf_medians?.[li.sub_area_id];
      if (!median) return `$${v}`;
      const diff = (v - median) / median;
      const pct = (diff * 100).toFixed(0);
      const sign = diff > 0 ? "+" : "";
      const tip = `${sign}${pct}% vs ${areaName.get(li.sub_area_id) ?? "area"} median ($${median}/sqft)`;
      return html`<span style="color: ${ppsfColor(diff)}; font-weight: 600;" title=${tip}>$${v}</span>`;
    },
    sqft: v => v?.toLocaleString() ?? "—",
    lot_size_sqft: v => v?.toLocaleString() ?? "—"
  },
  rows: 30,
  width: {
    _score: 60,
    sub_area_id: 160,
    address: 220,
    price_usd: 80,
    ppsf_usd: 80,
    beds: 40,
    baths: 40,
    sqft: 80,
    lot_size_sqft: 80,
    year_built: 50,
    days_on_market: 60
  }
})
```

> **Key takeaways**
>
> - All listings shown are at least 2,000 sqft (your buy-box floor).
> - Click any address for the Redfin listing. Sort by Score for best overall fit, or click any column header to re-sort.
> - $/sqft cell color is relative to the sub-area median: green = ≥10% under, gray = at, red = ≥10% over. Hover the value to see the exact percent and the median anchor.

## Map of active listings

Markers are color-graded by buy-fit score (green = best fit). Click for address, price, and a Redfin link.

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

  // Subtle sub-area boundary rectangles
  const allAreas = [...subAreas.sub_areas, ...(subAreas.watch_areas || [])];
  for (const a of allAreas) {
    const bb = a.bbox;
    L.rectangle([[bb.sw_lat, bb.sw_lng], [bb.ne_lat, bb.ne_lng]], {
      color: "#9ca3af", weight: 1, opacity: 0.45, fill: false, dashArray: "3,4"
    }).bindTooltip(a.name, { sticky: true }).addTo(map);
  }

  const scoreColor = d3.scaleLinear()
    .domain([0, 50, 100])
    .range(["#dc2626", "#f59e0b", "#16a34a"])
    .clamp(true);

  for (const li of (watchlist.listings || [])) {
    if (li.lat == null || li.lng == null) continue;
    const popup = `
      <div style="font-size: 12px; line-height: 1.45">
        <b><a href="${li.url}" target="_blank" rel="noopener">${li.address}</a></b><br>
        $${(li.price_usd/1000).toFixed(0)}k &nbsp;·&nbsp; ${li.sqft?.toLocaleString() ?? "—"} sqft &nbsp;·&nbsp; $${li.ppsf_usd ?? "—"}/sqft<br>
        ${li.beds ?? "—"} bd / ${li.baths ?? "—"} ba &nbsp;·&nbsp; built ${li.year_built ?? "—"}<br>
        DOM: ${li.days_on_market ?? "—"} &nbsp;·&nbsp; ${areaName.get(li.sub_area_id) ?? ""}<br>
        <b>Score:</b> ${li._score}
      </div>
    `;
    L.circleMarker([li.lat, li.lng], {
      radius: 6 + (li._score ?? 0) / 25,
      fillColor: scoreColor(li._score ?? 0),
      color: "#fff",
      weight: 1,
      fillOpacity: 0.85
    }).bindPopup(popup).addTo(map);
  }
}
```

> **Key takeaways**
>
> - Marker color and size scale with buy-fit score: green = best fit, red = worst.
> - Heavy clusters of green markers in Tier S sub-areas (Forest Hills, Hollywood Heights, M Streets) are where to focus tours.
> - Isolated green markers in Tier B/C areas are anomalies — investigate why they score so well; sometimes a hidden gem, sometimes a data quirk worth verifying.
> - Dashed gray rectangles are sub-area bounding boxes. Approximate.

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

> **Key takeaways**
>
> - Right-skewed shape (long right tail) = several high-fit options exist this week. Act on those first.
> - Left-skewed or flat = no compelling matches. Wait for new inventory or relax the buy box.
> - Median position tells you whether the screen is rich or poor right now overall.

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
