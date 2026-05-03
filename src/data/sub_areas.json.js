import {readFileSync} from "node:fs";

// Sub-area config is required for the dashboard. Fail loud if missing.
process.stdout.write(readFileSync("config/sub_areas.json", "utf-8"));
