import { chromium } from "playwright";
import { fileURLToPath } from "url";
import path from "path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const htmlPath = path.join(__dirname, "og-card.html");
const outPath = path.join(__dirname, "..", "public", "og-preview.png");

const browser = await chromium.launch();
const page = await browser.newPage({
  viewport: { width: 1200, height: 630 },
  deviceScaleFactor: 1,
});
await page.goto("file://" + htmlPath, { waitUntil: "networkidle" });
// ensure webfonts are fully loaded before shooting
await page.evaluate(() => document.fonts.ready);
await page.waitForTimeout(400);
await page.screenshot({ path: outPath, clip: { x: 0, y: 0, width: 1200, height: 630 } });
await browser.close();
console.log("wrote", outPath);
