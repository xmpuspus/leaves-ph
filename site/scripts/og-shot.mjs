import { chromium } from "playwright";
import { fileURLToPath } from "url";
import { readFileSync } from "fs";
import path from "path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const htmlPath = path.join(__dirname, "og-card.html");
const seriesPath = path.join(__dirname, "..", "src", "lib", "series.ts");
const outPath = path.join(__dirname, "..", "public", "og-preview.png");

// Pull the published figures straight from series.ts so the card stays in lockstep
// with the site and can't drift the way a hardcoded preview silently did.
const series = readFileSync(seriesPath, "utf8");
const constant = (name) => {
  const m = series.match(new RegExp(`export const ${name}\\s*=\\s*([0-9.]+)`));
  if (!m) throw new Error(`series.ts is missing ${name}`);
  return m[1];
};
const stats = {
  canopy: constant("LATEST_NCR_PCT"),
  lgus: constant("NCR_LGU_COUNT"),
  bgys: constant("NCR_BARANGAY_COUNT"),
  f1: Number(constant("CANOPY_MODEL_F1")).toFixed(2),
  labels: constant("GOLD_LABEL_N"),
};

const browser = await chromium.launch();
const page = await browser.newPage({
  viewport: { width: 1200, height: 630 },
  deviceScaleFactor: 1,
});
await page.goto("file://" + htmlPath, { waitUntil: "networkidle" });
await page.evaluate((s) => {
  const set = (id, v) => {
    const el = document.getElementById(id);
    if (el) el.textContent = v;
  };
  set("og-canopy", s.canopy);
  set("og-lgus", s.lgus);
  set("og-lgus2", s.lgus);
  set("og-bgys", s.bgys);
  set("og-bgys2", s.bgys);
  set("og-f1", s.f1);
  set("og-labels", s.labels);
}, stats);
// ensure webfonts are fully loaded before shooting
await page.evaluate(() => document.fonts.ready);
await page.waitForTimeout(400);
await page.screenshot({ path: outPath, clip: { x: 0, y: 0, width: 1200, height: 630 } });
await browser.close();
console.log("wrote", outPath);
