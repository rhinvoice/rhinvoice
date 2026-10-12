/*
  Renders the images of rhinvoice.com that are made, not drawn:

    assets/img/og.png, og-de.png            social previews, 1200 x 630
    assets/img/icon-192.png, icon-512.png    app icons from favicon.svg
    assets/img/icon-512-maskable.png         with the safe zone Android needs
    assets/img/apple-touch-icon.png          180 x 180
    assets/img/shots/*.{png,webp,avif}       screenshots from docs/screenshots

  Run from the frontend folder, which has Playwright:
    cd frontend && node ../website/tools/make-images.mjs
  Needs cwebp and avifenc (brew install webp libavif) for the screenshots.
*/
import { execFileSync } from "node:child_process";
import { copyFileSync, mkdirSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const require = createRequire(join(process.cwd(), "package.json"));
const { chromium } = require("@playwright/test");

const tools = dirname(fileURLToPath(import.meta.url));
const site = resolve(tools, "../site");
const img = join(site, "assets/img");
const shots = join(img, "shots");
const screenshots = resolve(tools, "../../docs/screenshots");
const favicon = pathToFileURL(join(img, "favicon.svg")).href;

const browser = await chromium.launch();

async function render(url, width, height, path) {
  const page = await browser.newPage({ viewport: { width, height } });
  await page.goto(url);
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path, omitBackground: false });
  await page.close();
}

const og = pathToFileURL(join(tools, "og.html")).href;
await render(og, 1200, 630, join(img, "og.png"));
await render(`${og}?lang=de`, 1200, 630, join(img, "og-de.png"));

// The icon on a square ground; "inset" leaves the margin maskable icons need.
async function icon(size, path, inset) {
  const page = await browser.newPage({ viewport: { width: size, height: size } });
  const pad = Math.round(size * inset);
  await page.setContent(
    `<body style="margin:0;background:#2f5d8a"><img src="${favicon}" style="display:block;width:${size - 2 * pad}px;height:${size - 2 * pad}px;margin:${pad}px"></body>`,
  );
  await page.screenshot({ path });
  await page.close();
}
await icon(192, join(img, "icon-192.png"), 0);
await icon(512, join(img, "icon-512.png"), 0);
await icon(512, join(img, "icon-512-maskable.png"), 0.1);
await icon(180, join(img, "apple-touch-icon.png"), 0);

await browser.close();

mkdirSync(shots, { recursive: true });
// Only the screenshots the pages show.
for (const name of ["dashboard", "editor", "dashboard-dark"]) {
  const file = `${name}.png`;
  copyFileSync(join(screenshots, file), join(shots, file));
  execFileSync("cwebp", ["-quiet", "-q", "82", join(screenshots, file), "-o", join(shots, `${name}.webp`)]);
  execFileSync("avifenc", ["--speed", "6", "-q", "60", join(screenshots, file), join(shots, `${name}.avif`)], { stdio: "ignore" });
}
console.log("images written to", img);
