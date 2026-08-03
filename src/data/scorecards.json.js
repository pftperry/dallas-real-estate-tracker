import {readFileSync, existsSync} from "node:fs";

// See src/data/watchlist.json.js for why data/stats/ is untracked and why a
// missing file fails loudly rather than degrading to an empty payload.
const statsPath = "data/stats/latest_scorecards.json";
const inputPath = "data/listings/latest_redfin.json";

if (existsSync(statsPath)) {
  process.stdout.write(readFileSync(statsPath, "utf-8"));
} else if (existsSync(inputPath)) {
  throw new Error(
    `${statsPath} is missing but ${inputPath} exists, so listings were scraped and ` +
    `never aggregated. data/stats/ is derived and intentionally untracked.\n` +
    `Run:  py -m pipeline.score && py -m pipeline.aggregate\n` +
    `(use "python" instead of "py" on Linux/CI)`
  );
} else {
  process.stdout.write(JSON.stringify({as_of: null, scorecards: []}));
}
