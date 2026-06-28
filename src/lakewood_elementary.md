---
title: Lakewood Elementary
toc: false
---

<style>
  .neighborhood-label {
    pointer-events: none;
    background: transparent;
    border: 0;
  }
  .neighborhood-label span {
    display: inline-block;
    transform: translate(-50%, -50%);
    white-space: nowrap;
    font-size: 11px;
    font-weight: 700;
    color: #1f2937;
    letter-spacing: 0.02em;
    text-shadow:
      -1px -1px 0 #fff, 1px -1px 0 #fff,
      -1px  1px 0 #fff, 1px  1px 0 #fff,
       0   -1px 0 #fff, 0    1px 0 #fff,
      -1px  0   0 #fff, 1px  0   0 #fff;
  }
  .school-marker { background: transparent; border: 0; }
  .school-pin {
    width: 32px;
    height: 32px;
    border-radius: 50%;
    background: #facc15;
    border: 2px solid #1f2937;
    box-shadow: 0 1px 4px rgba(0,0,0,0.35);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 16px;
    line-height: 1;
    cursor: pointer;
  }
</style>

```js
import L from "npm:leaflet";
```

# Lakewood Elementary feeder

Active listings and recent sold comps restricted to sub-areas that feed **Lakewood Elementary** (DISD's strongest elementary, paired with J.L. Long MS and Woodrow Wilson HS). Seven sub-areas qualify: Forest Hills, Hollywood Heights / Santa Monica, Lakewood proper, Lakewood Hills, Hillside, Lakewood Heights *(partial)*, and Junius Heights / Peak's Suburban / Munger Place *(partial)* — verify per address on the DISD school locator for the partial feeders.

```js
const watchlist = await FileAttachment("data/watchlist.json").json();
const sold = await FileAttachment("data/sold.json").json();
const subAreas = await FileAttachment("data/sub_areas.json").json();
```

```js
// Sub-areas whose feeder_pattern includes "Lakewood Elementary"
const LAKEWOOD_ELEM_IDS = new Set(
  subAreas.sub_areas
    .filter(a => (a.feeder_pattern || "").includes("Lakewood Elementary"))
    .map(a => a.id)
);
const LAKEWOOD_ELEM_AREAS = subAreas.sub_areas.filter(a => LAKEWOOD_ELEM_IDS.has(a.id));
const areaName = new Map(LAKEWOOD_ELEM_AREAS.map(a => [a.id, a.name]));

const activeAll = (watchlist.listings || []).filter(d => LAKEWOOD_ELEM_IDS.has(d.sub_area_id));
const soldAll = (sold.listings || []).filter(d => LAKEWOOD_ELEM_IDS.has(d.sub_area_id));

// Parse Redfin "Month-DD-YYYY" sold_date into a real Date
function parseSoldDate(s) {
  if (!s) return null;
  const m = String(s).match(/^([A-Za-z]+)-(\d{1,2})-(\d{4})$/);
  if (!m) return null;
  const months = {January:0,February:1,March:2,April:3,May:4,June:5,July:6,August:7,September:8,October:9,November:10,December:11};
  const mo = months[m[1]];
  if (mo == null) return null;
  return new Date(Date.UTC(+m[3], mo, +m[2]));
}
const soldDated = soldAll
  .map(d => ({...d, _date: parseSoldDate(d.sold_date)}))
  .filter(d => d._date);

// Color scales — match the Watchlist tab.
// $/sqft: green when % below baseline, red when % above (-25% .. +25%).
const ppsfColor = d3.scaleLinear()
  .domain([-0.25, 0, 0.25])
  .range(["#16a34a", "#737373", "#dc2626"])
  .clamp(true);
// DOM: longer-on-market = more buyer leverage = green; freshly listed = red.
// 0d red -> ~30d gray -> 60d+ green.
const domColor = d3.scaleLinear()
  .domain([0, 30, 60])
  .range(["#dc2626", "#737373", "#16a34a"])
  .clamp(true);
```

<div class="grid grid-cols-4">
  <div class="card"><h2>Active listings</h2><span class="big">${activeAll.length}</span></div>
  <div class="card"><h2>Median list price</h2><span class="big">$${activeAll.length ? Math.round(d3.median(activeAll, d => d.price_usd)/1000) : "—"}k</span></div>
  <div class="card"><h2>Sold (recent)</h2><span class="big">${soldAll.length}</span></div>
  <div class="card"><h2>Median sold $/sqft</h2><span class="big">$${soldAll.length ? Math.round(d3.median(soldAll.filter(d => d.ppsf_usd), d => d.ppsf_usd)) : "—"}</span></div>
</div>

## Price trend — sold $/sqft by month

```js
{
  // Bin sold homes by year-month and compute median $/sqft + median price
  const byMonth = d3.rollups(
    soldDated.filter(d => d.ppsf_usd),
    v => ({
      n: v.length,
      median_ppsf: d3.median(v, d => d.ppsf_usd),
      median_price: d3.median(v, d => d.price_usd),
    }),
    d => `${d._date.getUTCFullYear()}-${String(d._date.getUTCMonth()+1).padStart(2,"0")}`
  )
  .map(([month, stats]) => ({month, ...stats}))
  .sort((a, b) => d3.ascending(a.month, b.month));

  display(html`<div style="font-size: 12px; color: var(--theme-foreground-muted); margin-bottom: 6px;">
    ${byMonth.length} month(s) of data · marker size scales with sample count
  </div>`);

  display(Plot.plot({
    height: 260,
    marginLeft: 60,
    x: { label: "Sale month", type: "band" },
    y: { label: "Median $/sqft", grid: true, tickFormat: d => "$" + d },
    marks: [
      Plot.ruleY([0], { stroke: "transparent" }),
      Plot.line(byMonth, { x: "month", y: "median_ppsf", stroke: "#16a34a", strokeWidth: 2, curve: "monotone-x" }),
      Plot.dot(byMonth, {
        x: "month",
        y: "median_ppsf",
        r: d => Math.max(4, Math.min(14, Math.sqrt(d.n) * 2.5)),
        fill: "#16a34a",
        stroke: "white",
        title: d => `${d.month}\nMedian $/sqft: $${Math.round(d.median_ppsf)}\nMedian price: $${(d.median_price/1000).toFixed(0)}k\nN: ${d.n}`
      }),
      Plot.text(byMonth, {
        x: "month",
        y: "median_ppsf",
        text: d => `$${Math.round(d.median_ppsf)}`,
        dy: -14,
        fontWeight: 600,
        fontSize: 11
      })
    ]
  }));
}
```

> **How to read it.** Each dot is one month of sold comps in the Lakewood Elementary feeder zone. Dot size = sample count (bigger = more confident). Thin months are noisy — don't read a single low-volume tick as a trend. Recent direction matters more than absolute level.

## Heat map — recent sold $/sqft

```js
const mapDiv = display(html`<div style="height: 520px; border-radius: 4px; border: 1px solid var(--theme-foreground-faintest);"></div>`);
```

```js
{
  const points = soldAll.filter(d => d.lat && d.lng && d.ppsf_usd);
  // Use a percentile-clipped domain so a single outlier doesn't wash out the color scale
  const sortedPpsf = points.map(d => d.ppsf_usd).sort(d3.ascending);
  const lo = d3.quantile(sortedPpsf, 0.05) ?? sortedPpsf[0];
  const hi = d3.quantile(sortedPpsf, 0.95) ?? sortedPpsf[sortedPpsf.length - 1];
  const ppsfColor = d3.scaleSequential(d3.interpolateRdYlGn).domain([hi, lo]);

  // Center on Lakewood-area centroid; zoom in tighter than the global map
  const lats = points.map(d => d.lat), lngs = points.map(d => d.lng);
  const centerLat = lats.length ? d3.mean(lats) : 32.832;
  const centerLng = lngs.length ? d3.mean(lngs) : -96.745;
  const map = L.map(mapDiv, { scrollWheelZoom: true }).setView([centerLat, centerLng], 13.5);
  L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
    attribution: '&copy; OpenStreetMap &copy; CARTO',
    maxZoom: 19,
    subdomains: "abcd"
  }).addTo(map);

  // Sub-area outlines + permanent name labels for context
  for (const a of LAKEWOOD_ELEM_AREAS) {
    const bb = a.bbox;
    L.rectangle([[bb.sw_lat, bb.sw_lng], [bb.ne_lat, bb.ne_lng]], {
      color: "#6b7280", weight: 1, opacity: 0.55, fill: false, dashArray: "3,4"
    }).addTo(map);

    const labelLat = (bb.sw_lat + bb.ne_lat) / 2;
    const labelLng = (bb.sw_lng + bb.ne_lng) / 2;
    L.marker([labelLat, labelLng], {
      interactive: false,
      keyboard: false,
      icon: L.divIcon({
        className: "neighborhood-label",
        html: `<span>${a.name}</span>`,
        iconSize: null
      })
    }).addTo(map);
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
      radius: 7,
      fillColor: ppsfColor(d.ppsf_usd),
      color: "#1f2937",
      weight: 0.6,
      fillOpacity: 0.88
    }).bindPopup(popup).addTo(map);
  }

  // Lakewood Elementary School marker (3000 Hillbrook St, Dallas, TX 75214)
  const SCHOOL = { lat: 32.81965, lng: -96.74842, name: "Lakewood Elementary", addr: "3000 Hillbrook St" };
  L.marker([SCHOOL.lat, SCHOOL.lng], {
    icon: L.divIcon({
      className: "school-marker",
      html: `<div class="school-pin" title="${SCHOOL.name}">🏫</div>`,
      iconSize: [32, 32],
      iconAnchor: [16, 16]
    }),
    zIndexOffset: 1000
  })
    .bindPopup(`<b>${SCHOOL.name}</b><br>${SCHOOL.addr}<br><i style="color:#6b7280">DISD K-5 · feeder anchor</i>`)
    .addTo(map);

  const legend = L.control({ position: "bottomright" });
  legend.onAdd = () => {
    const div = L.DomUtil.create("div", "info legend");
    div.style.background = "rgba(255,255,255,0.92)";
    div.style.padding = "6px 10px";
    div.style.fontSize = "11px";
    div.style.lineHeight = "1.5";
    div.style.borderRadius = "4px";
    div.style.boxShadow = "0 1px 4px rgba(0,0,0,0.15)";
    const grades = [Math.round(lo), Math.round((lo + hi) / 2), Math.round(hi)];
    div.innerHTML = `
      <b>$/sqft (5–95%)</b><br>
      ${grades.map(v => `<span style="display:inline-block;width:10px;height:10px;background:${ppsfColor(v)};margin-right:4px;border-radius:50%"></span>$${v}`).join("<br>")}
      <hr style="margin:5px 0; border:0; border-top:1px solid #e5e7eb;">
      <span style="display:inline-block;width:14px;height:14px;background:#facc15;border:1.5px solid #1f2937;border-radius:50%;vertical-align:middle;text-align:center;font-size:9px;line-height:11px;margin-right:4px">🏫</span>Lakewood Elem
    `;
    return div;
  };
  legend.addTo(map);
}
```

> **How to read it.** Color = $/sqft of the most recent sold comps. Green = relatively cheap on a $/sqft basis, red = expensive. The scale is clipped to the 5th–95th percentile so a single outlier doesn't wash out the gradient. Tight clusters of green next to red = micro-arbitrage between adjacent streets — worth a closer look.

## Sub-area rollup (Lakewood Elementary only)

```js
{
  const feederPpsfs = soldAll.map(d => d.ppsf_usd).filter(Boolean);
  const feederMedianPpsf = feederPpsfs.length ? d3.median(feederPpsfs) : null;

  const rows = LAKEWOOD_ELEM_AREAS.map(a => {
    const soldHere = soldAll.filter(d => d.sub_area_id === a.id && d.ppsf_usd);
    const activeHere = activeAll.filter(d => d.sub_area_id === a.id);
    return {
      sub_area: a.name,
      tier: a.tier,
      n_sold: soldHere.length,
      median_sold_price: soldHere.length ? Math.round(d3.median(soldHere, d => d.price_usd)) : null,
      median_ppsf: soldHere.length ? Math.round(d3.median(soldHere, d => d.ppsf_usd)) : null,
      n_active: activeHere.length,
      median_active_price: activeHere.length ? Math.round(d3.median(activeHere, d => d.price_usd)) : null,
    };
  }).sort((a, b) => d3.descending(a.n_sold, b.n_sold));

  display(Inputs.table(rows, {
    columns: ["sub_area", "tier", "n_sold", "median_sold_price", "median_ppsf", "n_active", "median_active_price"],
    header: {
      sub_area: "Sub-area",
      tier: "Tier",
      n_sold: "Sold (n)",
      median_sold_price: "Median sold",
      median_ppsf: "$/sqft",
      n_active: "Active (n)",
      median_active_price: "Median active"
    },
    format: {
      median_sold_price: v => v ? `$${(v/1000).toFixed(0)}k` : "—",
      median_active_price: v => v ? `$${(v/1000).toFixed(0)}k` : "—",
      median_ppsf: v => {
        if (!v) return "—";
        if (!feederMedianPpsf) return `$${v}`;
        const diff = (v - feederMedianPpsf) / feederMedianPpsf;
        const pct = (diff * 100).toFixed(0);
        const sign = diff > 0 ? "+" : "";
        const tip = `${sign}${pct}% vs Lakewood feeder median ($${Math.round(feederMedianPpsf)}/sqft)`;
        return html`<span style="color: ${ppsfColor(diff)}; font-weight: 600;" title=${tip}>$${v}</span>`;
      }
    },
    rows: 20,
    width: { sub_area: 220, tier: 50 }
  }));
}
```

## Active listing map

```js
const activeMapDiv = display(html`<div style="height: 520px; border-radius: 4px; border: 1px solid var(--theme-foreground-faintest);"></div>`);
```

```js
{
  const points = activeAll.filter(d => d.lat && d.lng);
  if (points.length === 0) {
    activeMapDiv.innerHTML = `<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--theme-foreground-muted);font-style:italic">No active listings in the Lakewood Elementary feeder zone right now.</div>`;
  } else {
    // Color by absolute $/sqft (matches the sold heat map's logic).
    // With small N (<20), use raw min/max; with more data, clip to 5–95%.
    const pricedPoints = points.filter(d => d.ppsf_usd);
    const sortedPpsf = pricedPoints.map(d => d.ppsf_usd).sort(d3.ascending);
    const clip = sortedPpsf.length >= 20;
    const lo = clip ? d3.quantile(sortedPpsf, 0.05) : sortedPpsf[0];
    const hi = clip ? d3.quantile(sortedPpsf, 0.95) : sortedPpsf[sortedPpsf.length - 1];
    const activePpsfColor = d3.scaleSequential(d3.interpolateRdYlGn).domain([hi, lo]);

    const lats = points.map(d => d.lat), lngs = points.map(d => d.lng);
    const centerLat = d3.mean(lats), centerLng = d3.mean(lngs);
    const map = L.map(activeMapDiv, { scrollWheelZoom: true }).setView([centerLat, centerLng], 13.5);
    L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
      attribution: '&copy; OpenStreetMap &copy; CARTO',
      maxZoom: 19,
      subdomains: "abcd"
    }).addTo(map);

    // Sub-area outlines + labels (same overlays as the sold map)
    for (const a of LAKEWOOD_ELEM_AREAS) {
      const bb = a.bbox;
      L.rectangle([[bb.sw_lat, bb.sw_lng], [bb.ne_lat, bb.ne_lng]], {
        color: "#6b7280", weight: 1, opacity: 0.55, fill: false, dashArray: "3,4"
      }).addTo(map);
      const labelLat = (bb.sw_lat + bb.ne_lat) / 2;
      const labelLng = (bb.sw_lng + bb.ne_lng) / 2;
      L.marker([labelLat, labelLng], {
        interactive: false, keyboard: false,
        icon: L.divIcon({ className: "neighborhood-label", html: `<span>${a.name}</span>`, iconSize: null })
      }).addTo(map);
    }

    for (const d of points) {
      const score = d._score ?? 0;
      const radius = 7 + score / 20; // larger dot = higher buy-fit score
      const fill = d.ppsf_usd ? activePpsfColor(d.ppsf_usd) : "#9ca3af";
      const busy = d._busy_street
        ? `<span title="On or near ${d._nearest_arterial ?? "a busy street"}" style="color:#dc2626">⚠ busy street</span><br>`
        : "";
      const popup = `
        <div style="font-size: 12px; line-height: 1.45">
          <b><a href="${d.url}" target="_blank" rel="noopener">${d.address}</a></b><br>
          <b>Score:</b> ${score} &nbsp;·&nbsp; DOM: ${d.days_on_market ?? "—"}<br>
          ${busy}
          $${(d.price_usd/1000).toFixed(0)}k &nbsp;·&nbsp; ${d.sqft?.toLocaleString() ?? "—"} sqft &nbsp;·&nbsp; <b>$${d.ppsf_usd ?? "—"}/sqft</b><br>
          ${d.beds ?? "—"} bd / ${d.baths ?? "—"} ba &nbsp;·&nbsp; built ${d.year_built ?? "—"}<br>
          ${areaName.get(d.sub_area_id) ?? ""}
        </div>
      `;
      L.circleMarker([d.lat, d.lng], {
        radius,
        fillColor: fill,
        color: "#1f2937",
        weight: 0.8,
        fillOpacity: 0.9
      }).bindPopup(popup).addTo(map);
    }

    // School marker (same as sold map)
    const SCHOOL = { lat: 32.81965, lng: -96.74842, name: "Lakewood Elementary", addr: "3000 Hillbrook St" };
    L.marker([SCHOOL.lat, SCHOOL.lng], {
      icon: L.divIcon({
        className: "school-marker",
        html: `<div class="school-pin" title="${SCHOOL.name}">🏫</div>`,
        iconSize: [32, 32], iconAnchor: [16, 16]
      }),
      zIndexOffset: 1000
    }).bindPopup(`<b>${SCHOOL.name}</b><br>${SCHOOL.addr}<br><i style="color:#6b7280">DISD K-5 · feeder anchor</i>`).addTo(map);

    // Legend
    const legend = L.control({ position: "bottomright" });
    legend.onAdd = () => {
      const div = L.DomUtil.create("div", "info legend");
      div.style.background = "rgba(255,255,255,0.92)";
      div.style.padding = "6px 10px";
      div.style.fontSize = "11px";
      div.style.lineHeight = "1.5";
      div.style.borderRadius = "4px";
      div.style.boxShadow = "0 1px 4px rgba(0,0,0,0.15)";
      const grades = pricedPoints.length
        ? [Math.round(lo), Math.round((lo + hi) / 2), Math.round(hi)]
        : [];
      const scaleHtml = grades.length
        ? `<b>$/sqft${clip ? " (5–95%)" : ""}</b><br>` +
          grades.map(v => `<span style="display:inline-block;width:10px;height:10px;background:${activePpsfColor(v)};margin-right:4px;border-radius:50%"></span>$${v}`).join("<br>")
        : "";
      div.innerHTML = `
        ${scaleHtml}
        <hr style="margin:5px 0; border:0; border-top:1px solid #e5e7eb;">
        <b>Marker size</b><br>
        <span style="display:inline-block;width:6px;height:6px;background:#6b7280;border-radius:50%;margin-right:4px"></span>low score<br>
        <span style="display:inline-block;width:14px;height:14px;background:#6b7280;border-radius:50%;margin-right:4px;vertical-align:middle"></span>high score
        <hr style="margin:5px 0; border:0; border-top:1px solid #e5e7eb;">
        <span style="display:inline-block;width:14px;height:14px;background:#facc15;border:1.5px solid #1f2937;border-radius:50%;vertical-align:middle;text-align:center;font-size:9px;line-height:11px;margin-right:4px">🏫</span>Lakewood Elem
      `;
      return div;
    };
    legend.addTo(map);
  }
}
```

> **How to read it.** Marker color = absolute $/sqft (same scale as the sold heat map below — red is pricey, green is cheap). Marker size scales with the buy-fit score from the Watchlist, so high-fit listings visually pop. Click any dot for full details and a Redfin link. The 🏫 pin marks Lakewood Elementary itself.

## Active listings — Lakewood Elementary feeder

```js
{
  const rows = activeAll.slice().sort((a, b) => (b._score ?? 0) - (a._score ?? 0));
  if (rows.length === 0) {
    display(html`<p><i>No active listings in the Lakewood Elementary feeder zone matching the current buy box.</i></p>`);
  } else {
    display(Inputs.table(rows, {
      columns: ["_score", "sub_area_id", "address", "price_usd", "ppsf_usd", "beds", "baths", "sqft", "year_built", "days_on_market"],
      header: {
        _score: "Score",
        sub_area_id: "Sub-area",
        address: "Address",
        price_usd: "Price",
        ppsf_usd: "$/sqft",
        beds: "Bd",
        baths: "Ba",
        sqft: "Sqft",
        year_built: "Yr",
        days_on_market: "DOM"
      },
      format: {
        _score: v => html`<b>${v}</b>`,
        sub_area_id: v => areaName.get(v) ?? v ?? "—",
        address: (v, i, data) => {
          const li = data[i];
          return li?.url ? html`<a href="${li.url}" target="_blank" rel="noopener">${v}</a>` : v;
        },
        price_usd: v => v ? `$${(v/1000).toFixed(0)}k` : "—",
        ppsf_usd: (v, i, data) => {
          if (!v) return "—";
          const li = data[i];
          const baseline = li._ppsf_baseline ?? watchlist.area_ppsf_medians?.[li.sub_area_id];
          if (!baseline) return `$${v}`;
          const diff = (v - baseline) / baseline;
          const pct = (diff * 100).toFixed(0);
          const sign = diff > 0 ? "+" : "";
          const tip = `${sign}${pct}% vs ${li._ppsf_baseline_source || "baseline"} ($${Math.round(baseline)}/sqft)`;
          return html`<span style="color: ${ppsfColor(diff)}; font-weight: 600;" title=${tip}>$${v}</span>`;
        },
        sqft: v => v?.toLocaleString() ?? "—",
        days_on_market: v => {
          if (v == null) return "—";
          const tip = v >= 60 ? "Stale — buyer leverage"
            : v >= 30 ? "Moderate DOM"
            : "Fresh listing — limited leverage";
          return html`<span style="color: ${domColor(v)}; font-weight: 600;" title=${tip}>${v}</span>`;
        }
      },
      rows: 30,
      width: { _score: 60, sub_area_id: 160, address: 220, price_usd: 80, ppsf_usd: 70, sqft: 70 }
    }));
  }
}
```

> **Caveats.**
>
> - Lakewood Heights is a *partial* Lakewood Elementary feeder — some addresses zone to Mockingbird Elementary instead. Verify per address on the DISD school locator before bidding.
> - Sample sizes are thin month-to-month. Treat the trend line as direction, not magnitude — wait for two or three confirming months before sizing up on a perceived dip.
> - Sold data is filtered upstream to $600K–$1.3M, so the medians here reflect that price band, not the entire neighborhood.
