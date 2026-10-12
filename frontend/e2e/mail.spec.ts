import type { Page } from "@playwright/test";

import { createCustomer, expect, expectAccessible, post, test, unique } from "./fixtures";

// The mail catcher of the E2E stack (compose.e2e.yml); absent when run without it.
const MAILPIT = process.env.E2E_MAILPIT_URL ?? "http://localhost:8025";

interface MailpitMessage {
  readonly Subject: string;
  readonly Attachments: number;
}

async function mailsTo(page: Page, address: string): Promise<MailpitMessage[]> {
  const query = encodeURIComponent(`to:${address}`);
  const response = await page.request.get(`${MAILPIT}/api/v1/search?query=${query}`);
  const found = (await response.json()) as { messages: MailpitMessage[] };
  return found.messages;
}

async function setUpServer(page: Page): Promise<void> {
  await page.goto("/settings?tab=mail");
  await expect(page.getByRole("tab", { name: "E-Mail", selected: true })).toBeVisible();
  await page.getByLabel("Server", { exact: true }).fill("mailpit");
  await page.getByLabel("Verschlüsselung").selectOption("none");
  await page.getByLabel("Port").fill("1025");
  await page.getByLabel("Absenderadresse", { exact: true }).fill("rechnung@muster.example");
  await page.getByRole("button", { name: "Speichern" }).first().click();
  await expect(page.getByText("Gespeichert", { exact: true })).toBeVisible();
}

test("the mail server is set up and checked with a test mail", async ({ page }, testInfo) => {
  await page.goto("/settings?tab=mail");
  // Wrong entries are marked before anything is saved.
  await page.getByLabel("Server", { exact: true }).fill("");
  await page.getByLabel("Absenderadresse", { exact: true }).fill("rechnung");
  await page.getByRole("button", { name: "Speichern" }).first().click();
  await expect(page.getByText("Bitte prüfen Sie die markierten Angaben.")).toBeVisible();
  await expect(page.getByText("Keine gültige E-Mail-Adresse.")).toBeVisible();
  await expectAccessible(page);

  await setUpServer(page);
  const to = `test-${unique(testInfo.project.name)}@kunde.example`;
  await page.getByLabel("Senden an").fill(to);
  await page.getByRole("button", { name: "Test-E-Mail senden" }).click();
  await expect(page.getByText(`Test-E-Mail an ${to} gesendet.`)).toBeVisible();
  await expect
    .poll(async () => (await mailsTo(page, to)).map((mail) => mail.Subject))
    .toEqual(["Rhinvoice: Test-E-Mail"]);
  await expectAccessible(page);
});

test("an invoice goes out by mail with its PDF", async ({ page }, testInfo) => {
  const suffix = unique(testInfo.project.name);
  await setUpServer(page);
  const customerId = await createCustomer(page, `Mailkunde ${suffix} AG`);
  const invoice = await post<{ id: string }>(page, "/api/documents", {
    type: "invoice",
    customer_id: customerId,
    lines: [{ description: "Beratung", quantity: "2", unit: "HUR", unit_price: "150" }],
  });
  const issued = await post<{ number: string }>(page, `/api/documents/${invoice.id}/issue`, {});

  await page.goto(`/documents/${invoice.id}`);
  await page.getByRole("button", { name: "Per E-Mail senden" }).click();
  const dialog = page.getByRole("dialog", { name: `Rechnung ${issued.number} per E-Mail senden` });
  await expect(dialog.getByLabel("Betreff")).toHaveValue(`Rechnung ${issued.number}`);
  await expect(dialog.getByText(`Rechnung ${issued.number}.pdf`)).toBeVisible();
  await expect(dialog.getByText("Beim Kunden ist keine E-Mail-Adresse hinterlegt.")).toBeVisible();
  await expectAccessible(page);
  // Without a recipient nothing goes out.
  await dialog.getByRole("button", { name: "Senden" }).click();
  await expect(dialog.getByText("Bitte mindestens eine E-Mail-Adresse angeben.")).toBeVisible();

  const to = `buchhaltung-${suffix}@kunde.example`;
  await dialog.getByLabel("An", { exact: true }).fill(to);
  await dialog.getByRole("button", { name: "Senden" }).click();
  await expect(page.getByText(`E-Mail an ${to} gesendet.`)).toBeVisible();
  await expect(dialog).toBeHidden();
  await expect
    .poll(async () => (await mailsTo(page, to)).map((mail) => [mail.Subject, mail.Attachments]))
    .toEqual([[`Rechnung ${issued.number}`, 1]]);

  await page.getByRole("button", { name: "Details" }).click();
  const history = page.getByRole("region", { name: "Verlauf" });
  await expect(history.getByText("Per E-Mail versendet")).toBeVisible();
  await expect(history.getByText(to)).toBeVisible();
});
