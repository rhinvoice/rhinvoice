import type { Download, Page } from "@playwright/test";

import {
  createCustomer,
  expect,
  expectAccessible,
  expectDocumentAccessible,
  OVERDUE_CUSTOMER,
  openApp,
  post,
  test,
  unique,
  waitForToastsToClose,
} from "./fixtures";

test.describe.configure({ mode: "serial" });

test("create, issue, pay and cancel an invoice", async ({ page, isMobile }, testInfo) => {
  // The whole life of an invoice in one test: more time than the default.
  test.setTimeout(90_000);
  const suffix = unique(testInfo.project.name);
  const customerName = `Rechnungskunde ${suffix} AG`;
  await createCustomer(page, customerName);
  await post(page, "/api/articles", {
    name: `Wartung ${suffix}`,
    unit: "HUR",
    prices: { CHF: "120" },
  });

  await openApp(page, "/invoices", "Rechnungen");
  await page
    .getByRole("link", { name: /Neue Rechnung/ })
    .first()
    .click();
  await expect(page.getByRole("heading", { level: 1, name: "Neue Rechnung" })).toBeVisible();

  // Saving without a customer and description shows the error summary.
  await page.getByRole("button", { name: "Speichern" }).click();
  const summary = page.getByRole("alert").filter({ hasText: "korrigiert werden" });
  await expect(summary).toBeFocused();
  await expect(summary.getByRole("link", { name: "Bitte wählen Sie einen Kunden." })).toBeVisible();
  await expect(summary.getByRole("link", { name: "Position 1: Bitte ausfüllen." })).toBeVisible();
  await expectAccessible(page);

  // Customer search (umlaut-tolerant on the server); the chosen customer shows as a card.
  await page.getByRole("combobox", { name: "Kunde suchen" }).fill(`rechnungskunde ${suffix}`);
  await page.getByRole("option", { name: new RegExp(customerName) }).click();
  const customerCard = page.getByRole("region", { name: "Kunde" });
  await expect(customerCard.getByText(customerName)).toBeVisible();
  await expect(page.getByRole("combobox", { name: "Kunde suchen" })).toHaveCount(0);

  // Article autocomplete in the first line fills price and unit; "Übernehmen" closes it.
  const firstLine = page.locator("#lines-0-description");
  await firstLine.fill(`Wartung ${suffix}`);
  await page.getByRole("option", { name: new RegExp(`Wartung ${suffix}`) }).click();
  await expect(page.locator("#lines-0-unit_price")).toHaveValue("120.00");
  await expect(page.locator("#lines-0-unit")).toHaveValue("HUR");
  await page.locator("#lines-0-quantity").fill("2");
  await page.getByRole("button", { name: "Übernehmen" }).click();
  await expect(page.locator("#lines-0-description")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: `Position 1 bearbeiten: Wartung ${suffix}` }),
  ).toBeFocused();

  // ↵ applies a line, too.
  await page.getByRole("button", { name: "Textzeile hinzufügen" }).click();
  await expect(page.locator("#lines-1-description")).toBeFocused();
  await page.locator("#lines-1-description").fill("Spesen");
  await page.locator("#lines-1-description").press("Enter");
  await page.getByRole("button", { name: "Position hinzufügen" }).click();
  await page.locator("#lines-2-description").fill("Fahrtkosten");
  await page.locator("#lines-2-unit_price").fill("35.50");
  await page.getByRole("button", { name: "Übernehmen" }).click();

  // Live totals and page from the server: 240.00 + 35.50 net, 8.1 % VAT, rounded to 0.05.
  await expect(page.getByText("CHF 297.80")).toBeVisible();
  if (isMobile) await page.getByRole("button", { name: "Vorschau" }).click();
  const paper = page.frameLocator('iframe[title="Vorschau: Rechnung"]');
  await expect(paper.getByText("MWST 8.1\u00a0% auf 275.50")).toBeVisible();
  await expect(paper.getByText(`Wartung ${suffix}`)).toBeVisible();
  if (isMobile) {
    await page.getByRole("button", { name: "Bearbeiten" }).click();
  } else {
    // A click on a line of the paper opens it for editing; Esc closes it unchanged.
    await paper.locator('tr[data-index="2"]').click();
    await expect(page.locator("#lines-2-description")).toBeFocused();
    await page.locator("#lines-2-description").press("Escape");
    await expect(page.locator("#lines-2-description")).toHaveCount(0);

    // Alt+↑ moves the travel costs above the text line (WCAG 2.5.7).
    await page
      .getByRole("button", { name: "Position 3 bearbeiten: Fahrtkosten" })
      .press("Alt+ArrowUp");
    await expect(
      page.getByRole("button", { name: "Position 2 bearbeiten: Fahrtkosten" }),
    ).toBeFocused();

    // Dragging a line onto another moves it there (and back here).
    await page
      .getByRole("button", { name: "Position 2 bearbeiten: Fahrtkosten" })
      .dragTo(page.getByRole("button", { name: /^Position 1 bearbeiten: Wartung/ }));
    await expect(
      page.getByRole("button", { name: "Position 1 bearbeiten: Fahrtkosten" }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "Position 1 bearbeiten: Fahrtkosten" })
      .dragTo(page.getByRole("button", { name: /^Position 2 bearbeiten: Wartung/ }));
    await expect(
      page.getByRole("button", { name: "Position 2 bearbeiten: Fahrtkosten" }),
    ).toBeVisible();
  }

  // The texts come from the templates; payment terms switch on and off.
  await page.getByText("Texte", { exact: true }).click();
  await expect(page.locator("#payment_text")).toHaveValue(/Zahlbar bis \{faellig\}\./);
  await page.getByRole("button", { name: "Zahlbar prompt ohne Abzug" }).click();
  await expect(page.locator("#payment_text")).toHaveValue(/Zahlbar prompt und ohne Abzug\./);
  await expectAccessible(page);
  await expect(page).toHaveScreenshot("invoice-editor.png", {
    // The customer number, the draft dates and the texts' order depend on other tests.
    mask: [customerCard, paper.locator(".meta")],
  });

  // ⌘↵ / Ctrl+↵ saves the draft; the editor continues on the draft's page.
  await page.keyboard.press("ControlOrMeta+Enter");
  await expect(page.getByRole("heading", { level: 1, name: "Rechnung (Entwurf)" })).toBeVisible();
  await expect(page.getByText("Entwurf gespeichert.")).toBeVisible();

  await page.getByRole("button", { name: "Ausstellen" }).click();
  const confirm = page.getByRole("alertdialog", { name: "Rechnung ausstellen?" });
  await expect(confirm).toBeVisible();
  await expectAccessible(page);
  await confirm.getByRole("button", { name: "Ausstellen" }).click();

  await expect(page.getByText(/^Rechnung .+ ausgestellt\.$/)).toBeVisible();
  const heading = page.getByRole("heading", { level: 1, name: /^Rechnung \S+$/ });
  await expect(heading).toBeVisible();
  await expect(page.getByText("Ausgestellt", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("textbox")).toHaveCount(0);
  // Issued documents open as paper.
  const issued = page.frameLocator('iframe[title^="Rechnung "]');
  await expect(issued.getByText("Fahrtkosten")).toBeVisible();
  await expectAccessible(page);
  await waitForToastsToClose(page);
  // The accessibility check scrolls through the page; the screenshot starts at the top.
  await page.evaluate(() => {
    window.scrollTo(0, 0);
    for (const element of document.querySelectorAll("*")) {
      if (element.scrollTop > 0) element.scrollTop = 0;
    }
  });
  await expect(page).toHaveScreenshot("invoice-issued.png", {
    // Number and dates depend on the day and on earlier tests.
    mask: [page.locator("h1"), issued.locator(".meta"), issued.locator("h1")],
  });
  await expectDocumentAccessible(page, page.url().split("/").at(-1) ?? "");

  // The PDF comes from Gotenberg and is archived: the second request gets the same file.
  const documentId = page.url().split("/").at(-1) ?? "";
  const pdfUrl = `/api/documents/${documentId}/pdf`;
  const first = await page.request.get(pdfUrl);
  expect(first.status()).toBe(200);
  expect(first.headers()["content-type"]).toBe("application/pdf");
  const body = await first.body();
  expect(body.subarray(0, 5).toString()).toBe("%PDF-");
  // The invoice fits one page; the Swiss QR-bill follows on a page of its own.
  expect(body.toString("latin1").match(/\/Type\s*\/Page(?!s)/g)).toHaveLength(2);
  const second = await page.request.get(pdfUrl);
  expect((await second.body()).equals(body)).toBe(true);
  expect(second.headers().etag).toBe(first.headers().etag);
  // Headless Chromium has no PDF viewer: the new tab receives the PDF as a download. The
  // archived PDF comes at once, so listen for it as soon as the tab exists.
  const shown = new Promise<{ popup: Page; download: Download }>((resolve) => {
    page.once("popup", (popup) => {
      popup.once("download", (download) => {
        resolve({ popup, download });
      });
    });
  });
  await page.getByRole("button", { name: /^PDF/ }).click();
  const { popup, download: opened } = await shown;
  expect(await opened.failure()).toBeNull();
  await popup.close();
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "Herunterladen" }).click(),
  ]);
  expect(download.suggestedFilename()).toMatch(/^Rechnung \S+\.pdf$/);

  await page.getByRole("button", { name: "Details" }).click();
  await expect(page.getByRole("button", { name: "Details" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  // The archived PDF is a ZUGFeRD e-invoice; an XRechnung would need more details.
  const eInvoice = page.getByRole("region", { name: "E-Rechnung" });
  await expect(eInvoice).toContainText("Das PDF enthält die E-Rechnung (ZUGFeRD, EN 16931)");
  await eInvoice.getByText("XRechnung für deutsche Behörden").click();
  await expect(eInvoice).toContainText("Für eine XRechnung fehlte beim Ausstellen:");
  await expect(eInvoice.getByRole("listitem")).toContainText([
    "Leitweg-ID beim Kunden oder Referenz der Rechnung",
  ]);

  // Partial payment.
  await page.getByRole("button", { name: "Zahlung erfassen" }).click();
  const dialog = page.getByRole("dialog", { name: "Zahlung erfassen" });
  await expect(dialog.getByLabel("Betrag in CHF")).toHaveValue("297.80");
  await dialog.getByLabel("Betrag in CHF").fill("400");
  await dialog.getByRole("button", { name: "Zahlung speichern" }).click();
  await expect(
    dialog.getByText("Der Betrag ist höher als der offene Betrag von CHF 297.80."),
  ).toBeVisible();
  await expectAccessible(page);
  await dialog.getByLabel("Betrag in CHF").fill("97.80");
  await dialog.getByRole("button", { name: "Zahlung speichern" }).click();
  await expect(page.getByText("Zahlung über CHF 97.80 erfasst.")).toBeVisible();
  await expect(page.getByText("Teilweise bezahlt", { exact: true }).first()).toBeVisible();

  // Mark as paid, then undo.
  await page.getByRole("button", { name: "Als bezahlt markieren" }).click();
  await expect(page.getByText("Als bezahlt markiert.")).toBeVisible();
  await expect(page.getByText("Bezahlt", { exact: true }).first()).toBeVisible();
  if (isMobile) {
    await page
      .locator("[data-sonner-toast]")
      .filter({ hasText: "Als bezahlt markiert." })
      .getByRole("button", { name: "Rückgängig" })
      .click();
  } else {
    // ⌘Z / Ctrl+Z triggers the undo of the visible toast.
    await page.locator("body").press("ControlOrMeta+z");
  }
  await expect(page.getByText("Teilweise bezahlt", { exact: true }).first()).toBeVisible();

  // Removing a payment can be undone as well.
  await page.getByRole("button", { name: /^Zahlung über CHF 97\.80 vom .+ entfernen$/ }).click();
  await expect(page.getByText("Zahlung entfernt.")).toBeVisible();
  await expect(page.getByText("Ausgestellt", { exact: true }).first()).toBeVisible();
  await page
    .locator("[data-sonner-toast]")
    .filter({ hasText: "Zahlung entfernt." })
    .getByRole("button", { name: "Rückgängig" })
    .click();
  await expect(page.getByText("Teilweise bezahlt", { exact: true }).first()).toBeVisible();

  // Cancellation issues a cancellation invoice with its own number.
  await page.getByRole("button", { name: "Weitere Aktionen" }).click();
  await page.getByRole("menuitem", { name: "Stornieren" }).click();
  const cancel = page.getByRole("alertdialog", { name: "Rechnung stornieren?" });
  await cancel.getByRole("button", { name: "Stornieren" }).click();
  await expect(page.getByRole("heading", { level: 1, name: /^Stornorechnung \S+$/ })).toBeVisible();
  await expect(page.getByText("CHF-297.80").first()).toBeVisible();
  // A cancellation reverses its invoice: nobody pays it.
  await expect(page.getByRole("button", { name: "Als bezahlt markieren" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Zahlung erfassen" })).toHaveCount(0);
  await page.getByRole("link", { name: "Stornierte Rechnung öffnen" }).click();
  await expect(page.getByText("Storniert", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Zahlung erfassen" })).toHaveCount(0);
  await expectAccessible(page);
});

test("a quote is sent, accepted and turned into an invoice", async ({ page }, testInfo) => {
  const suffix = unique(testInfo.project.name);
  const customerId = await createCustomer(page, `Angebotskunde ${suffix}`);
  const quote = await post<{ id: string }>(page, "/api/documents", {
    type: "quote",
    customer_id: customerId,
    subject: "Neue Website",
    lines: [{ description: "Konzept", quantity: "1", unit: "LS", unit_price: "2500" }],
  });

  await page.goto(`/documents/${quote.id}`);
  await expect(page.getByRole("heading", { level: 1, name: "Angebot (Entwurf)" })).toBeVisible();
  await page.getByRole("button", { name: "Als versendet markieren" }).click();
  await page
    .getByRole("alertdialog", { name: "Angebot als versendet markieren?" })
    .getByRole("button", { name: "Als versendet markieren" })
    .click();
  await expect(page.getByRole("heading", { level: 1, name: /^Angebot \S+$/ })).toBeVisible();
  await page.getByRole("button", { name: "Angenommen" }).click();
  await expect(page.getByText("Angebot als angenommen markiert.")).toBeVisible();

  await page.getByRole("button", { name: "Weitere Aktionen" }).click();
  await page.getByRole("menuitem", { name: "In Rechnung umwandeln" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Rechnung (Entwurf)" })).toBeVisible();
  await expect(page.locator("#subject")).toHaveValue("Neue Website");
  await expect(page.getByRole("button", { name: "Position 1 bearbeiten: Konzept" })).toBeVisible();
  await expectAccessible(page);

  // The quote links to its invoice and cannot be converted a second time.
  await page.getByRole("link", { name: "Ursprungsdokument öffnen" }).click();
  await expect(page.getByRole("heading", { level: 1, name: /^Angebot \S+$/ })).toBeVisible();
  await expect(page.getByRole("link", { name: "Rechnung öffnen" })).toBeVisible();
  await page.getByRole("button", { name: "Weitere Aktionen" }).click();
  await expect(page.getByRole("menuitem", { name: "Duplizieren" })).toBeVisible();
  await expect(page.getByRole("menuitem", { name: "In Rechnung umwandeln" })).toHaveCount(0);
  await page.keyboard.press("Escape");
});

test("issuing without a bank account points to it; the draft saves and can be deleted", async ({
  page,
}, testInfo) => {
  const suffix = unique(testInfo.project.name);
  const customerName = `Euro ${suffix} GmbH`;
  await createCustomer(page, customerName);
  await openApp(page, "/invoices/new", "Neue Rechnung");
  await page.getByRole("combobox", { name: "Kunde suchen" }).fill(customerName);
  await page.getByRole("option", { name: new RegExp(customerName) }).click();
  await page.getByText("Weitere Angaben", { exact: true }).click();
  await page.getByLabel("Währung").selectOption("EUR");
  await page.locator("#lines-0-description").fill("Beratung");
  await page.locator("#lines-0-unit_price").fill("100");
  // No EUR account: the editor says so before issuing and leads there instead.
  const missing = page.getByRole("region", { name: "Vor dem Ausstellen fehlt noch:" });
  await expect(missing.getByText("ein Bankkonto in EUR für die Zahlungsangaben")).toBeVisible();
  await page.getByRole("button", { name: "Ausstellen" }).click();
  await expect(missing).toBeFocused();
  await expect(page.getByRole("alertdialog", { name: "Rechnung ausstellen?" })).toBeHidden();
  await expectAccessible(page);

  // Saving still works.
  await page.getByRole("button", { name: "Speichern" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Rechnung (Entwurf)" })).toBeVisible();
  await expect(page).toHaveURL(/\/documents\/[0-9a-f-]{36}$/);

  await page.getByRole("button", { name: "Weitere Aktionen" }).click();
  await page.getByRole("menuitem", { name: "Entwurf löschen" }).click();
  await page
    .getByRole("alertdialog", { name: "Entwurf löschen?" })
    .getByRole("button", { name: "Löschen" })
    .click();
  await expect(page.getByRole("heading", { level: 1, name: "Rechnungen" })).toBeVisible();
  await expect(page.getByText("Entwurf gelöscht.")).toBeVisible();
});

test("lists filter by view and search, the customer shows its documents", async ({
  page,
}, testInfo) => {
  const suffix = unique(testInfo.project.name);
  const customerName = `Saumselig ${suffix} GmbH`;
  const customerId = await createCustomer(page, customerName);
  await post(page, "/api/documents", {
    type: "invoice",
    customer_id: customerId,
    subject: `Entwurf ${suffix}`,
    lines: [{ description: "Beratung", quantity: "1", unit: "HUR", unit_price: "150" }],
  });

  // The overdue invoice comes from the global setup: documents cannot be
  // backdated before the last issued one, so it is issued before all others.
  await openApp(page, "/invoices", "Rechnungen");
  await page.getByRole("searchbox", { name: "Dokumente durchsuchen" }).fill("saumselig");
  const views = page.getByRole("group", { name: "Ansicht" });
  await views.getByRole("button", { name: /^Überfällig/ }).click();
  await expect(page).toHaveURL(/view=overdue/);
  await expect(page.getByText("1 Treffer")).toBeVisible();
  const row = page.getByRole("row").filter({ hasText: OVERDUE_CUSTOMER });
  await expect(row.getByText("Überfällig · 10 Tage").filter({ visible: true })).toBeVisible();
  await waitForToastsToClose(page);
  await expectAccessible(page);
  await expect(page).toHaveScreenshot("invoice-list.png", {
    // Numbers and dates depend on the day.
    mask: [
      // The counts per view depend on the documents of the other projects.
      views.locator(".tabular-nums"),
      page.locator("tbody td:nth-child(3)"),
      page.locator("tbody td:nth-child(6)"),
      page.locator("tbody td:nth-child(7)"),
    ],
  });

  const search = page.getByRole("searchbox", { name: "Dokumente durchsuchen" });
  await search.fill(`saumselig ${suffix}`);
  await expect(page.getByText("Keine Dokumente für diesen Filter.")).toBeVisible();
  await views.getByRole("button", { name: /^Entwürfe/ }).click();
  await expect(page.getByText("1 Treffer")).toBeVisible();
  await views.getByRole("button", { name: /^Bezahlt/ }).click();
  await expect(page.getByText("Keine Dokumente für diesen Filter.")).toBeVisible();
  await page.getByRole("button", { name: "Filter zurücksetzen" }).click();
  await expect(page).not.toHaveURL(/view=/);

  await page.goto(`/customers/${customerId}`);
  const documents = page.getByRole("region", { name: "Dokumente" });
  await expect(documents.getByRole("listitem")).toHaveCount(1);
  await expect(documents.getByRole("link", { name: "Neue Rechnung" })).toHaveAttribute(
    "href",
    `/invoices/new?customer=${customerId}`,
  );
  await documents.getByRole("listitem").first().getByRole("link").click();
  await expect(page.getByRole("heading", { level: 1, name: /^Rechnung/ })).toBeVisible();
});

test("the invoice list filters by year and customer and marks invoices as paid", async ({
  page,
  isMobile,
}, testInfo) => {
  const suffix = unique(testInfo.project.name);
  const customerName = `Zahlfreudig ${suffix} AG`;
  const customerId = await createCustomer(page, customerName);
  const numbers: string[] = [];
  for (const price of ["100", "200"]) {
    const draft = await post<{ id: string }>(page, "/api/documents", {
      type: "invoice",
      customer_id: customerId,
      lines: [{ description: "Beratung", quantity: "1", unit: "HUR", unit_price: price }],
    });
    const issued = await post<{ number: string }>(page, `/api/documents/${draft.id}/issue`, {});
    numbers.push(issued.number);
  }
  const [first = "", second = ""] = numbers;
  const year = first.slice(1, 5);

  await openApp(page, "/invoices", "Rechnungen");
  const filters = page.getByRole("search", { name: "Filter" });
  await filters.getByRole("combobox", { name: "Kunde" }).fill(`zahlfreudig ${suffix}`);
  await page.getByRole("option", { name: new RegExp(customerName) }).click();
  await expect(page).toHaveURL(new RegExp(`customer=${customerId}`));
  await filters.getByLabel("Jahr").selectOption(year);
  await expect(page).toHaveURL(new RegExp(`year=${year}`));
  await expect(page.getByText("2 Treffer")).toBeVisible();
  const sums = page.getByRole("region", { name: "Summen" });
  await expect(sums).toContainText("2 Rechnungen in CHF");
  await expect(sums).toContainText("Total CHF 324.30");

  // One click pays an invoice in full; the toast can undo it.
  await page
    .getByRole("button", { name: `${first} als bezahlt markieren (heute, voller Betrag)` })
    .filter({ visible: true })
    .click();
  const toastMessage = page
    .locator("[data-sonner-toast]")
    .filter({ hasText: `${first} als bezahlt markiert` });
  await expect(toastMessage).toBeVisible();
  const firstRow = page.getByRole("row").filter({ hasText: first });
  await expect(firstRow.getByText("Bezahlt").filter({ visible: true }).first()).toBeVisible();
  await toastMessage.getByRole("button", { name: "Rückgängig" }).click();
  await expect(page.getByText("Zahlungen entfernt")).toBeVisible();
  await expect(
    page
      .getByRole("button", { name: `${first} als bezahlt markieren (heute, voller Betrag)` })
      .filter({ visible: true }),
  ).toBeVisible();

  if (!isMobile) {
    // Several at once: tick them and pay the selection.
    await page.getByRole("checkbox", { name: `${first} auswählen` }).check();
    await page.getByRole("checkbox", { name: `${second} auswählen` }).check();
    const selection = page.getByRole("region", { name: "Auswahl", exact: true });
    await expect(selection).toContainText("2 ausgewählt");
    await expect(selection).toContainText("CHF 324.30");
    await waitForToastsToClose(page);
    await expectAccessible(page);
    await selection.getByRole("button", { name: "Als bezahlt markieren" }).click();
    await expect(page.getByText("2 Rechnungen als bezahlt markiert")).toBeVisible();
    await expect(selection).toBeHidden();
    await expect(sums).toContainText("davon offen CHF 0.00");
  }
});

test("the dashboard summarises open and overdue invoices", async ({ page }) => {
  await openApp(page, "/", "Übersicht");
  await expect(page.getByRole("region", { name: "Kennzahlen in CHF" })).toBeVisible();
  await expect(page.getByText(/überfällige Rechnung/).first()).toBeVisible();
  await expect(page.getByRole("figure", { name: "Umsatz in CHF" })).toBeVisible();
  await expect(page.getByRole("figure", { name: "Erwartete Zahlungen" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Offen nach Fälligkeit" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Letzte Aktivitäten" })).toBeVisible();
  await expectAccessible(page);
  await page.getByRole("link", { name: "Offene Rechnungen" }).click();
  await expect(page).toHaveURL(/\/invoices\?view=open/);
});

test("N opens a new invoice and Q a new quote", async ({ page, isMobile }) => {
  test.skip(isMobile, "keyboard shortcuts are a desktop feature");
  await openApp(page, "/", "Übersicht");
  await page.keyboard.press("n");
  await expect(page.getByRole("heading", { level: 1, name: "Neue Rechnung" })).toBeVisible();
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "Übersicht" })).toBeVisible();
  await page.keyboard.press("q");
  await expect(page.getByRole("heading", { level: 1, name: "Neues Angebot" })).toBeVisible();
});

test("the editor points out a missing VAT number of an EU business", async ({ page }, testInfo) => {
  const suffix = unique(testInfo.project.name);
  const name = `Ohne UID ${suffix} GmbH`;
  const customer = await post<{ id: string }>(page, "/api/customers", {
    kind: "company",
    company_name: name,
    address: { postal_code: "6850", city: "Dornbirn", country: "AT" },
  });
  const draft = await post<{ id: string }>(page, "/api/documents", {
    type: "invoice",
    customer_id: customer.id,
    lines: [{ description: "Beratung", quantity: "1", unit_price: "100" }],
  });
  await page.goto(`/documents/${draft.id}`);
  const hint = page.getByText(/hat aber keine UID/);
  await expect(hint).toBeVisible();
  await expect(hint).toContainText("ohne: Export (steuerfrei)");
  await expectAccessible(page);
  await expect(
    page.getByRole("link", { name: "UID / USt-IdNr. beim Kunden erfassen" }),
  ).toHaveAttribute("href", `/customers/${customer.id}`);
});

test("German customers: Leitweg-ID, reference hint and XRechnung warning before issuing", async ({
  page,
}, testInfo) => {
  const suffix = unique(testInfo.project.name);
  const customer = await post<{ id: string }>(page, "/api/customers", {
    kind: "company",
    company_name: `Bezirksamt ${suffix}`,
    address: { postal_code: "10115", city: "Berlin", country: "DE" },
  });
  const draft = await post<{ id: string }>(page, "/api/documents", {
    type: "invoice",
    customer_id: customer.id,
    lines: [{ description: "Beratung", quantity: "1", unit_price: "100" }],
  });
  await page.goto(`/documents/${draft.id}`);
  await page.getByText("Weitere Angaben", { exact: true }).click();
  await expect(page.getByText("Bestellnummer o. ä. – nötig für die XRechnung")).toBeVisible();

  // The warning comes before the invoice is frozen; issuing stays possible.
  await page.getByRole("button", { name: "Ausstellen" }).click();
  const confirm = page.getByRole("alertdialog", { name: "Rechnung ausstellen?" });
  await expect(confirm.getByText("Für die XRechnung (deutsche Behörden) fehlt:")).toBeVisible();
  await expect(
    confirm.getByText("Leitweg-ID beim Kunden oder Referenz der Rechnung"),
  ).toBeVisible();
  await expect(confirm.getByRole("button", { name: "Ausstellen" })).toBeEnabled();
  await expectAccessible(page);
  await confirm.getByRole("button", { name: "Abbrechen" }).click();

  // The Leitweg-ID belongs to the customer; the field is shown for German customers only.
  await page.goto(`/customers/${customer.id}`);
  const leitwegId = page.getByLabel("Leitweg-ID oder feste Käuferreferenz");
  await leitwegId.fill("04011000-1234512345-06");
  await page.getByRole("button", { name: "Speichern" }).click();
  await expect(page.getByText("Gespeichert", { exact: true })).toBeVisible();
  await expectAccessible(page);
  const country = page.getByLabel("Land").first();
  await country.selectOption("CH");
  await expect(leitwegId).toBeHidden();
  await country.selectOption("DE");
  await expect(leitwegId).toHaveValue("04011000-1234512345-06");

  await page.goto(`/documents/${draft.id}`);
  await page.getByText("Weitere Angaben", { exact: true }).click();
  await expect(
    page.getByText("Für die XRechnung gilt die Leitweg-ID des Kunden: 04011000-1234512345-06"),
  ).toBeVisible();
  await page.getByRole("button", { name: "Ausstellen" }).click();
  await expect(confirm.getByText("E-Mail beim Kunden")).toBeVisible();
  await expect(confirm.getByText("Leitweg-ID beim Kunden oder Referenz der Rechnung")).toBeHidden();
});

test("cancelling the first line of a new invoice discards it without errors", async ({ page }) => {
  await openApp(page, "/invoices/new", "Neue Rechnung");
  // The first line opens blank: "Discard" removes it instead of checking it.
  await page.locator("#lines-0-description").focus();
  await page.getByRole("button", { name: "Verwerfen" }).click();
  await expect(page.locator("#lines-0-description")).toHaveCount(0);
  await expect(page.getByText("Bitte ausfüllen.")).toHaveCount(0);

  // A line added by hand behaves the same, also when the click leaves an empty field.
  await page.getByRole("button", { name: "Position hinzufügen" }).click();
  await expect(page.locator("#lines-0-description")).toBeFocused();
  await page.getByRole("button", { name: "Verwerfen" }).click();
  await expect(page.locator("#lines-0-description")).toHaveCount(0);
  await expect(page.getByText("Bitte ausfüllen.")).toHaveCount(0);
});

test("the PDF goes to the share sheet only where the browser can share files", async ({
  page,
}, testInfo) => {
  const customerId = await createCustomer(page, `Teilkunde ${unique(testInfo.project.name)} AG`);
  const invoice = await post<{ id: string; number: string }>(page, "/api/documents", {
    type: "invoice",
    customer_id: customerId,
    lines: [{ description: "Beratung", quantity: "1", unit: "HUR", unit_price: "100" }],
  });
  const issued = await post<{ number: string }>(page, `/api/documents/${invoice.id}/issue`, {});
  const heading = `Rechnung ${issued.number}`;

  // The test browser has no Web Share API: no button, no replacement.
  await page.goto(`/documents/${invoice.id}`);
  await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
  await expect(page.getByRole("button", { name: "Drucken" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Teilen" })).toHaveCount(0);

  // A phone's browser: the button hands the PDF to the share sheet.
  await page.addInitScript(() => {
    const shared: { name: string; type: string; size: number; title: string }[] = [];
    Object.assign(window, { shared });
    Object.assign(navigator, {
      canShare: (data?: ShareData) => (data?.files ?? []).every((file) => file.type !== ""),
      share: (data: ShareData) => {
        const [file] = data.files ?? [];
        if (file !== undefined) {
          shared.push({
            name: file.name,
            type: file.type,
            size: file.size,
            title: data.title ?? "",
          });
        }
        return Promise.resolve();
      },
    });
  });
  await page.reload();
  const share = page.getByRole("button", { name: "Teilen" });
  await expect(share).toBeEnabled();
  await expectAccessible(page);
  await share.click();
  await expect
    .poll(() => page.evaluate(() => (window as unknown as { shared: unknown[] }).shared))
    .toEqual([
      {
        name: expect.stringMatching(/\.pdf$/) as unknown as string,
        type: "application/pdf",
        size: expect.any(Number) as unknown as number,
        title: heading,
      },
    ]);
});
