import { expect, test as setup, type Page } from "@playwright/test";

import {
  ADMIN,
  createCustomer,
  expectAccessible,
  HEADERS,
  isoDaysFromToday,
  OVERDUE_CUSTOMER,
  post,
} from "./fixtures";

const authFile = "e2e/.auth/user.json";

setup("create the first user or log in", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/(setup|login)/);
  if (page.url().includes("/setup")) {
    await expect(
      page.getByRole("heading", { level: 1, name: "Rhinvoice einrichten" }),
    ).toBeVisible();
    await expectAccessible(page);
    await page.getByLabel("Ihr Name").fill(ADMIN.name);
    await page.getByLabel("E-Mail-Adresse").fill(ADMIN.email);
    await page.getByLabel("Passwort").fill(ADMIN.password);
    await page.getByRole("button", { name: "Konto anlegen" }).click();
    // First start: the wizard asks for the country and the company.
    await expect(page).toHaveURL(/\/welcome$/);
    await expect(page.getByRole("heading", { level: 1, name: "Wo ist Ihre Firma?" })).toBeVisible();
    await expect(page.getByRole("radio", { name: /^Schweiz/ })).toBeChecked();
    await expectAccessible(page);
    await page.getByRole("button", { name: "Weiter" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Ihre Firma" })).toBeVisible();
    await page.getByRole("button", { name: "Speichern und weiter" }).click();
    await expect(page.getByLabel("Firmenname")).toHaveAttribute("aria-invalid", "true");
    await page.getByLabel("Firmenname").fill("Muster GmbH");
    await page.getByLabel("Strasse").fill("Bahnhofstrasse");
    await page.getByLabel(/^Nr\./).fill("1");
    await page.getByLabel("PLZ").fill("8001");
    await page.getByLabel("Ort").fill("Zürich");
    await page.getByLabel("UID / MWST-Nummer").fill("CHE-123.456.788");
    await expectAccessible(page);
    await page.getByRole("button", { name: "Speichern und weiter" }).click();
  } else {
    await page.getByLabel("E-Mail-Adresse").fill(ADMIN.email);
    await page.getByLabel("Passwort").fill(ADMIN.password);
    await page.getByRole("button", { name: "Anmelden" }).click();
  }
  await expect(page.getByRole("heading", { level: 1, name: "Übersicht" })).toBeVisible();
  await page.context().storageState({ path: authFile });
  await seedOverdueInvoice(page);
});

/**
 * One overdue invoice for list and dashboard tests. Documents cannot be dated
 * before the last issued one, so it is issued here, before any other test.
 */
async function seedOverdueInvoice(page: Page): Promise<void> {
  const existing = await page.request.get("/api/documents?q=saumselig&type=invoice&status=overdue");
  if (((await existing.json()) as { total: number }).total > 0) return;
  if ((await page.request.get("/api/company")).status() === 404) {
    const company = {
      name: "Muster GmbH",
      address: {
        street: "Bahnhofstrasse",
        house_number: "1",
        postal_code: "8001",
        city: "Zürich",
        country: "CH",
      },
      default_currency: "CHF",
      vat_number: "CHE-123.456.788",
    };
    const saved = await page.request.put("/api/company", { data: company, headers: HEADERS });
    expect(saved.ok()).toBe(true);
  }
  // The 5-centime rounding is off for new companies; the Swiss test company uses it.
  const company = (await (await page.request.get("/api/company")).json()) as Record<
    string,
    unknown
  >;
  if (company.cash_rounding !== true) {
    const rounded = await page.request.put("/api/company", {
      // The response carries derived fields the request does not take.
      data: {
        ...company,
        id: undefined,
        country: undefined,
        profile: undefined,
        cash_rounding: true,
      },
      headers: HEADERS,
    });
    expect(rounded.ok(), await rounded.text()).toBe(true);
  }
  const accounts = (await (await page.request.get("/api/bank-accounts")).json()) as unknown[];
  if (accounts.length === 0) {
    await post(page, "/api/bank-accounts", {
      currency: "CHF",
      bank_name: "Musterbank",
      holder: "Muster GmbH",
      iban: "CH93 0076 2011 6238 5295 7",
    });
  }
  const customerId = await createCustomer(page, OVERDUE_CUSTOMER);
  // One overdue invoice per project for the dunning test (reminders change it).
  for (const project of ["desktoplight", "desktopdark", "mobilelight", "mobiledark"]) {
    const dunned = await createCustomer(page, `Mahnkunde ${project} AG`);
    const late = await post<{ id: string }>(page, "/api/documents", {
      type: "invoice",
      customer_id: dunned,
      issue_date: isoDaysFromToday(-40),
      due_date: isoDaysFromToday(-20),
      lines: [{ description: "Wartung", quantity: "2", unit: "HUR", unit_price: "100" }],
    });
    await post(page, `/api/documents/${late.id}/issue`, {});
  }
  const invoice = await post<{ id: string }>(page, "/api/documents", {
    type: "invoice",
    customer_id: customerId,
    subject: "Altlast",
    issue_date: isoDaysFromToday(-40),
    due_date: isoDaysFromToday(-10),
    lines: [{ description: "Beratung", quantity: "4", unit: "HUR", unit_price: "150" }],
  });
  await post(page, `/api/documents/${invoice.id}/issue`, {});
}
