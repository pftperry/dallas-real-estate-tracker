---
title: Watchlist
toc: false
---

```js
import L from "npm:leaflet";
```

# Watchlist

Every listing here has cleared a **hard eligibility gate**: price inside the buy box, 3+ bedrooms, 2+ bathrooms, and either zoned to **Mockingbird or Lakewood Elementary** or sitting inside one of two **Lake Highlands geographic zones** (the drawn L Streets outline, or Lake Highlands Estates). Anything failing one of those is excluded outright rather than merely down-ranked.

Survivors are ranked on **the house, not the neighborhood** — location is already settled by the gate, and all three qualifying bases count equally. The score answers one question: *is this a character home on a real lot, at a fair price?* Weights: lot size 30%, period character 25%, $/sqft vs. peers 20%, baths per bedroom 10%, size 10%, price position 5%.

**Deal signals are kept out of the score** and shown beside it: days on market, busy-street exposure ⚠, and zone-edge proximity ⚑. Those tell you how to *approach* a house, not whether it's a good one.

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
    && /^(location_gate|wrong_elementary|outside_disd|location_unverifiable)/.test(x._exclusion_reasons[0])
);

// Compact labels for the geographic zones. More than one qualifies now, so a bare
// "LH zone" would not say which.
const focusZoneLabel = new Map([
  ["l_streets", "L Streets"],
  ["lake_highlands_estates", "LH Estates"]
]);
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

Of the ${watchlist.n} eligible, **${watchlist.eligible_by_basis?.elementary_zone ?? 0} qualify on verified Mockingbird or Lakewood zoning** and **${watchlist.eligible_by_basis?.focus_zone ?? 0} on geography alone** via the Lake Highlands zones. ${watchlist.n_excluded ?? 0} of ${watchlist.n_screened ?? 0} screened listings failed the gate. A listing can fail on more than one count, so these do not sum to the total.

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
      const label = verified ? v : (focusZoneLabel.get(li._focus_zone) ?? li._focus_zone ?? "—");
      const tip = verified
        ? `Zoned ${li._feeder} (DISD official). ${edge}m from the zone edge.`
        : `Qualifies on geography: inside the ${li._focus_zone} zone. `
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
    lot_size_sqft: (v, i, data) => {
      if (!v) return "—";
      // Lot drives 30% of the score, so make the good ones visible at a glance.
      const color = v >= 9000 ? "#16a34a" : v >= 6000 ? "#737373" : "#b45309";
      const tip = v >= 9000 ? "Generous lot for this market (top quartile)"
        : v >= 6000 ? "Typical lot" : "Small lot — often a subdivided spec build";
      return html`<span style="color: ${color}; font-weight: 600;" title=${tip}>${v.toLocaleString()}</span>`;
    },
    days_on_market: (v, i, data) => {
      const f = data[i]._dom_flag;
      // Deal signal, deliberately NOT part of the score. Long DOM used to be
      // rewarded, which put a 114-day listing at #1; it is context for how to
      // approach the house, not evidence the house is good.
      const style = { fresh: ["#dc2626", "move fast, expect competition"],
                      normal: ["#737373", "unremarkable time on market"],
                      slow: ["#b45309", "some negotiating room"],
                      stale: ["#7c3aed", "find out WHY before assuming a bargain"],
                      unknown: ["#737373", "no DOM reported"] }[f] ?? ["#737373", ""];
      return html`<span style="color: ${style[0]}; font-weight: 600;" title=${style[1]}>${v ?? "—"}${f === "stale" ? " ⚑" : ""}</span>`;
    }
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
> - **The score ranks the house, not the location.** All three qualifying bases count equally, so a Lake Highlands home is not docked for being in Lake Highlands. Rank differences come from lot, character, price per foot and layout.
> - **Lot** is 30% of the score and color-coded: green ≥9,000 sqft, amber <6,000 (usually a subdivided spec build). **Yr** matters almost as much — pre-1945 scores highest, 1966–90 lowest.
> - **DOM is not scored.** Red = fresh, so expect competition. Purple ⚑ = 90+ days: in a market turning in 24, that usually means something is wrong with the house, so find out what before treating it as a bargain.
> - There is no sqft floor. Beds and baths carry the size requirement, so small-but-qualifying homes appear.
> - **Zone** in green = verified Mockingbird or Lakewood attendance zone. Gray "L Streets" or "LH Estates" = qualifies on geography; both are RISD, so the elementary gate does not apply. A ⚑ there means within 40m of an attendance boundary — confirm on DISD SchoolFinder before touring.
> - $/sqft color is relative to the size-matched peer baseline: green = ≥10% under, red = ≥10% over. Hover for the exact percent and anchor.

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
> - If several strong near misses cluster just outside one edge of a Lake Highlands zone, that edge is probably drawn a block too tight.

## Map of eligible listings

Markers are color-graded by buy-fit score (green = best fit). Click for address, price, and a Redfin link. The **green shaded areas are the two qualifying elementary attendance zones** and the **blue outlines are the two Lake Highlands geographic zones** — together they are the location gate. Dashed gray rectangles are sub-area bounding boxes, used only for scraping and labeling.

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
| Location | Zoned to **Mockingbird** or **Lakewood Elementary**, **or** inside a Lake Highlands geographic zone (L Streets outline, or Lake Highlands Estates) |

Zoning comes from `config/school_zones.geojson` — all 135 official DISD elementary attendance boundaries for 2026-27 — resolved per listing from its coordinates. It is deliberately **not** taken from the `feeder_pattern` labels in `config/sub_areas.json`. Those labels claimed Forest Hills fed Lakewood Elementary; it is entirely Hexter, verified at four corners and every live listing. Boundaries are redrawn annually, so re-pull each spring with `python -m scrapers.school_zones --refresh`.

The whole district is cached, not just the two qualifying zones, so a rejected listing can be told apart: `wrong_elementary` means it resolved to a real DISD zone that is not on the allowlist, and the near-miss table names it. `outside_disd` means Richardson ISD or beyond.

## How the score works

Applied only to listings that already passed the gate.

| Component | Weight | What it measures |
|---|---:|---|
| Lot size | 30% | Land. Calibrated to this market: 4,000 sqft (a subdivided spec lot) scores zero, 12,000 scores full. Median here is 8,364. |
| Period character | 25% | Pre-1945 Tudor/Craftsman/Prairie = full credit. 1946–65 mid-century ranch = 0.75, and that's 45% of this market. 1966–90 = 0.25, the weakest era locally. 1991+ = 0.45: turnkey, but not what this screen is shopping for. |
| $/sqft vs. peers | 20% | **Size-normalized**: sold comps in the same sub-area within ±25% sqft. Full credit at 25% under peers, neutral on baseline, zero at 25% over. Falls back to area median if peer set <3. |
| Baths per bedroom | 10% | Livability. Runs 0.50 to 1.17 across the current set. Small on purpose — a two-bath character home should still beat a four-bath spec box. |
| Size | 10% | Raw square footage, 1,500 → 3,500. Secondary by choice: the bigger houses here are mostly new builds on small lots. |
| Price position | 5% | Full credit mid-band, tapering toward the $750K and $1M edges. Near-constant, since the gate already enforces the band. |
| Busy-street flag | -5pt | Soft penalty for Garland Rd, Buckner, Skillman, Abrams, Mockingbird, NW Hwy, Plano Rd, Walnut Hill, Forest Ln, Greenville Ave, Audelia, Royal Ln |

**What this score deliberately ignores.** Two things used to dominate it and both were misleading:

- **Days on market** was the strongest single correlate (r = +0.54), so a listing that had sat 114 days in a market turning in 24 ranked first. Staleness was reading as quality. It's now a flag in the DOM column: red = fresh, purple ⚑ = 90+ days, meaning find out *why* before assuming a bargain.
- **Lakewood-orbit** carried 30% and supplied 36% of all discriminating power. Once the gate decided location, scoring it again charged the same preference twice: it buried the drawn Lake Highlands zone in the bottom four ranks by construction and docked Junius Heights 13.5 points for feeder uncertainty the gate now resolves outright. It's still reported per listing as context but no longer moves the number.
- **School zoning** is gone from the score too. The gate guarantees it, so ranking it again only penalized Lake Highlands homes for qualifying on geography rather than on a DISD boundary.

The old set also never scored square footage at all, and its `lot_size` correlated **negatively** with the score despite carrying 20% weight. After this revision: DOM correlation +0.09 (neutral), lot +0.41, year built −0.60 (older = better). One honest side effect — because the character stock here sits on bigger lots but is smaller, square footage now correlates mildly negative (−0.26). That's the trade this weighting makes on purpose.

**Why size-normalized $/sqft?** Larger homes price at lower $/sqft as a baseline (fixed costs spread across more sqft). The previous "vs. area median" rule fired on every 4,000 sqft listing in a 2,000-sqft-typical neighborhood, generating false-positive "hidden value" flags. The peer-comp rule now compares apples to apples. Peer baselines are drawn from **all** scraped listings, including ones that fail the gate: a $1.3M neighbor is still a valid comp even though it can never be a buy.

Tweak weights in `pipeline/score.py` and rerun `python -m pipeline.score`.
