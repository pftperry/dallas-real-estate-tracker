import {readFileSync, existsSync} from "node:fs";

const path = "data/stats/latest_scorecards.json";
if (existsSync(path)) {
  process.stdout.write(readFileSync(path, "utf-8"));
} else {
  process.stdout.write(JSON.stringify({as_of: null, scorecards: []}));
}
