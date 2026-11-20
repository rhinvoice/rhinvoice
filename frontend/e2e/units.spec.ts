import {
  HEADERS,
  createCustomer,
  expect,
  expectAccessible,
  openApp,
  post,
  test,
  unique,
  unitId,
  units,
  waitForToastsToClose,
} from "./fixtures";

test.describe.configure({ mode: "serial" });

/** The labels of the units offered, in the order of Settings → Units. */
async function offered(page: Parameters<typeof units>[0]): Promise<string[]> {
  return (await units(page)).filter((unit) => !unit.hidden).map((unit) => unit.label);
}

test("own units: from the catalogue, sorted, renamed, chosen in a line, hidden and back", async ({
  page,
  isMobile,
}, testInfo) => {
  test.setTimeout(120_000);
  const suffix = unique(testInfo.project.name);
  await openApp(page, "/settings?tab=units", "Einstellungen");
  await expect(page.getByRole("heading", { level: 2, name: "Einheiten" })).toBeVisible();
  const list = page.getByRole("list", { name: "Einheiten" });
  // The 21 units of before, in their order; hidden ones are not listed.
  await expect(list.getByRole("listitem")).toHaveCount(21);
  await expect(list.getByRole("listitem").first()).toContainText("Stk.");
  await expect(list.getByRole("listitem").first()).toContainText("C62");
  await expectAccessible(page);
  await expect(page).toHaveScreenshot("units-settings.png");
  const before = await offered(page);

  // dz from the catalogue (taken over before, it is hidden and comes back the same way).
  await page.getByRole("button", { name: "Aus Vorlage …" }).click();
  const catalogue = page.getByRole("dialog", { name: "Aus Vorlage übernehmen" });
  await catalogue.getByRole("searchbox", { name: "Einheit suchen" }).fill("doppel");
  const weight = catalogue.getByRole("group", { name: "Gewicht" });
  await expect(weight.getByRole("checkbox")).toHaveCount(1);
  await expect(catalogue.getByRole("group")).toHaveCount(1);
  await weight.getByRole("checkbox", { name: /Doppelzentner \(100 kg\)/ }).check();
  await expect(catalogue.getByText("1 ausgewählt")).toBeVisible();
  await expectAccessible(page);
  await catalogue.getByRole("button", { name: "Übernehmen" }).click();
  await expect(page.getByText("1 Einheit übernommen.")).toBeVisible();
  await expect(catalogue).toHaveCount(0);
  const quintal = list.getByRole("button", { name: /^«dz\.?» bearbeiten$/ });
  await expect(list.getByRole("listitem").last()).toContainText("DTN");
  expect((await offered(page)).length).toBe(22);

  // Sorting by keyboard (Alt+↑) and by dragging; the selects follow the order.
  await quintal.press("Alt+ArrowUp");
  await expect(quintal).toBeFocused();
  await expect(list.getByRole("listitem").nth(20)).toContainText("DTN");
  await expect.poll(async () => (await offered(page)).at(20)).toMatch(/^dz/);
  // The arrows do the same without dragging or keys (WCAG 2.5.7).
  await list.getByRole("button", { name: /^«dz\.?» nach unten$/ }).click();
  await expect(list.getByRole("listitem").last()).toContainText("DTN");
  await expect(list.getByRole("button", { name: /^«dz\.?» nach unten$/ })).toBeDisabled();
  await expect.poll(async () => (await offered(page)).at(21)).toMatch(/^dz/);
  if (!isMobile) {
    // Dragging is the pointer shortcut of desktops; phones use the arrows.
    // Onto a unit nearby: both stay in view while the pointer moves.
    await quintal.dragTo(list.getByRole("button", { name: "«Paket» bearbeiten" }));
    await expect(list.getByRole("listitem").nth(19)).toContainText("DTN");
    await expect.poll(async () => (await offered(page)).at(19)).toMatch(/^dz/);
  }
  // Back to the order of before, so that new lines elsewhere start in "Stk." again.
  const ids = (await units(page)).filter((unit) => !unit.hidden);
  const order = [
    ...before.map((label) => ids.find((unit) => unit.label === label)?.id ?? ""),
    ...ids.filter((unit) => !before.includes(unit.label)).map((unit) => unit.id),
  ];
  const sorted = await page.request.put("/api/units/order", {
    data: { unit_ids: order },
    headers: HEADERS,
  });
  expect(sorted.ok(), await sorted.text()).toBe(true);
  await openApp(page, "/settings?tab=units", "Einstellungen");
  await expect(list.getByRole("listitem").last()).toContainText("DTN");

  // Renamed, with a label of its own on English invoices.
  await quintal.click();
  const edit = page.getByRole("dialog", { name: "Einheit bearbeiten" });
  await expect(edit.getByLabel("Code für die E-Rechnung")).toHaveValue("DTN – decitonne");
  const others = edit.getByRole("button", {
    name: "Andere Bezeichnung auf englischen, französischen oder italienischen Rechnungen",
  });
  // The catalogue brings the labels of the other languages: they show.
  await expect(others).toHaveAttribute("aria-expanded", "true");
  await edit.getByLabel("Bezeichnung", { exact: true }).fill("dz.");
  await edit.getByLabel("Englisch").fill("dt.");
  await expectAccessible(page);
  await edit.getByRole("button", { name: "Speichern" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("Einheit «dz.» gespeichert.")).toBeVisible();
  await expect(list.getByRole("listitem").last()).toContainText("dz.");

  // An own unit nothing uses is deleted.
  const crate = `Kiste ${suffix}`.slice(0, 20);
  await page.getByRole("button", { name: "Neue Einheit" }).click();
  const add = page.getByRole("dialog", { name: "Neue Einheit" });
  await add.getByLabel("Bezeichnung", { exact: true }).fill(crate);
  await add.getByRole("button", { name: "Speichern" }).focus();
  await page.keyboard.press("Enter");
  await expect(add.getByLabel("Code für die E-Rechnung")).toHaveAccessibleDescription(
    "Wählen Sie einen Code aus der Liste.",
  );
  await add.getByLabel("Code für die E-Rechnung").fill("crate");
  await add.getByRole("option", { name: /^XCR\s*Crate$/ }).click();
  await expect(add.getByLabel("Code für die E-Rechnung")).toHaveValue("XCR – Crate");
  await expectAccessible(page);
  await add.getByRole("button", { name: "Speichern" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText(`Einheit «${crate}» gespeichert.`)).toBeVisible();
  await waitForToastsToClose(page);
  await list.getByRole("button", { name: `«${crate}» bearbeiten` }).click();
  await page
    .getByRole("dialog", { name: "Einheit bearbeiten" })
    .getByRole("button", { name: "Entfernen" })
    .click();
  const unused = page.getByRole("alertdialog", { name: `«${crate}» entfernen?` });
  await expect(unused).toContainText("Die Einheit wird gelöscht.");
  await unused.getByRole("button", { name: "Entfernen" }).click();
  await expect(page.getByText(`«${crate}» gelöscht.`)).toBeVisible();
  await expect(list.getByRole("button", { name: `«${crate}» bearbeiten` })).toHaveCount(0);
  expect((await units(page)).some((unit) => unit.label === crate)).toBe(false);
  await waitForToastsToClose(page);

  // dz in a line: the select offers it, the paper prints it.
  const customerId = await createCustomer(page, `Einheiten ${suffix} AG`);
  const draft = await post<{ id: string }>(page, "/api/documents", {
    type: "invoice",
    customer_id: customerId,
    lines: [
      {
        description: "Weizen",
        quantity: "12",
        unit_id: await unitId(page, "HUR"),
        unit_price: "45",
      },
    ],
  });
  await openApp(page, `/documents/${draft.id}`, "Rechnung (Entwurf)");
  const line = page.getByRole("button", { name: /^Position 1 bearbeiten/ });
  await expect(line).toContainText("12 Std.");
  await line.click();
  await page.locator("#lines-0-unit").selectOption({ label: "dz." });
  await expectAccessible(page);
  await page.getByRole("button", { name: "Übernehmen" }).click();
  await expect(line).toContainText("12 dz.");
  if (isMobile) await page.getByRole("button", { name: "Vorschau" }).click();
  const paper = page.frameLocator('iframe[title="Vorschau: Rechnung"]');
  await expect(paper.getByText(/^12\sdz\.$/)).toBeVisible();
  if (isMobile) await page.getByRole("button", { name: "Bearbeiten" }).click();
  const dz = await unitId(page, "DTN");
  // The draft saves itself; then the unit is in use.
  await expect
    .poll(async () => {
      const saved = (await (await page.request.get(`/api/documents/${draft.id}`)).json()) as {
        lines: { unit_id: string | null }[];
      };
      return saved.lines[0]?.unit_id;
    })
    .toBe(dz);

  // Removed while in use, dz is hidden: the line keeps it, new lines are not offered it.
  await openApp(page, "/settings?tab=units", "Einstellungen");
  await quintal.click();
  await page
    .getByRole("dialog", { name: "Einheit bearbeiten" })
    .getByRole("button", { name: "Entfernen" })
    .click();
  const used = page.getByRole("alertdialog", { name: "«dz.» entfernen?" });
  await expect(used).toContainText("Sie wird ausgeblendet");
  await used.getByRole("button", { name: "Entfernen" }).click();
  await expect(page.getByText("«dz.» ausgeblendet", { exact: false })).toBeVisible();
  await expect(quintal).toHaveCount(0);
  await openApp(page, `/documents/${draft.id}`, "Rechnung (Entwurf)");
  await expect(line).toContainText("12 dz.");
  await line.click();
  await expect(page.locator("#lines-0-unit option:checked")).toHaveText("dz. (ausgeblendet)");
  await openApp(page, "/invoices/new", "Neue Rechnung");
  await expect(page.locator("#lines-0-unit option", { hasText: "dz." })).toHaveCount(0);

  // The catalogue brings the hidden unit back, in its group.
  await openApp(page, "/settings?tab=units", "Einstellungen");
  await page.getByRole("button", { name: "Aus Vorlage …" }).click();
  await catalogue
    .getByRole("group", { name: "Gewicht" })
    .getByRole("checkbox", { name: /^dz\. · Doppelzentner/ })
    .check();
  await catalogue.getByRole("button", { name: "Übernehmen" }).click();
  await expect(page.getByText("1 Einheit übernommen.")).toBeVisible();
  await expect(list.getByRole("listitem").last()).toContainText("dz.");

  // Hidden again, for the next run of this test.
  await quintal.click();
  await page
    .getByRole("dialog", { name: "Einheit bearbeiten" })
    .getByRole("button", { name: "Entfernen" })
    .click();
  await page
    .getByRole("alertdialog", { name: "«dz.» entfernen?" })
    .getByRole("button", { name: "Entfernen" })
    .click();
  await expect(quintal).toHaveCount(0);
  // The open dialogs hide the list from the accessibility tree, so ask the API until it is hidden.
  await expect.poll(() => offered(page)).toEqual(before);
});

test("a unit's dialog", async ({ page }) => {
  await openApp(page, "/settings?tab=units", "Einstellungen");
  await page.getByRole("button", { name: "«Stk.» bearbeiten" }).click();
  const edit = page.getByRole("dialog", { name: "Einheit bearbeiten" });
  await expect(edit.getByLabel("Code für die E-Rechnung")).toHaveValue("C62 – one");
  await expect(edit.getByLabel("Englisch")).toHaveValue("pcs");
  await expectAccessible(page);
  await expect(edit).toHaveScreenshot("unit-dialog.png");
  await edit.getByRole("button", { name: "Abbrechen" }).click();
  await expect(edit).toHaveCount(0);
});
