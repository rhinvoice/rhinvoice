import type { Page } from "@playwright/test";

import { createCustomer, expect, openApp, post, test, unique } from "./fixtures";

// The mail catcher of the E2E stack (compose.e2e.yml), as in mail.spec.ts.
const MAILPIT = process.env.E2E_MAILPIT_URL ?? "http://localhost:8025";

/**
 * Hold the requests that match until released: the action that sent them keeps running,
 * as with a slow connection or a large file, while the test tries to start it again.
 */
async function hold(page: Page, url: RegExp, method = "POST"): Promise<() => void> {
  let release: () => void = () => undefined;
  const released = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route(url, async (route) => {
    if (route.request().method() === method) await released;
    await route.continue();
  });
  return release;
}

async function issuedInvoice(page: Page, customerId: string): Promise<string> {
  const draft = await post<{ id: string }>(page, "/api/documents", {
    type: "invoice",
    customer_id: customerId,
    lines: [{ description: "Beratung", quantity: "2", unit: "HUR", unit_price: "150" }],
  });
  await post(page, `/api/documents/${draft.id}/issue`, {});
  return draft.id;
}

async function documentsOf(page: Page, customerId: string): Promise<number> {
  const response = await page.request.get(`/api/documents?customer_id=${customerId}`);
  return ((await response.json()) as { total: number }).total;
}

test("a new customer is saved once, with the shortcut held down and the button clicked", async ({
  page,
  isMobile,
}, testInfo) => {
  test.skip(isMobile, "keyboard shortcuts are a desktop feature");
  const name = `Tastenkürzel ${unique(testInfo.project.name)} AG`;
  await openApp(page, "/customers/new", "Neuer Kunde");
  await page.getByLabel("Firmenname").fill(name);
  await page.getByLabel("PLZ").fill("3011");
  await page.getByLabel("Ort").fill("Bern");
  const release = await hold(page, /\/api\/customers$/);

  await page.keyboard.down("ControlOrMeta");
  // Held down, the key repeats; a second press follows while the first save runs.
  await page.keyboard.down("Enter");
  await page.keyboard.down("Enter");
  await page.keyboard.up("Enter");
  await page.keyboard.press("Enter");
  await page.keyboard.up("ControlOrMeta");
  const save = page.getByRole("button", { name: /^Speichern/ });
  await expect.soft(save).toBeDisabled();
  await expect.soft(save).toHaveAttribute("aria-busy", "true");
  release();

  await expect(page.getByText(`Kunde «${name}» angelegt.`)).toBeVisible();
  const found = await page.request.get(`/api/customers?q=${encodeURIComponent(name)}`);
  expect(((await found.json()) as { total: number }).total).toBe(1);
});

test("a partial payment is recorded once, however often it is confirmed", async ({
  page,
}, testInfo) => {
  const customerId = await createCustomer(page, `Zahlt ${unique(testInfo.project.name)} AG`);
  const invoiceId = await issuedInvoice(page, customerId);
  await page.goto(`/documents/${invoiceId}`);
  await page.getByRole("button", { name: "Zahlung erfassen" }).click();
  const dialog = page.getByRole("dialog", { name: "Zahlung erfassen" });
  const amount = dialog.getByLabel("Betrag in CHF");
  await amount.fill("50");
  const release = await hold(page, /\/payments$/);

  await amount.press("Enter");
  await amount.press("Enter");
  await expect.soft(dialog.getByRole("button", { name: "Zahlung speichern" })).toBeDisabled();
  release();
  // The payment is recorded and the dialog closes: while it fades out, the amount field
  // still has the focus, and Enter must record nothing more.
  await expect(page.getByText("Zahlung über CHF 50.00 erfasst.")).toBeVisible();
  await page.keyboard.press("Enter");
  await page.keyboard.press("Enter");
  await expect(dialog).toBeHidden();
  await expect(page.getByText("Zahlung über CHF 50.00 erfasst.")).toHaveCount(1);
  const invoice = await page.request.get(`/api/documents/${invoiceId}`);
  expect(((await invoice.json()) as { payments: unknown[] }).payments).toHaveLength(1);
});

test("a document is duplicated once while the copy is being made", async ({ page }, testInfo) => {
  const customerId = await createCustomer(page, `Kopie ${unique(testInfo.project.name)} AG`);
  const draft = await post<{ id: string }>(page, "/api/documents", {
    type: "invoice",
    customer_id: customerId,
    lines: [{ description: "Beratung", quantity: "1", unit_price: "100" }],
  });
  await page.goto(`/documents/${draft.id}`);
  await expect(page.getByRole("heading", { level: 1, name: "Rechnung (Entwurf)" })).toBeVisible();
  const release = await hold(page, /\/duplicate$/);

  await page.getByRole("button", { name: "Weitere Aktionen" }).click();
  await page.getByRole("menuitem", { name: "Duplizieren" }).click();
  // Opened again while the copy is made: the actions wait for it.
  await page.getByRole("button", { name: "Weitere Aktionen" }).click();
  await expect(page.getByRole("menuitem", { name: "Duplizieren" })).toBeDisabled();
  await page.keyboard.press("Escape");
  release();

  await expect(page.getByText("Kopie als Entwurf erstellt.")).toBeVisible();
  expect(await documentsOf(page, customerId)).toBe(2);
});

test("an invoice is cancelled once, however often the dialog is confirmed", async ({
  page,
}, testInfo) => {
  const customerId = await createCustomer(page, `Storno ${unique(testInfo.project.name)} AG`);
  const invoiceId = await issuedInvoice(page, customerId);
  await page.goto(`/documents/${invoiceId}`);
  await page.getByRole("button", { name: "Weitere Aktionen" }).click();
  await page.getByRole("menuitem", { name: "Stornieren" }).click();
  const confirm = page.getByRole("alertdialog", { name: "Rechnung stornieren?" });
  // Several clicks at once, while the dialog closes.
  await confirm.getByRole("button", { name: "Stornieren" }).click({ clickCount: 3 });

  await expect(page.getByRole("heading", { level: 1, name: /^Stornorechnung \S+$/ })).toBeVisible();
  await expect(page.getByText("Rechnung storniert, Stornorechnung ausgestellt.")).toBeVisible();
  // No second attempt, neither as a cancellation nor as a deletion.
  await expect(page.locator("[data-sonner-toast][data-type='error']")).toHaveCount(0);
  expect(await documentsOf(page, customerId)).toBe(2);
});

test("a document is printed once per click", async ({ page }, testInfo) => {
  const customerId = await createCustomer(page, `Druck ${unique(testInfo.project.name)} AG`);
  const invoiceId = await issuedInvoice(page, customerId);
  await page.goto(`/documents/${invoiceId}`);
  // Count the print frames: one per printing (headless, print() opens no dialog).
  await page.evaluate(() => {
    const counter = window as unknown as { printFrames: number };
    counter.printFrames = 0;
    new MutationObserver((changes) => {
      for (const change of changes) {
        for (const node of change.addedNodes) {
          if (node instanceof HTMLIFrameElement && node.hasAttribute("srcdoc")) {
            counter.printFrames += 1;
          }
        }
      }
    }).observe(document.body, { childList: true });
  });
  const release = await hold(page, /\/html$/, "GET");

  const print = page.getByRole("button", { name: "Drucken" });
  await print.click();
  await expect(print).toBeDisabled();
  release();
  await expect
    .poll(() => page.evaluate(() => (window as unknown as { printFrames: number }).printFrames))
    .toBe(1);
  await expect(print).toBeEnabled();
});

test("a mail goes out once, also when its dialog is closed and opened again", async ({
  page,
}, testInfo) => {
  const suffix = unique(testInfo.project.name);
  await page.goto("/settings?tab=mail");
  await page.getByLabel("Server", { exact: true }).fill("mailpit");
  await page.getByLabel("Verschlüsselung").selectOption("none");
  await page.getByLabel("Port").fill("1025");
  await page.getByLabel("Absenderadresse", { exact: true }).fill("rechnung@muster.example");
  await page.getByRole("button", { name: "Speichern" }).first().click();
  await expect(page.getByText("Gespeichert", { exact: true })).toBeVisible();
  const customerId = await createCustomer(page, `Post ${suffix} AG`);
  const invoiceId = await issuedInvoice(page, customerId);
  await page.goto(`/documents/${invoiceId}`);

  const to = `einmal-${suffix}@kunde.example`;
  await page.getByRole("button", { name: "Per E-Mail senden" }).click();
  let dialog = page.getByRole("dialog", { name: /per E-Mail senden$/ });
  await dialog.getByLabel("An", { exact: true }).fill(to);
  const release = await hold(page, /\/mail$/);
  await dialog.getByRole("button", { name: "Senden" }).click();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();

  // Opened again while the first mail goes out: it cannot be sent a second time.
  await page.getByRole("button", { name: "Per E-Mail senden" }).click();
  dialog = page.getByRole("dialog", { name: /per E-Mail senden$/ });
  await expect(dialog.getByRole("button", { name: "Wird gesendet …" })).toBeDisabled();
  release();
  await expect(page.getByText(`E-Mail an ${to} gesendet.`)).toBeVisible();

  const query = encodeURIComponent(`to:${to}`);
  await expect
    .poll(async () => {
      const response = await page.request.get(`${MAILPIT}/api/v1/search?query=${query}`);
      return ((await response.json()) as { messages: unknown[] }).messages.length;
    })
    .toBe(1);
});

test("a save whose answer was lost creates nothing twice when it is tried again", async ({
  page,
}, testInfo) => {
  const name = `Funkloch ${unique(testInfo.project.name)} AG`;
  await openApp(page, "/customers/new", "Neuer Kunde");
  await page.getByLabel("Firmenname").fill(name);
  await page.getByLabel("PLZ").fill("3011");
  await page.getByLabel("Ort").fill("Bern");
  // The first request reaches the server, which saves the customer; its answer is lost.
  const keys: (string | undefined)[] = [];
  let lost = false;
  await page.route(/\/api\/customers$/, async (route) => {
    if (route.request().method() !== "POST") {
      await route.continue();
      return;
    }
    keys.push(route.request().headers()["idempotency-key"]);
    if (lost) {
      await route.continue();
      return;
    }
    lost = true;
    await route.fetch();
    await route.abort("connectionreset");
  });
  const save = page.getByRole("button", { name: /^Speichern/ });
  await save.click();
  await expect(
    page.getByText("Keine Verbindung zum Server.", { exact: false }).first(),
  ).toBeVisible();

  const replayed = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/customers") && response.request().method() === "POST",
  );
  await save.click();
  expect((await replayed).headers()["idempotent-replayed"]).toBe("true");
  await expect(page.getByText(`Kunde «${name}» angelegt.`)).toBeVisible();
  // The same intent carried the same key; the server answered from the first request.
  expect(keys).toHaveLength(2);
  expect(keys[0]).toMatch(/^[0-9a-f-]{36}$/);
  expect(keys[1]).toBe(keys[0]);
  const found = await page.request.get(`/api/customers?q=${encodeURIComponent(name)}`);
  expect(((await found.json()) as { total: number }).total).toBe(1);
});
