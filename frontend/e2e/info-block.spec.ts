import {
  defaultLayout,
  HEADERS,
  createCustomer,
  expect,
  expectAccessible,
  openApp,
  post,
  test,
  unique,
} from "./fixtures";

test("the print template lists the facts top right, with fields for every invoice", async ({
  page,
  isMobile,
}, testInfo) => {
  test.setTimeout(90_000);
  const before = await defaultLayout(page);
  try {
    await page.goto("/settings?tab=print");
    const block = page.getByRole("region", { name: "Angaben oben rechts" });
    const paper = page.frameLocator('iframe[title="Vorschau der Druckvorlage"]');
    await expect(block.getByText("Nummer des Dokuments")).toBeVisible();

    // Hiding the date of supply warns that it is mandatory; it stays shown here.
    const service = block.getByRole("switch", { name: "Leistungsdatum oder -zeitraum anzeigen" });
    await service.click();
    await expect(block.getByRole("note")).toContainText("Pflichtangabe");
    await expectAccessible(page);
    await service.click();
    await expect(block.getByRole("note")).toHaveCount(0);
    // Number and date are always shown.
    await expect(block.getByRole("switch", { name: "Datum anzeigen" })).toHaveCount(0);

    // A reference field of the e-invoice and a field of one's own.
    await block.getByRole("button", { name: "Feld hinzufügen" }).click();
    await page.getByRole("menuitem", { name: /^Projekt/ }).click();
    await expect(block.getByText("Projekt", { exact: true })).toBeVisible();
    await block.getByRole("button", { name: "Feld hinzufügen" }).click();
    await page.getByRole("menuitem", { name: "Eigenes Feld (nur im PDF)" }).click();
    const save = page.getByRole("button", { name: "Speichern" });
    await expect(page.getByText("Jedes eigene Feld braucht eine Bezeichnung.")).toBeVisible();
    await expect(save).toBeDisabled();
    await block.getByRole("textbox", { name: "Bezeichnung von Eigenes Feld" }).fill("Objekt");
    // The project moves up twice, before the date of supply and the reference.
    await block.getByRole("button", { name: "Projekt nach oben" }).click();
    await block.getByRole("button", { name: "Projekt nach oben" }).click();
    await expect(paper.locator("dl.meta")).toBeAttached();
    await expectAccessible(page);
    await save.click();
    await expect(save).toBeDisabled();
    const saved = (await defaultLayout(page)).layout;
    const keys = saved.info_block.map((entry) => entry.key);
    expect(keys.slice(-4, -1)).toEqual(["project", "service_date", "reference"]);
    expect(keys.at(-1)).toMatch(/^custom-[0-9a-f]{8}$/);

    // The invoice asks for the values next to its dates and prints them top right.
    const customerId = await createCustomer(page, `Felder ${unique(testInfo.project.name)} AG`);
    const draft = await post<{ id: string }>(page, "/api/documents", {
      type: "invoice",
      customer_id: customerId,
      lines: [{ description: "Beratung", quantity: "2", unit: "HUR", unit_price: "150" }],
    });
    await openApp(page, `/documents/${draft.id}`, "Rechnung (Entwurf)");
    const dates = page.getByRole("region", { name: "Daten" });
    await dates.getByRole("textbox", { name: "Projekt" }).fill("Website-Redesign");
    await dates.getByRole("textbox", { name: "Objekt" }).fill("Haus Nord");
    await page.keyboard.press("ControlOrMeta+Enter");
    await expect(page.getByText("Gespeichert", { exact: true }).first()).toBeVisible();
    if (isMobile) await page.getByRole("button", { name: "Vorschau" }).click();
    const document = page.frameLocator('iframe[title="Vorschau: Rechnung"]');
    await expect(document.locator("dl.meta")).toContainText("Website-Redesign");
    await expect(document.locator("dl.meta")).toContainText("Haus Nord");
    await expectAccessible(page);
    const stored = (await (await page.request.get(`/api/documents/${draft.id}`)).json()) as {
      fields: Record<string, string>;
    };
    expect(stored.fields).toEqual({
      project: "Website-Redesign",
      [saved.info_block.at(-1)?.key ?? ""]: "Haus Nord",
    });
  } finally {
    // Saved for everyone: put the rows back as they were.
    await page.request.put(`/api/print-layouts/${before.id}`, {
      data: { name: before.name, layout: before.layout },
      headers: HEADERS,
    });
  }
});

test("a hidden row is still asked for, with a hint that fits the document", async ({
  page,
}, testInfo) => {
  const before = await defaultLayout(page);
  try {
    const hidden = before.layout.info_block.map((entry) =>
      entry.key === "reference" ? { ...entry, shown: false } : entry,
    );
    await page.request.put(`/api/print-layouts/${before.id}`, {
      data: { name: before.name, layout: { ...before.layout, info_block: hidden } },
      headers: HEADERS,
    });
    const customerId = await createCustomer(page, `Hinweis ${unique(testInfo.project.name)} AG`);
    const lines = [{ description: "Beratung", quantity: "1", unit: "HUR", unit_price: "150" }];

    // The invoice still sends the reference in its e-invoice.
    const invoice = await post<{ id: string }>(page, "/api/documents", {
      type: "invoice",
      customer_id: customerId,
      lines,
    });
    await openApp(page, `/documents/${invoice.id}`, "Rechnung (Entwurf)");
    const reference = page.getByRole("region", { name: "Daten" }).getByRole("textbox", {
      name: "Referenz",
    });
    await expect(reference).toHaveAccessibleDescription(/nur in der E-Rechnung/);

    // A quote has no e-invoice: it only says the PDF leaves the reference out.
    const quote = await post<{ id: string }>(page, "/api/documents", {
      type: "quote",
      customer_id: customerId,
      lines,
    });
    await openApp(page, `/documents/${quote.id}`, "Angebot (Entwurf)");
    await expect(reference).toHaveAccessibleDescription(
      "z. B. Bestellnummer des Kunden. Nicht im PDF (Druckvorlage).",
    );
    await expect(reference).not.toHaveAccessibleDescription(/E-Rechnung|XRechnung/);
    await expectAccessible(page);
  } finally {
    await page.request.put(`/api/print-layouts/${before.id}`, {
      data: { name: before.name, layout: before.layout },
      headers: HEADERS,
    });
  }
});
