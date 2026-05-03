---
title: Strategy
toc: true
---

# Strategy

This tab is the "what should I actually do this week" layer. The lists below are recomputed from the latest scrape every time the workflow runs.

```js
const watchlist = await FileAttachment("data/watchlist.json").json();
const sold = await FileAttachment("data/sold.json").json();
const config = await FileAttachment("data/sub_areas.json").json();
const card = await FileAttachment("data/scorecards.json").json();
```

```js
const areaName = new Map([
  ...config.sub_areas.map(a => [a.id, a.name]),
  ...(config.watch_areas || []).map(a => [a.id, a.name])
]);
const buyBox = config.buy_box;
const allActive = (watchlist.listings || []);
const inBox = allActive.filter(li => li.price_usd >= buyBox.price_min_usd && li.price_usd <= buyBox.price_max_usd);
```

## This week's plays

Auto-generated from the most recent scrape. Listings appear in multiple sections if they qualify.

### Top 5 by buy-fit score

The watchlist's top picks. If you're going to look at five homes this week, look at these.

```js
function listingCard(li, footer) {
  const subName = areaName.get(li.sub_area_id) ?? li.sub_area_id ?? "";
  const median = watchlist.area_ppsf_medians?.[li.sub_area_id];
  const ppsfDelta = median && li.ppsf_usd
    ? `${li.ppsf_usd > median ? "+" : ""}${Math.round(((li.ppsf_usd - median) / median) * 100)}% vs ${subName} median`
    : "";
  return html`
    <div class="card" style="padding: 0.6rem 0.8rem;">
      <h3 style="margin: 0 0 0.25rem 0; font-size: 0.95rem;">
        <a href="${li.url ?? "#"}" target="_blank" rel="noopener">${li.address}</a>
      </h3>
      <div style="font-size: 0.85rem; color: var(--theme-foreground-muted);">
        ${subName} &middot; built ${li.year_built ?? "—"} &middot; ${li.beds ?? "—"} bd / ${li.baths ?? "—"} ba
      </div>
      <div style="margin: 0.4rem 0; font-size: 1rem;">
        <b>$${li.price_usd ? (li.price_usd/1000).toFixed(0) : "—"}k</b>
        &nbsp;&middot;&nbsp;
        <span style="color: var(--theme-foreground-muted)">${li.sqft?.toLocaleString() ?? "—"} sqft</span>
        &nbsp;&middot;&nbsp;
        <span style="color: var(--theme-foreground-muted)">$${li.ppsf_usd ?? "—"}/sqft</span>
      </div>
      <div style="font-size: 0.8rem; color: var(--theme-foreground-muted);">
        DOM ${li.days_on_market ?? "—"} &middot; ${ppsfDelta}
      </div>
      <div style="font-size: 0.8rem; margin-top: 0.4rem;">${footer}</div>
    </div>
  `;
}
```

```js
const top5 = allActive.slice(0, 5);
html`<div class="grid grid-cols-2 grid-cols-3-md">${top5.map(li => listingCard(li, html`<b>Score:</b> ${li._score}`))}</div>`
```

### Hidden value (≥15% under sub-area $/sqft median)

Mispriced or motivated sellers. These either need first-look quickly, or have a reason no one else wants them — find out why before assuming it's a deal.

```js
const hidden = inBox.filter(li => {
  const m = watchlist.area_ppsf_medians?.[li.sub_area_id];
  return m && li.ppsf_usd && li.ppsf_usd <= m * 0.85;
}).sort((a, b) => {
  const ma = watchlist.area_ppsf_medians?.[a.sub_area_id] ?? 0;
  const mb = watchlist.area_ppsf_medians?.[b.sub_area_id] ?? 0;
  return (a.ppsf_usd / ma) - (b.ppsf_usd / mb);
}).slice(0, 6);

display(hidden.length
  ? html`<div class="grid grid-cols-2 grid-cols-3-md">${hidden.map(li => listingCard(li, html`<b style="color:#16a34a">Likely undervalued</b>`))}</div>`
  : html`<p><i>No active listings ≥15% under area median right now.</i></p>`);
```

### Negotiation territory (DOM > 60 in your buy box)

Stale listings where you have leverage. Open with 5–8% below ask if condition supports it.

```js
const stale = inBox.filter(li => (li.days_on_market ?? 0) > 60)
  .sort((a, b) => (b.days_on_market ?? 0) - (a.days_on_market ?? 0))
  .slice(0, 6);

display(stale.length
  ? html`<div class="grid grid-cols-2 grid-cols-3-md">${stale.map(li => listingCard(li, html`<b style="color:#a16207">${li.days_on_market} DOM &middot; leverage</b>`))}</div>`
  : html`<p><i>No buy-box listings sitting over 60 days right now. Either you're early or the market is hot — either way, no leverage plays this week.</i></p>`);
```

### At your ceiling ($1.0M–$1.1M, score ≥ 50)

Top of your band, score still solid. The rationality test: are you stretching for the right reasons (school zone, lot, condition) or just because it's available?

```js
const ceiling = allActive.filter(li =>
  li.price_usd >= 1_000_000 && li.price_usd <= buyBox.price_max_usd && (li._score ?? 0) >= 50
).slice(0, 6);

display(ceiling.length
  ? html`<div class="grid grid-cols-2 grid-cols-3-md">${ceiling.map(li => listingCard(li, html`<b>$${(li.price_usd/1000).toFixed(0)}k &middot; score ${li._score}</b>`))}</div>`
  : html`<p><i>No listings in the $1.0–1.1M band scoring ≥ 50 right now.</i></p>`);
```

## Tactical playbook by tier

### Tier S — Lakewood-orbit prime focus

Spend the most time here. These are the closest thing to "Lakewood proper" that fit the buy box.

- **Forest Hills (75218)** &mdash; Look for: 2,000–2,800 sqft homes with 8K+ lots between Garland Rd and Edmondson Ave, west of Buckner. Skip: anything backing Garland Rd or Buckner (busy-street flag in the watchlist). Note: Redfin tags newer northern subdivisions (Wyrick Estates, Lake Park) as "Forest Hills" — those are now bucketed under Lake Park Estates here. Median ~$759K (12mo); $1.1M buys the top quartile. Slowing market (48 DOM) = ask for terms (closing credit, repair credit) before discount.
- **Hollywood Heights / Santa Monica** &mdash; Look for: Tudor or Craftsman with original details. Skip: anything where exterior was recently changed without permits (conservation district = clawback risk). 47% YoY $/sqft pop is a yellow flag — verify with at least 3 same-block comps before paying ask.

### Tier A — RISD optionality + lake-adjacent value plays

Watch closely. Pull the trigger if a strong listing appears.

- **M Streets / Greenland Hills** *(demoted from S to A per critical review)* &mdash; Look for: Mercedes, Monticello, Martel — the quietest streets. Walkable to Greenville Ave (Walk Score ~75). Skip: anything backing 75 / Knox-Henderson. Conservation district. The "demotion" reasoning: walkable/urban character is meaningfully different from the lake-centric Lakewood vibe. Still a strong area, just not "Lakewood-orbit" in spirit.
- **Moss Farm** &mdash; +26% YoY momentum is real but watch for thin-sample bias. Verify against the dispersion ranking before paying ask. Smaller sub-area (~30 homes), inventory turns over slowly.
- **Merriman Park Estates** &mdash; 22 DOM = competitive. Don't try to negotiate hard on a fresh listing; either commit fast or pass. Best for renovated mid-century ranches; new construction here is rare.
- **Casa Linda** &mdash; The undervalued pick. Bryan Adams feeder is the school weakness, but for a 5+ year hold before kindergarten, you're getting Lakewood-orbit walking distance to White Rock Lake at $700K median. Niche #11 in Dallas. If you find a renovated 2,500+ sqft here at $850–950K, that's a genuinely good trade.
- **Lake Park Estates** *(new addition per critical review)* &mdash; Adjacent to Forest Hills, immediately northeast of White Rock Lake. Mid-century modern, large lots up to 0.5ac. Range $700K–$1.2M+. Same Bryan Adams feeder as Casa Linda but with deeper lake-adjacency and bigger lots. Inventory tight (<15 active typically); strong appreciation. Includes the newer Wyrick Estates / Eastwood Estates pockets.

### Tier B — Top of band buys

Only with a specific reason.

- **Lake Highlands Estates** &mdash; Use this if RISD becomes a hard requirement. ~$1M median means you're paying full retail for the school zone — fine if that's the explicit reason, less fine if you're emotional about it.
- **Old Lake Highlands** &mdash; The leverage play. 93 DOM means listings here are tired. Open at 8–10% below ask for anything sitting >75 days. School pattern (Bryan Adams) is the weakness — verify per-address school zone via the DISD lookup tool, not the neighborhood name.

### Tier C — RISD-only, top-of-area

Watch but don't lead with these.

- **L Streets** &mdash; At $1.1M you're 1.7–2x the area median ($599K). Resale pool is thinner. Only worth it for fully renovated/expanded turnkey on the best streets, with school zone as the explicit driver.
- **Town Creek** &mdash; Lower entry RISD pocket. You'd be at the top of the local market. Same caveat as L Streets.

## Buy-box hygiene checklist

Run through this for every listing you tour.

- [ ] **DCAD verify lot size and sqft.** Listings often inflate sqft. Pull the parcel and compare. (DCAD search: https://www.dallascad.org)
- [ ] **Foundation report mandatory.** North Texas has expansive clay soils (50–70% clay) that swell and shrink. 1940s–1970s East Dallas homes commonly have foundation history. Require a structural engineer report (not just a regular inspector). A $30K foundation issue can be invisible at showing.
- [ ] **Roof age ≤ 12 years.** Dallas hail events nearly doubled 2022–2024; Texas insurance averages ~$4,380/yr (~85% above national). Old roofs are insurability landmines. Impact-resistant Class 4 shingles are a meaningful underwriting plus.
- [ ] **FEMA flood zone check.** Use FEMA maps or First Street Flood Factor. Anything in the 100-year floodplain dramatically raises insurance and limits renovation options.
- [ ] **Confirm school zone for the specific address.** Old Lake Highlands has DISD/RISD boundary splits. Casa Linda and Lake Park Estates are Bryan Adams (DISD). Use https://www.risd.org or https://www.dallasisd.org with the actual address.
- [ ] **If Hollywood Heights or M Streets:** confirm any planned exterior changes are allowed under the conservation district guidelines. Review board can take 6+ weeks.
- [ ] **Pull last 5 sold within 0.25mi** for a real comp anchor. The Comps tab gives you sub-area level; a quarter-mile radius is what an appraiser will use.
- [ ] **Tax appraisal vs. asking.** Texas non-disclosure means DCAD's appraised value is an imperfect anchor (often trails market by 10–25% due to caps and protests), but a >40% premium over appraised value warrants a "what changed?" conversation.
- [ ] **Property tax protest history.** Pull the parcel's protest record. A house that's been successfully protested down has lower carry cost; one that hasn't may have room you can capture.
- [ ] **Drive-by at 7am, 5pm, and 9pm.** Noise pockets, traffic flow, neighbor parking, ambient activity don't show up on Zillow. Especially important for anything inside one block of Garland Rd, Skillman, Mockingbird, NW Hwy.
- [ ] **Listing agent owner-motivation question.** "Why is the seller moving and what's their timeline?" Ask in the first call, not the offer.
- [ ] **ForwardDallas zoning check.** The 2024 ForwardDallas plan allows more "missing middle" housing (duplexes, ADUs) in historically single-family zones. Most established conservation districts are protected, but Tier B/C areas without historic-district status could see density changes. Check the parcel's zoning classification on the city's plan.

## How to use this tracker

- **Daily:** Open the Watchlist tab. Top 30 are pre-ranked by score. Anything new at the top, look at within 24 hours.
- **Weekly:** Open the Comps tab on Sunday after the weekly sold scrape. Any new comps in your target sub-areas? Update your mental anchor for asking-price reasonableness.
- **Monthly:** Look at the Sub-area scorecards tab. Has the buy-box capture rate moved? Has $/sqft IQR widened (more dispersion = more opportunity)?
- **When something hits:** Use the Map tab to see what else is nearby in your price band, drive the area at varied times, run through the hygiene checklist before offering.

## Calibration & caveats

- **Texas non-disclosure** &mdash; Sale prices in this dashboard come from MLS via Redfin, not DCAD. Trust the Redfin data; DCAD has appraised values, which are not sale prices.
- **Bounding boxes are rough rectangles** &mdash; A few listings on this map are technically in a different sub-area than the one they're tagged with. Use the Sub_area column as a coarse filter and verify the actual neighborhood via the address.
- **Thin samples on appreciation** &mdash; Areas like Hollywood Heights show 47% YoY $/sqft, which is real signal, but each percentage point comes from only a handful of closings. Don't size up a bid based on the YoY alone.
- **The score is a tool, not a verdict.** It helps rank 109 listings into 30 worth opening. The final 5 you actually tour deserve human judgment.
