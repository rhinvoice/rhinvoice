import {
  HEADERS,
  createCustomer,
  defaultLayout,
  expect,
  expectAccessible,
  openApp,
  post,
  test,
  unique,
  type NamedLayout,
} from "./fixtures";

test("several print templates: one per customer, chosen in the editor header", async ({
  page,
  isMobile,
}, testInfo) => {
  test.setTimeout(90_000);
  const name = `Treuhand ${unique(testInfo.project.name)}`;
  const standard = await defaultLayout(page);
  try {
    // A new template starts as a copy of the chosen one and gets its own look.
    await page.goto("/settings?tab=print");
    await page.getByRole("button", { name: "Neue Vorlage" }).click();
    const dialog = page.getByRole("dialog", { name: "Neue Druckvorlage" });
    await expect(dialog).toContainText(`Kopie von «${standard.name}»`);
    await dialog.getByRole("textbox", { name: "Name" }).fill(standard.name);
    await dialog.getByRole("button", { name: "Anlegen" }).click();
    await expect(dialog.getByText("Eine andere Druckvorlage hat diesen Namen.")).toBeVisible();
    await dialog.getByRole("textbox", { name: "Name" }).fill(name);
    await dialog.getByRole("button", { name: "Anlegen" }).click();
    await expect(dialog).toHaveCount(0);
    const choice = page.getByRole("combobox", { name: "Druckvorlage" });
    await expect(choice.locator("option:checked")).toHaveText(name);
    await page.getByRole("radio", { name: "Klassisch" }).check();
    // Another template is chosen after saving or resetting.
    await expect(choice).toBeDisabled();
    await page.getByRole("button", { name: "Speichern" }).click();
    await expect(choice).toBeEnabled();
    await expectAccessible(page);
    const sample = page.waitForEvent("download");
    await page.getByRole("button", { name: "Muster-PDF" }).click();
    expect((await sample).suggestedFilename()).toBe(`Muster ${name}.pdf`);

    // The customer takes the template; the editor header shows it.
    const customerName = `Vorlage ${unique(testInfo.project.name)} AG`;
    const customerId = await createCustomer(page, customerName);
    await openApp(page, `/customers/${customerId}`, customerName);
    await page.getByRole("combobox", { name: "Druckvorlage" }).selectOption({ label: name });
    await page.keyboard.press("ControlOrMeta+Enter");
    await expect(page.getByText("Gespeichert", { exact: true }).first()).toBeVisible();
    const draft = await post<{ id: string }>(page, "/api/documents", {
      type: "invoice",
      customer_id: customerId,
      lines: [{ description: "Beratung", quantity: "1", unit: "HUR", unit_price: "100" }],
    });
    await openApp(page, `/documents/${draft.id}`, "Rechnung (Entwurf)");
    if (isMobile) await page.getByRole("button", { name: "Vorschau" }).click();
    const picked = page.getByRole("combobox", { name: "Druckvorlage" });
    await expect(picked.locator("option:checked")).toHaveText(`${name} (vom Kunden)`);
    const paper = page.frameLocator('iframe[title="Vorschau: Rechnung"]');
    await expect(paper.locator("body.template-classic")).toBeAttached();
    await picked.selectOption({ label: standard.name });
    await expect(paper.locator("body.template-classic")).toHaveCount(0);
    await expectAccessible(page);
  } finally {
    // Saved for everyone: remove the template again.
    const layouts = (await (await page.request.get("/api/print-layouts")).json()) as NamedLayout[];
    for (const named of layouts.filter((other) => other.name === name)) {
      await page.request.delete(`/api/print-layouts/${named.id}`, { headers: HEADERS });
    }
  }
});
