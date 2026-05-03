import {readFileSync, existsSync} from "node:fs";

const path = "data/sold/latest_redfin.json";
if (existsSync(path)) {
  process.stdout.write(readFileSync(path, "utf-8"));
} else {
  process.stdout.write(JSON.stringify({as_of: null, n_listings: 0, listings: []}));
}
