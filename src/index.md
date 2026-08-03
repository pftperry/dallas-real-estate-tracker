---
title: Watchlist
toc: false
---

```js
import L from "npm:leaflet";
```

# Watchlist

Every listing here has cleared a **hard eligibility gate**: price inside the buy box, 3+ bedrooms, 2+ bathrooms, and either zoned to **Mockingbird or Lakewood Elementary** or sitting inside the **drawn Lake Highlands zone**. Anything failing one of those is excluded outright rather than merely down-ranked. Survivors are then ranked by buy-fit score: Lakewood-orbit 30%, price fit 20%, schools 10%, $/sqft vs. peers 10%, DOM leverage 10%, vintage 10%, lot size 10%. Busy-street listings are flagged ⚠ and lose 5 points.

Zoning is resolved **per address** from the listing's own coordinates against all 135 official Dallas ISD elementary attendance polygons, not from neighborhood feeder labels. Those labels were wrong in several areas.

```js
const watchlist = await FileAttachment("data/watchlist.json").json();
const subAreas = await FileAttachment("data/sub_areas.json").json();
const schoolZones = await FileAttachment("data/school_zones.json").json();
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
const nearMisses = (watchlist.excluded || []).filter(
  x => (x._exclusion_reasons || []).length === 1
    && x._exclusion_reasons[0].startsWith("location_gate")
);
```

<div class="grid grid-cols-4">
  <div class="card"><h2>Eligible</h2><span class="big">${watchlist.n}</span><span style="color: var(--theme-foreground-muted)"> of ${watchlist.n_screened ?? "—"} screened</span></div>
  <div class="card"><h2>Top score</h2><span class="big">${watchlist.listings?.[0]?._score ?? "—"}</span></div>
  <div class="card"><h2>Buy box</h2><span class="big">$${(watchlist.buy_box?.price_min_usd / 1000) || 750}k–$${(watchlist.buy_box?.price_max_usd / 1000) || 1000}k</span><span style="color: var(--theme-foreground-muted)"> · ${watchlist.buy_box?.beds_min ?? 3}bd / ${watchlist.buy_box?.baths_min ?? 2}ba</span></div>
  <div class="card"><h2>Listings scraped</h2><span class="big">${watchlist.listings_as_of?.slice(0, 10) ?? watchlist.as_of?.slice(0, 10) ?? "no data"}</span>${
    watchlist.listings_age_days >= 7
      ? html`<span style="color: #dc2626; font-weight: 600"> · ${watchlist.listings_age_days}d stale</span>`
      : html`<span style="color: var(--theme-foreground-muted)"> · scored ${watchlist.as_of?.slice(0, 10)}</span>`
  }</div>
</div>

## Why listings were excluded

Of the ${watchlist.n} eligible, **${watchlist.eligible_by_basis?.elementary_zone ?? 0} qualify on verified Mockingbird or Lakewood zoning** and **${watchlist.eligible_by_basis?.focus_zone ?? 0} on geography alone** via the drawn Lake Highlands zone. ${watchlist.n_excluded ?? 0} of ${watchlist.n_screened ?? 0} screened listings failed the gate. A listing can fail on more than one count, so these do not sum to the total.

```js
Plot.plot({
  marginLeft: 210,
  x: { label: "Listings excluded" },
  y: { label: null },
  marks: [
    Plot.barX(Object.entries(watchlist.exclusion_reason_counts || {}),
      { y: "0", x: "1", fill: "#dc2626", fillOpacity: 0.75, sort: { y: "x", reverse: true } }),
    Plot.text(Object.entries(watchlist.exclusion_reason_counts || {}),
      { y: "0", x: "1", text: "1", dx: 12, fontWeight: 600 }),
    Plot.ruleX([0])
  ],
  height: 180
})
```

## Eligible listings by buy-fit score

Click any address to open the Redfin listing. **Zone** is the verified elementary attendance zone, or the focus zone the listing falls inside. $/sqft is colored red→gray→green based on percent over/under the **size-normalized peer baseline** (same sub-area, ±25% sqft). ⚠ flags known Dallas arterials.

```js
const top = (watchlist.listings || []).slice(0, 30);
```

```js
Inputs.table(top, {
  columns: [
    "_score", "_busy_street", "_elementary_short", "sub_area_id", "address", "price_usd", "ppsf_usd",
    "beds", "baths", "sqft", "lot_size_sqft", "year_built", "days_on_market"
  ],
  header: {
    _score: "Score",
    _busy_street: "⚠",
    _elementary_short: "Zone",
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
    _elementary_short: (v, i, data) => {
      const li = data[i];
      const edge = li._zone_edge_m;
      // Label by how the listing actually qualified, NOT by whether a DISD zone
      // resolved. A home in the drawn zone can also sit in a non-qualifying DISD
      // zone (Lake Park Estates is Hexter), and showing "Hexter" in green here
      // would imply it passed on schools when it passed on geography.
      const verified = li._eligible_basis === "elementary_zone";
      const label = verified ? v : "LH zone";
      const tip = verified
        ? `Zoned ${li._feeder} (DISD official). ${edge}m from the zone edge.`
        : `Qualifies on geography: inside the drawn ${li._focus_zone} zone. `
          + `${li._elementary ? `Actually zoned ${li._feeder}, which is not on the allowlist.` : "Outside Dallas ISD (RISD)."}`
          + ` ${edge}m from the zone edge.`;
      const warn = li._near_zone_edge ? " ⚑" : "";
      return html`<span title=${tip} style="color: ${verified ? "#16a34a" : "#737373"}; font-weight: 600;">${label}${warn}</span>`;
    },
    _busy_street: (v, i, data) => {
      if (!v) return "";
      const li = data[i];
      const arterial = li._nearest_arterial;
      const dist = li._nearest_arterial_m;
      const onAddr = li._busy_address_on;
      const proximity = li._busy_proximity;
      const reason = onAddr
        ? `On ${arterial ?? "a busy street"}`
        : `Backs up to / near ${arterial} (~${dist}m from centerline)`;
      const tip = `${reason} — likely noise/traffic discount`;
      return html`<span title=${tip} style="color: #dc2626; font-weight: 700;">⚠</span>`;
    },
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
      const baseline = li._ppsf_baseline ?? watchlist.area_ppsf_medians?.[li.sub_area_id];
      if (!baseline) return `$${v}`;
      const diff = (v - baseline) / baseline;
      const pct = (diff * 100).toFixed(0);
      const sign = diff > 0 ? "+" : "";
      const tip = `${sign}${pct}% vs ${li._ppsf_baseline_source || "baseline"} ($${Math.round(baseline)}/sqft)`;
      return html`<span style="color: ${ppsfColor(diff)}; font-weight: 600;" title=${tip}>$${v}</span>`;
    },
    sqft: v => v?.toLocaleString() ?? "—",
    lot_size_sqft: v => v?.toLocaleString() ?? "—"
  },
  rows: 30,
  width: {
    _score: 60,
    _busy_street: 30,
    _elementary_short: 95,
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
> - There is no sqft floor. Beds and baths carry the size requirement, so small-but-qualifying homes now appear.
> - **Zone** in green = verified Mockingbird or Lakewood attendance zone. Gray "LH zone" = qualifies on geography only; it is RISD, so the elementary gate does not apply. Hover for the full feeder pattern.
> - A ⚑ next to the zone means the listing sits within 40m of an attendance boundary. Rooftop coordinates cannot settle which side it is on — confirm on DISD SchoolFinder before touring.
> - $/sqft cell color is relative to the peer baseline: green = ≥10% under, gray = at, red = ≥10% over. Hover for the exact percent and anchor.

## Near misses

These cleared price, bedrooms and bathrooms and failed **only** the location gate, sorted by how close they sit to a qualifying boundary. Worth a look when the eligible list is thin: the closest are a block or two outside the line.

```js
Inputs.table(nearMisses.slice().sort((a, b) => (a._zone_edge_m ?? 1e9) - (b._zone_edge_m ?? 1e9)).slice(0, 15), {
  columns: ["_zone_edge_m", "_nearest_gate_zone", "elementary_short", "sub_area_id", "address", "price_usd", "beds", "baths", "sqft"],
  header: {
    _zone_edge_m: "Metres out",
    _nearest_gate_zone: "Nearest qualifying",
    elementary_short: "Actually zoned",
    sub_area_id: "Sub-area",
    address: "Address",
    price_usd: "Price",
    beds: "Bd",
    baths: "Ba",
    sqft: "Sqft"
  },
  format: {
    _zone_edge_m: v => html`<b>${v?.toLocaleString() ?? "—"}m</b>`,
    sub_area_id: v => areaName.get(v) ?? v ?? "—",
    address: (v, i, data) => {
      const li = data[i];
      return li?.url ? html`<a href="${li.url}" target="_blank" rel="noopener">${v}</a>` : v;
    },
    price_usd: v => v ? `$${(v/1000).toFixed(0)}k` : "—",
    sqft: v => v?.toLocaleString() ?? "—",
    _nearest_gate_zone: v => v ?? "—",
    elementary_short: (v, i, data) => {
      const li = data[i];
      if (!v) return html`<span style="color: var(--theme-foreground-muted)" title="Outside Dallas ISD, so no DISD attendance zone applies">RISD / non-DISD</span>`;
      return html`<span title=${li.feeder ?? v}>${v}</span>`;
    }
  },
  rows: 15,
  width: { _zone_edge_m: 90, _nearest_gate_zone: 130, elementary_short: 120, sub_area_id: 140, address: 200, price_usd: 80, beds: 40, baths: 40, sqft: 80 }
})
```

> **Key takeaways**
>
> - "Metres out" is the distance to the nearest qualifying boundary, so the top of this list is where redrawing the zone or relaxing the school rule would buy you the most inventory.
> - "Nearest qualifying" names the closest qualifying area, so a 65m miss against Mockingbird is a different conversation from a 65m miss against the drawn Lake Highlands zone.
> - "Actually zoned" is the real DISD zone for that address, resolved from all 135 district polygons. Hover for the full feeder pattern. "RISD / non-DISD" means outside Dallas ISD altogether.
> - Read the two zone columns together. A home 100m from Mockingbird that is actually zoned Geneva Heights is a different proposition from one zoned Hexter, even though both fail the same rule.
> - If several strong near misses cluster just outside one edge of the drawn Lake Highlands zone, that edge is probably drawn a block too tight.

## Map of eligible listings

Markers are color-graded by buy-fit score (green = best fit). Click for address, price, and a Redfin link. The **green shaded areas are the two qualifying elementary attendance zones** and the **blue outline is the drawn Lake Highlands zone** — together they are the location gate. Dashed gray rectangles are sub-area bounding boxes, used only for scraping and labeling.

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

  // The qualifying elementary attendance zones -- the school half of the gate.
  // Drawn first so listing markers sit on top.
  L.geoJSON(schoolZones, {
    style: { color: "#16a34a", weight: 2, opacity: 0.8, fillColor: "#16a34a", fillOpacity: 0.1 }
  }).bindTooltip(
    f => `${f.properties.ELEM_DESC} → ${f.properties.MIDDLE} MS → ${f.properties.HIGH} HS (qualifying)`,
    { sticky: true }
  ).addTo(map);

  const allAreas = [...subAreas.sub_areas, ...(subAreas.watch_areas || [])];
  for (const a of allAreas) {
    if (a.polygon) {
      // A traced outline is a real boundary, so draw it solid rather than as
      // the dashed approximation used for bbox rectangles.
      L.polygon(a.polygon.map(([lng, lat]) => [lat, lng]), {
        color: "#2563eb", weight: 2, opacity: 0.9, fillColor: "#2563eb", fillOpacity: 0.08
      }).bindTooltip(`${a.name} (drawn focus zone, qualifying)`, { sticky: true }).addTo(map);
      continue;
    }
    const bb = a.bbox;
    L.rectangle([[bb.sw_lat, bb.sw_lng], [bb.ne_lat, bb.ne_lng]], {
      color: "#9ca3af", weight: 1, opacity: 0.45, fill: false, dashArray: "3,4"
    }).bindTooltip(`${a.name} (scrape area, not a gate)`, { sticky: true }).addTo(map);
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
        ${li._eligible_basis === "elementary_zone"
          ? `Zoned <b>${li._elementary}</b> → ${li._middle} MS → ${li._high} HS`
          : `Inside <b>${li._focus_zone}</b> (geography, RISD)`}<br>
        ${li._near_zone_edge ? `<span style="color:#b45309">⚑ ${li._zone_edge_m}m from zone edge — verify zoning</span><br>` : ""}
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
> - Every marker sits inside a green attendance zone or the blue drawn zone, by construction. A marker that appears to sit outside one is a rendering artifact of the zoom level, not a gate failure.
> - Heavy clusters in Hollywood Heights and M Streets are where to focus tours: those two areas have both qualifying zoning and prices that fit the $750K–$1M band.
> - Dashed gray rectangles are scrape areas only. They do not decide eligibility, and several extend well outside the qualifying zones.

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

## How eligibility works

Hard gate, applied before any scoring. Failing any row excludes the listing.

| Requirement | Rule |
|---|---|
| Price | $750K–$1M |
| Bedrooms | 3 or more |
| Bathrooms | 2 or more |
| Location | Zoned to **Mockingbird** or **Lakewood Elementary**, **or** inside the drawn Lake Highlands zone |

Zoning comes from `config/school_zones.geojson` — all 135 official DISD elementary attendance boundaries for 2026-27 — resolved per listing from its coordinates. It is deliberately **not** taken from the `feeder_pattern` labels in `config/sub_areas.json`. Those labels claimed Forest Hills fed Lakewood Elementary; it is entirely Hexter, verified at four corners and every live listing. Boundaries are redrawn annually, so re-pull each spring with `python -m scrapers.school_zones --refresh`.

The whole district is cached, not just the two qualifying zones, so a rejected listing can be told apart: `wrong_elementary` means it resolved to a real DISD zone that is not on the allowlist, and the near-miss table names it. `outside_disd` means Richardson ISD or beyond.

## How the score works

Applied only to listings that already passed the gate.

| Component | Weight | What it measures |
|---|---:|---|
| Lakewood orbit | 30% | How "Lakewood" the sub-area feels (1.0 = Lakewood-side, 0.3 = deep LH) |
| Price fit | 20% | Full credit mid-band; tapers toward the $750K and $1M edges |
| Schools | 10% | From the **resolved** zone: verified Mockingbird/Lakewood = full credit, drawn-zone-only = 0.9. No longer from the unreliable sub-area score. |
| $/sqft vs. peers | 10% | **Size-normalized**: compares to sold comps in same sub-area within ±25% sqft. Falls back to area median if peer set <3. |
| DOM leverage | 10% | Longer-on-market = more negotiation room |
| Vintage | 10% | Newer build = more turnkey, less maintenance |
| Lot size | 10% | Bigger lots — meaningful in Dallas where lot premiums diverge sharply |
| Busy-street flag | -5pt | Soft penalty for Garland Rd, Buckner, Skillman, Abrams, Mockingbird, NW Hwy, Plano Rd, Walnut Hill, Forest Ln, Greenville Ave, Audelia, Royal Ln |

Because schools are now a gate, the 10% school weight only separates verified DISD zoning from drawn-zone-only qualification. If that distinction stops mattering to you, reallocate the weight in `pipeline/score.py`.

**Why size-normalized $/sqft?** Larger homes price at lower $/sqft as a baseline (fixed costs spread across more sqft). The previous "vs. area median" rule fired on every 4,000 sqft listing in a 2,000-sqft-typical neighborhood, generating false-positive "hidden value" flags. The peer-comp rule now compares apples to apples. Peer baselines are drawn from **all** scraped listings, including ones that fail the gate: a $1.3M neighbor is still a valid comp even though it can never be a buy.

Tweak weights in `pipeline/score.py` and rerun `python -m pipeline.score`.
