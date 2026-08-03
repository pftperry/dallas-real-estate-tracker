---
title: Strategy
toc: true
---

# Strategy

This tab is the "what should I actually do this week" layer. The lists below are recomputed from the latest scrape every time the workflow runs.

Everything shown here has already cleared the hard eligibility gate: price inside the $750K–$1M band, 3+ beds, 2+ baths, and either resolved zoning to **Mockingbird or Lakewood Elementary** or an address inside the **drawn Lake Highlands zone**. Nothing that fails one of those is down-ranked; it is excluded before scoring, so these plays are already zoning-clean.

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
// Redundant since the price rule became part of the hard gate -- everything in
// watchlist.listings is already inside the band, so this is currently a no-op.
// Kept as a guard so these sections stay correct if the gate is ever relaxed
// back to scoring price rather than filtering on it.
const inBox = allActive.filter(li => li.price_usd >= buyBox.price_min_usd && li.price_usd <= buyBox.price_max_usd);
```

## This week's plays

Auto-generated from the most recent scrape. Listings appear in multiple sections if they qualify.

### Top 5 by buy-fit score

The watchlist's top picks. If you're going to look at five homes this week, look at these.

```js
function listingCard(li, footer) {
  const subName = areaName.get(li.sub_area_id) ?? li.sub_area_id ?? "";
  // Prefer the scorer's size-normalized peer baseline so the percentage shown
  // here matches what the score actually rewarded.
  const median = li._ppsf_baseline ?? watchlist.area_ppsf_medians?.[li.sub_area_id];
  const anchor = li._ppsf_baseline ? "peer comps" : `${subName} median`;
  const ppsfDelta = median && li.ppsf_usd
    ? `${li.ppsf_usd > median ? "+" : ""}${Math.round(((li.ppsf_usd - median) / median) * 100)}% vs ${anchor}`
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

### Hidden value (≥15% under the size-normalized peer baseline)

Mispriced or motivated sellers. These either need first-look quickly, or have a reason no one else wants them, so find out why before assuming it's a deal.

Measured against sold comps in the same sub-area within ±25% of the listing's square footage, which is the same baseline the score uses. Larger homes carry a lower $/sqft as a matter of arithmetic, so comparing against a flat area median would surface every big house in a small-house neighborhood as a bargain.

```js
// Use the size-normalized peer baseline the scorer uses (_ppsf_baseline: same
// sub-area, +/-25% sqft), falling back to the area median only when no peer set
// existed. Comparing against the raw area median flagged every large home in a
// small-home neighborhood as "hidden value", which is the exact false positive
// the peer baseline was introduced to kill.
const ppsfBase = li => li._ppsf_baseline ?? watchlist.area_ppsf_medians?.[li.sub_area_id];
const hidden = inBox.filter(li => {
  const m = ppsfBase(li);
  return m && li.ppsf_usd && li.ppsf_usd <= m * 0.85;
}).sort((a, b) => (a.ppsf_usd / ppsfBase(a)) - (b.ppsf_usd / ppsfBase(b))).slice(0, 6);

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

### At your ceiling ($900K–$1.0M, score ≥ 50)

Top of your band, score still solid. $1.0M is a hard ceiling now rather than a stretch target, so anything past it never appears anywhere on this page. That makes this the rationality test on the last $100K of budget: are you spending it for a real reason (zoning, lot, condition) or just because the listing exists?

```js
const ceiling = allActive.filter(li =>
  li.price_usd >= 900_000 && li.price_usd <= buyBox.price_max_usd && (li._score ?? 0) >= 50
).slice(0, 6);

display(ceiling.length
  ? html`<div class="grid grid-cols-2 grid-cols-3-md">${ceiling.map(li => listingCard(li, html`<b>$${(li.price_usd/1000).toFixed(0)}k &middot; score ${li._score}</b>`))}</div>`
  : html`<p><i>No listings in the $900K–$1.0M band scoring ≥ 50 right now.</i></p>`);
```

## Tactical playbook by how listings qualify

Tiers no longer drive where you spend your time; the location gate does. The groups below are ordered by how reliably an area can produce an eligible listing at all. Both allowlisted elementaries feed Long MS and then Wilson HS, so the high-school anchor is identical whichever side of the gate a listing clears on.

### Whole footprint inside a qualifying zone

The only group where the neighborhood name is enough. Spend the most time here.

- **Hollywood Heights / Santa Monica** &mdash; The standout post-gate. Its entire footprint sits inside a qualifying zone, split roughly Lakewood east / Mockingbird west, so every address clears the location test. $749K median sits right at the $750K floor, so the band opens where the local market already is rather than above it. Look for: Tudor or Craftsman with original details. Skip: anything where the exterior was recently changed without permits (conservation district = clawback risk). 47% YoY $/sqft is a thin-sample yellow flag, so verify with at least 3 same-block comps before paying ask.

### Partially zoned, so the address decides

Real inventory here, but the neighborhood name tells you nothing. The watchlist resolves zoning per listing; two homes on facing blocks can land on opposite sides of the gate.

- **M Streets / Greenland Hills** &mdash; Best price fit of any strong area: $865K median sits comfortably mid-band, so you are not buying the top of the local market. Mockingbird covers only part of the footprint, which is exactly why per-address zoning matters more here than in Hollywood Heights. Look for: Mercedes, Monticello, Martel, the quietest streets. Walkable to Greenville Ave (Walk Score ~75). Skip: anything backing 75 / Knox-Henderson. Conservation district. Negative YoY (-6.9%) = buyer leverage.
- **Caruth Terrace** &mdash; Small enclave east of Greenville Ave, north of Belmont. Mostly Mockingbird-zoned, but both active listings in the last snapshot fell *outside* the zone, which is where per-address checking earns its keep. $654K median now sits just under the $750K floor, so entry-level stock is too cheap to qualify: the target is the $750K–$1M renovated mid-century band. 66 DOM = real negotiation room. +36% YoY $/sqft is thin-sample noise, so verify against same-block comps.
- **Vickery Place** &mdash; Urban-walkable, M Streets-adjacent. Roughly the northern 60% is Mockingbird; the southern remainder splits to Geneva Heights and Lipscomb and fails the gate outright. $1.21M median sits above the ceiling, so what qualifies will be the smaller or less-updated end. +30% YoY is real momentum.
- **Lakewood Hills** &mdash; North of Mockingbird Ln, south of NW Hwy, east of Abrams. The Lakewood zone covers the southern portion only; the northern strip fails. $1.4M median is well over the ceiling, so only bottom-of-range listings can qualify.
- **Lakewood Heights** &mdash; Split across both qualifying zones, covering most of its footprint. $1.2M median is above the ceiling, so expect the smaller or less-updated end of its 1930s-original stock.

### Qualifying zoning, priced above the ceiling

These clear the school gate but not the $1M price rule, so listings will be rare. Keep them for comps and for the occasional original-condition print.

- **Lakewood proper** &mdash; Almost entirely Lakewood Elementary, so it clears the school gate nearly everywhere. $1.495M–$1.6M median is far above the ceiling. Walking distance to White Rock Lake and Lakewood Country Club; conservation district overlay in some pockets.
- **Hillside** &mdash; West of White Rock Lake, mostly mid-century ranches built 1951 to the early 1960s, mature trees, serene streetscape. Lakewood covers nearly all of it. $1.3M median is over the ceiling, so an original-condition ranch is the realistic entry.
- **Wilshire Heights** &mdash; Mostly Mockingbird. $1.5M median is far over the ceiling; kept mainly for the Mockingbird-side comp set. 97% YoY is thin-sample noise.

### Qualifying on geography only, via the drawn zone

No school path here. These qualify because of where they sit, so treat the elementary question as unanswered rather than answered.

- **L Streets (drawn Lake Highlands zone)** &mdash; Qualifies on geography alone, independent of schools. It is RISD, so the DISD elementary gate can never pass here. Bounded by Audelia Rd (west), Plano Rd (east), East Northwest Hwy (south), and a line just south of I-635 (north). At $750K–$1M you are 1.3–1.7x the area median ($599K), so the resale pool is thinner than on the Lakewood side. Only worth it for fully renovated or expanded turnkey on the best streets.
- **Lake Park Estates** &mdash; Hexter-zoned, so it fails the school gate everywhere. Its northwest corner falls inside the drawn zone, and that corner is the entire reason it is still tracked. Mid-century modern, large lots up to 0.5ac. Includes the newer Wyrick Estates / Eastwood Estates pockets that Redfin loosely tags as "Forest Hills."
- **Lake Highlands Estates** &mdash; RISD, so the elementary gate cannot pass. It sits mostly *west* of Audelia Rd and therefore outside the drawn zone; only its eastern edge qualifies. ~$1.03M median means anything eligible is at the bottom of the local range, so you are paying full retail for a premium LH pocket. Fine as an explicit choice, less fine as an emotional one.

### Watch area

- **Mockingbird Meadows** &mdash; Promoted in relevance by the gate: about half its footprint is Mockingbird-zoned, which the old config did not reflect. $662K median sits just under the $750K floor, so much of the local stock prices below the band. 147 DOM = very slow, which is either a stale market or a hidden opportunity. It is scraped and scored like the primary areas, so anything here that clears the gate surfaces in the lists above on its own.

## Buy-box hygiene checklist

Run through this for every listing you tour.

- [ ] **DCAD verify lot size and sqft.** Listings often inflate sqft. Pull the parcel and compare. (DCAD search: https://www.dallascad.org)
- [ ] **Foundation report mandatory.** North Texas has expansive clay soils (50–70% clay) that swell and shrink. 1940s–1970s East Dallas homes commonly have foundation history. Require a structural engineer report (not just a regular inspector). A $30K foundation issue can be invisible at showing.
- [ ] **Roof age ≤ 12 years.** Dallas hail events nearly doubled 2022–2024; Texas insurance averages ~$4,380/yr (~85% above national). Old roofs are insurability landmines. Impact-resistant Class 4 shingles are a meaningful underwriting plus.
- [ ] **FEMA flood zone check.** Use FEMA maps or First Street Flood Factor. Anything in the 100-year floodplain dramatically raises insurance and limits renovation options.
- [ ] **School zoning is already resolved for you.** Every eligible listing carries its resolved elementary, middle and high school, read from the official DISD 2026-27 attendance polygons against the listing's own coordinates. There is no per-address lookup left to do by hand, and the neighborhood feeder labels are not what the gate uses. Two things still need you: (1) any listing flagged `_near_zone_edge`, meaning it sits within 40m of an attendance boundary, needs confirming on DISD SchoolFinder, because rooftop coordinates cannot settle which side of the line a home falls on; (2) RISD zoning inside the drawn Lake Highlands zone is **not** verified against official boundaries, since only DISD polygons are cached. Those listings qualify on geography, so nothing in the gate depends on it, but do not treat the RISD feeder shown as confirmed.
- [ ] **If Hollywood Heights, M Streets, or a Lakewood proper conservation pocket:** confirm any planned exterior changes are allowed under the conservation district guidelines. Review board can take 6+ weeks.
- [ ] **Pull last 5 sold within 0.25mi** for a real comp anchor. The Comps tab gives you sub-area level; a quarter-mile radius is what an appraiser will use.
- [ ] **Tax appraisal vs. asking.** Texas non-disclosure means DCAD's appraised value is an imperfect anchor (often trails market by 10–25% due to caps and protests), but a >40% premium over appraised value warrants a "what changed?" conversation.
- [ ] **Property tax protest history.** Pull the parcel's protest record. A house that's been successfully protested down has lower carry cost; one that hasn't may have room you can capture.
- [ ] **Drive-by at 7am, 5pm, and 9pm.** Noise pockets, traffic flow, neighbor parking, ambient activity don't show up on Zillow. Especially important for anything inside one block of Mockingbird Ln, NW Hwy, Abrams, Greenville Ave, Audelia or Plano Rd.
- [ ] **Listing agent owner-motivation question.** "Why is the seller moving and what's their timeline?" Ask in the first call, not the offer.
- [ ] **ForwardDallas zoning check.** The 2024 ForwardDallas plan allows more "missing middle" housing (duplexes, ADUs) in historically single-family zones. Established conservation districts like Hollywood Heights and M Streets are largely protected, but areas without conservation or historic-district status, the Lake Highlands-side pockets in particular, could see density changes. Check the parcel's zoning classification on the city's plan.

## How to use this tracker

- **Daily:** Open the Watchlist tab. Everything on it has already cleared the gate, pre-ranked by score, top 30 shown. Anything new at the top, look at within 24 hours. Check the near-miss list under it as well: those failed on location alone and are ranked by how far they sit from the boundary.
- **Weekly:** Open the Comps tab on Sunday after the weekly sold scrape. Any new comps in your target sub-areas? Update your mental anchor for asking-price reasonableness.
- **Monthly:** Look at the Sub-area scorecards tab. Has the buy-box capture rate moved? Has $/sqft IQR widened (more dispersion = more opportunity)?
- **When something hits:** Use the Map tab to see what else is nearby in your price band, drive the area at varied times, run through the hygiene checklist before offering.

## Calibration & caveats

- **Texas non-disclosure** &mdash; Sale prices in this dashboard come from MLS via Redfin, not DCAD. Trust the Redfin data; DCAD has appraised values, which are not sale prices.
- **Bounding boxes are rough rectangles** &mdash; A few listings are technically in a different sub-area than the one they're tagged with. Those rectangles now only drive scraping and labeling, never eligibility, so the imprecision costs you a label rather than a qualification. Eligibility uses real polygons: the DISD attendance boundaries and the traced outline of the drawn Lake Highlands zone.
- **Schools are a gate, not a weight** &mdash; A listing that fails the elementary or drawn-zone test never reaches the lists above, so there is no "good area, bad schools" trade left to make here. Schools carry **no** scoring weight at all now: the gate guarantees them, and ranking them again only docked Lake Highlands homes for qualifying on geography rather than on a DISD boundary. Location is likewise absent from the score. What ranks a listing is the house: lot 30%, period character 25%, $/sqft vs peers 20%, baths per bedroom 10%, size 10%, price position 5%.
- **Days on market is not scored** &mdash; It used to be the strongest single driver, which put a listing that had sat 114 days at the top. It is a flag beside the score now: fresh means expect competition, 90+ days means find out what is wrong before treating it as a bargain.
- **Thin samples on appreciation** &mdash; Areas like Hollywood Heights show 47% YoY $/sqft, which is real signal, but each percentage point comes from only a handful of closings. Don't size up a bid based on the YoY alone.
- **The score is a tool, not a verdict.** The gate does the culling now, and it cuts hard: most of what gets scraped never makes it here. The handful you actually tour deserve human judgment.
