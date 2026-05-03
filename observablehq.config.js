// Base path is /dallas-real-estate-tracker/ on GitHub Pages
// (username.github.io/dallas-real-estate-tracker/). Override locally with
// `OBSERVABLE_BASE=/ npm run dev` if you want root-relative paths.
const base = process.env.OBSERVABLE_BASE ?? "/dallas-real-estate-tracker/";

export default {
  title: "Dallas Real Estate Tracker",
  pages: [
    { name: "Watchlist", path: "/" },
    { name: "Strategy", path: "/strategy" },
    { name: "Sub-area scorecards", path: "/scorecards" },
    { name: "Comps explorer", path: "/comps" },
    { name: "Map", path: "/heatmap" },
    { name: "About", path: "/about" }
  ],
  theme: ["air", "near-midnight"],
  header: "Lakewood &middot; Lake Highlands",
  footer: "Personal tracker. Data: Redfin + DCAD. Refreshed daily.",
  output: "dist",
  root: "src",
  base,
  cleanUrls: true
};
