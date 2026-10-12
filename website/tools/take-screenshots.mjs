/*
  Takes the screenshots of the README and the website from the public demo
  (ch.rhinvoice.com, de.rhinvoice.com) into docs/screenshots.

    cd frontend && node ../website/tools/take-screenshots.mjs [https://ch.rhinvoice.com]

  The demo is shared: take them shortly after a reset (full hour) so that the data is the
  demo's own. Then run make-images.mjs for the website's AVIF/WebP copies and previews.
*/
import { join, resolve } from "node:path";
import { createRequire } from "node:module";
import { dirname } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(join(process.cwd(), "package.json"));
const { chromium, devices } = require("@playwright/test");

const out = resolve(dirname(fileURLToPath(import.meta.url)), "../../docs/screenshots");
const swiss = process.argv[2] ?? "https://ch.rhinvoice.com";
const german = swiss.replace("//ch.", "//de.");
// The screenshots show the product, not the demo strip.
const HIDE_DEMO = "aside[aria-label='Demo'] { display: none !important; }";

// German date fields need a German browser.
const browser = await chromium.launch({ args: ["--lang=de-CH"] });

async function open(base, options) {
  const context = await browser.newContext(options);
  const page = await context.newPage();
  await page.goto(base);
  await page.getByRole("button", { name: /Demo öffnen|Open the demo/ }).click();
  await page.getByRole("heading", { level: 1 }).waitFor();
  return { context, page };
}

async function shot(page, name) {
  // The editor refreshes its paper preview, so the network never goes quiet there.
  await page.waitForLoadState("load");
  await page.addStyleTag({ content: HIDE_DEMO });
  await page.waitForTimeout(1500);
  await page.screenshot({ path: join(out, `${name}.png`) });
}

{
  const { context, page } = await open(swiss, { viewport: { width: 1440, height: 900 }, locale: "de-CH" });
  await shot(page, "dashboard");
  await page.goto(`${swiss}/invoices`);
  await shot(page, "invoices");
  await page.getByRole("link", { name: "Entwurf" }).first().click();
  await page.getByRole("button", { name: "Ausstellen" }).waitFor();
  await page.waitForTimeout(3000);
  await shot(page, "editor");
  await context.close();
}
{
  const { context, page } = await open(german, {
    viewport: { width: 1440, height: 900 },
    locale: "de-DE",
    colorScheme: "dark",
  });
  await shot(page, "dashboard-dark");
  await context.close();
}
{
  const { context, page } = await open(swiss, { ...devices["Pixel 7"], locale: "de-CH" });
  await shot(page, "mobile-dashboard");
  await context.close();
}

await browser.close();
console.log("screenshots written to", out);
