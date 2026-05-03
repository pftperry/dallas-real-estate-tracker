import {readFileSync, existsSync} from "node:fs";

// Data loader: reads the latest scored watchlist from the repo-root data/
// folder and pipes it to stdout. Observable Framework runs this at build
// time so the resulting data/watchlist.json is colocated with src/data/.
const path = "data/stats/latest_watchlist.json";
if (existsSync(path)) {
  process.stdout.write(readFileSync(path, "utf-8"));
} else {
  process.stdout.write(JSON.stringify({
    as_of: null,
    n: 0,
    listings: [],
    weights: {},
    buy_box: {},
    area_ppsf_medians: {},
    note: "No watchlist snapshot yet. Run pipeline.score after the first Redfin scrape."
  }));
}
