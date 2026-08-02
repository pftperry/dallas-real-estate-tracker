import {readFileSync} from "node:fs";

// The map only needs the zones that actually gate eligibility, so this filters
// the cache down to the allowlist before shipping it to the browser. The full
// cache is all 135 DISD elementary zones (~1MB) because scoring needs to resolve
// what a *rejected* listing is zoned to; sending all of that to the client would
// be a megabyte of polygons nobody draws.
//
// The allowlist is read from sub_areas.json rather than hardcoded here, so there
// is one place to change it. pipeline/score.py refuses to run if that list and
// scrapers/school_zones.TARGET_ELEMENTARIES disagree.
const zones = JSON.parse(readFileSync("config/school_zones.geojson", "utf-8"));
const allow = new Set(
  JSON.parse(readFileSync("config/sub_areas.json", "utf-8"))
    .buy_box.eligibility.elementary_allowlist
);

const features = zones.features.filter(f => allow.has(f.properties.ELEM_DESC));
if (features.length !== allow.size) {
  // Fail the build rather than render a map that silently omits a qualifying
  // zone, which would read as "no listings qualify over there".
  const found = features.map(f => f.properties.ELEM_DESC);
  throw new Error(
    `school_zones: expected ${allow.size} qualifying zones, found ${features.length}. ` +
    `Missing: ${[...allow].filter(n => !found.includes(n)).join(", ")}. ` +
    `Run: python -m scrapers.school_zones --refresh`
  );
}

process.stdout.write(JSON.stringify({...zones, features}));
