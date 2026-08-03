import {readFileSync, existsSync} from "node:fs";

// Pipes the scored watchlist to stdout; Observable Framework runs this at build
// time so the result is served as data/watchlist.json.
//
// data/stats/ is NOT committed (see .gitignore) because it is derived from
// data/listings/ + data/sold/ + code + config, and committing it produced a merge
// conflict every time a CI run landed while a branch was open. That makes a
// missing file here ambiguous, so the two cases are told apart deliberately:
//
//   inputs present, stats absent -> the pipeline was not run. FAIL the build.
//   inputs absent too            -> genuine cold start. Emit an empty shell.
//
// The old fallback emitted an empty watchlist in both cases, which would now
// publish a live site reading "0 eligible" whenever someone forgot to run the
// scorer. An empty watchlist must never be indistinguishable from a broken build.
const statsPath = "data/stats/latest_watchlist.json";
const inputPath = "data/listings/latest_redfin.json";

if (existsSync(statsPath)) {
  process.stdout.write(readFileSync(statsPath, "utf-8"));
} else if (existsSync(inputPath)) {
  throw new Error(
    `${statsPath} is missing but ${inputPath} exists, so listings were scraped and ` +
    `never scored. data/stats/ is derived and intentionally untracked.\n` +
    `Run:  py -m pipeline.score && py -m pipeline.aggregate\n` +
    `(use "python" instead of "py" on Linux/CI)`
  );
} else {
  process.stdout.write(JSON.stringify({
    as_of: null,
    listings_as_of: null,
    n: 0,
    n_screened: 0,
    n_excluded: 0,
    listings: [],
    excluded: [],
    weights: {},
    buy_box: {},
    eligible_by_basis: {},
    exclusion_reason_counts: {},
    area_ppsf_medians: {},
    note: "Cold start: no listings snapshot yet. Run scrapers.redfin, then pipeline.score."
  }));
}
