// Record the Leaves.PH protected-areas demo GIF of the live surface.
//
// Reproducible recipe (run from site/):
//   pnpm build && pnpm preview --port 4331 &
//   node scripts/record_protected_areas_demo.mjs
//
// Narrative: the national accountability inventory. Land on the headline
// ("185,955 ha cleared inside 251 protected areas"), scroll to the national
// choropleth, open the worst area (Palawan Game Refuge, 101,355 ha) from the
// ranked table so the map flies and its popup shows, re-rank by share of each
// area's own forest (South Upi tops at ~23%), then flip the page to Filipino.
// Records the production preview build (no dev toolbar); drives the same page a
// visitor does; ffmpeg palette-encodes to docs/demo/protected-areas.{gif,mp4}.
import { chromium } from "playwright";
import { execSync } from "node:child_process";
import fs from "node:fs";

const BASE = "http://localhost:4331";
const OUT = "/Users/xavier/Desktop/leaves-ph/docs/demo";
const WORK = "/Users/xavier/Desktop/leaves-ph/tmp/pa-demo-record";
fs.rmSync(WORK, { recursive: true, force: true });
fs.mkdirSync(WORK + "/video", { recursive: true });
fs.mkdirSync(OUT, { recursive: true });

const cursorInit = () => {
  const c = document.createElement("div");
  c.id = "__cursor";
  c.style.cssText =
    "position:fixed;left:-60px;top:-60px;width:22px;height:22px;border:2px solid #1a1a1a;border-radius:50%;background:rgba(182,87,36,0.4);box-shadow:0 1px 5px rgba(0,0,0,0.35);z-index:99999;pointer-events:none;transform:translate(-50%,-50%);transition:left 0.4s ease,top 0.4s ease;";
  const add = () => (document.body || document.documentElement).appendChild(c);
  if (document.body) add();
  else document.addEventListener("DOMContentLoaded", add);
  window.__cur = (x, y) => {
    const e = document.getElementById("__cursor");
    if (e) {
      e.style.left = x + "px";
      e.style.top = y + "px";
    }
  };
  window.__pulse = () => {
    const e = document.getElementById("__cursor");
    if (e)
      e.animate(
        [{ transform: "translate(-50%,-50%) scale(1)" }, { transform: "translate(-50%,-50%) scale(0.55)" }, { transform: "translate(-50%,-50%) scale(1)" }],
        { duration: 300 },
      );
  };
};

const b = await chromium.launch({ headless: true });
const ctx = await b.newContext({
  viewport: { width: 1040, height: 820 },
  deviceScaleFactor: 2,
  recordVideo: { dir: WORK + "/video", size: { width: 1040, height: 820 } },
});
const page = await ctx.newPage();
await page.addInitScript(cursorInit);
await page.goto(BASE + "/protected-areas/", { waitUntil: "domcontentloaded" });
// wait for the data-driven headline + table to populate
await page.waitForFunction(
  () => {
    const h = document.getElementById("hl-loss-ha");
    const t = document.getElementById("pa-tbody");
    return h && h.textContent && h.textContent !== "—" && t && t.children.length > 5;
  },
  { timeout: 25000 },
);
await page.waitForTimeout(2500); // let map tiles + polygons settle

const center = async (sel) => {
  const bb = await page.locator(sel).boundingBox();
  if (bb) await page.evaluate(([x, y]) => window.__cur(x, y), [bb.x + bb.width / 2, bb.y + bb.height / 2]);
  return bb;
};
const scrollTo = (sel, block = "center") =>
  page.evaluate(([s, bl]) => document.querySelector(s)?.scrollIntoView({ behavior: "smooth", block: bl }), [sel, block]);

const tLoaded = Date.now();

// BEAT 1: the headline + the 185,955 ha stat
await page.evaluate(() => window.scrollTo({ top: 0 }));
await center("#hl-loss-ha");
await page.waitForTimeout(2400);

// BEAT 2: the national choropleth (Palawan's orange band stands out)
await scrollTo("#pa-map");
await page.waitForTimeout(2600);

// BEAT 3: open the worst area from the ranked table -> map flies + popup
await scrollTo("#pa-tbody", "start");
await page.waitForTimeout(1100);
const row1 = await center("#pa-tbody tr:first-child");
if (row1) await page.evaluate(() => window.__pulse());
await page.waitForTimeout(450);
await page.locator("#pa-tbody tr:first-child").click();
await page.waitForTimeout(900);

// BEAT 4: reveal the flown map with Palawan's popup (101,355 ha / 11.7%)
await scrollTo("#pa-map");
await page.waitForTimeout(3000);

// BEAT 5: re-rank by share of each area's own forest -> South Upi tops
await scrollTo("#pa-tbody", "start");
await page.waitForTimeout(900);
const sortBtn = await center("#sort-pct");
if (sortBtn) await page.evaluate(() => window.__pulse());
await page.waitForTimeout(350);
await page.locator("#sort-pct").click();
await page.waitForTimeout(2600);

// BEAT 6: flip the whole surface to Filipino
await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
await page.waitForTimeout(900);
const tl = await center("#lang-tl");
if (tl) await page.evaluate(() => window.__pulse());
await page.waitForTimeout(350);
await page.locator("#lang-tl").click();
await page.waitForTimeout(2800);

const tEnd = Date.now();
await ctx.close();
await b.close();

const beatsSec = (tEnd - tLoaded) / 1000;
const webm = WORK + "/video/" + fs.readdirSync(WORK + "/video").find((f) => f.endsWith(".webm"));
const raw = WORK + "/raw.webm";
fs.copyFileSync(webm, raw);
const trim = WORK + "/trim.webm";
const tail = (beatsSec + 0.4).toFixed(1);
execSync(`ffmpeg -y -sseof -${tail} -i "${raw}" -c:v libvpx-vp9 -b:v 3M -an "${trim}"`, { stdio: "ignore" });
const gif = OUT + "/protected-areas.gif";
const palette = WORK + "/palette.png";
const VF = "fps=9,scale=640:-1:flags=lanczos";
execSync(`ffmpeg -y -i "${trim}" -vf "${VF},palettegen=max_colors=128:stats_mode=diff" "${palette}"`, { stdio: "ignore" });
execSync(`ffmpeg -y -i "${trim}" -i "${palette}" -lavfi "${VF}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=5" "${gif}"`, { stdio: "ignore" });
execSync(`ffmpeg -y -i "${trim}" -c:v libx264 -pix_fmt yuv420p -crf 21 -vf "scale=1040:-2:flags=lanczos,format=yuv420p" -movflags +faststart "${OUT}/protected-areas.mp4"`, { stdio: "ignore" });
console.log("beatsSec", beatsSec.toFixed(1));
console.log("GIF_MB", (fs.statSync(gif).size / 1e6).toFixed(2), "bytes", fs.statSync(gif).size);
