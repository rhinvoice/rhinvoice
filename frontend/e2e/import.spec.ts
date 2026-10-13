import { expect, expectAccessible, openApp, test, unique, waitForToastsToClose } from "./fixtures";

function csv(rows: readonly string[]): { name: string; mimeType: string; buffer: Buffer } {
  // Windows-1252 like files saved by Excel on Windows.
  return {
    name: "kunden.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(rows.join("\r\n"), "latin1"),
  };
}

test("customers are imported after a test run", async ({ page }, testInfo) => {
  const suffix = unique(testInfo.project.name);
  const company = `Import ${suffix} AG`;
  const person = `Beispiel${suffix}`;
  await openApp(page, "/customers", "Kunden");
  await page.getByRole("link", { name: "Importieren" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Kunden importieren" })).toBeVisible();
  await expectAccessible(page);

  await page
    .getByLabel("Datei wählen")
    .setInputFiles(
      csv([
        "Firma;Vorname;Nachname;Strasse;PLZ_Ort;Land;Bemerkung2",
        `${company};;;Dorfstrasse 1;CH-9470 Buchs SG;;Stammkunde`,
        `;Anna;${person};Bahnhofstrasse 5a;6850 Dornbirn;Österreich;`,
        `Ohne Ort ${suffix} GmbH;;;Feldweg 3;;;`,
      ]),
    );
  await expect(page.getByText("3 Zeilen · Windows-1252 · «;»")).toBeVisible();
  const result = page.getByRole("region", { name: "Ergebnis des Testlaufs" });
  await expect(
    result.getByText("2 neu · 0 aktualisiert · 0 übersprungen · 1 mit Fehlern"),
  ).toBeVisible();
  // Announced, too.
  await expect(page.getByRole("status").filter({ hasText: "2 neu ·" })).toBeAttached();
  // Rows with errors are shown first.
  await expect(page.getByRole("cell", { name: "PLZ: fehlt" })).toBeVisible();

  await page.getByText(/^Spalten zuordnen/).click();
  const remark = page.getByLabel("Feld für die Spalte Bemerkung2");
  await expect(remark).toHaveValue("");
  await remark.selectOption({ label: "Notiz" });
  await expect(page.getByText("Spalten zuordnen (7 von 7 zugeordnet)")).toBeVisible();
  await page.getByRole("button", { name: /^Alle/ }).click();
  await expect(
    page.getByRole("region", { name: "Zeilen der Datei" }).getByRole("cell", { name: company }),
  ).toBeVisible();
  await expectAccessible(page);

  await page.getByRole("button", { name: "2 Kunden importieren" }).click();
  await expect(page.getByRole("heading", { name: "Import abgeschlossen" })).toBeVisible();
  await expect(page.getByText("2 Kunden importiert.")).toBeVisible();
  await waitForToastsToClose(page);
  await expectAccessible(page);

  await page.getByRole("link", { name: "Zu den Kunden" }).click();
  await page.getByRole("searchbox", { name: "Kunden durchsuchen" }).fill(suffix);
  await expect(page.getByRole("row").filter({ hasText: company })).toBeVisible();
  await expect(page.getByRole("row").filter({ hasText: `Anna ${person}` })).toBeVisible();
});

test("a column mapping is saved as a template", async ({ page }, testInfo) => {
  const suffix = unique(testInfo.project.name);
  await page.goto("/articles/import");
  await page.getByLabel("Datei wählen").setInputFiles({
    name: "artikel.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(`Titel;VK\nWorkshop ${suffix} Import;120,00\n`, "utf8"),
  });
  // "Titel" is a usual name of the article name, "VK" of the price.
  await expect(
    page
      .getByRole("region", { name: "Ergebnis des Testlaufs" })
      .getByText("1 neu · 0 aktualisiert · 0 übersprungen · 0 mit Fehlern"),
  ).toBeVisible();
  await page.getByRole("button", { name: "Als Vorlage speichern" }).click();
  const dialog = page.getByRole("dialog", { name: "Als Vorlage speichern" });
  await dialog.getByLabel("Name der Vorlage").fill(`Webshop ${suffix}`);
  await dialog.getByRole("button", { name: "Speichern" }).click();
  await expect(dialog).toBeHidden();
  await expect(page.getByRole("combobox", { name: "Vorlage" })).toHaveValue(/.+/);
  await page.getByRole("button", { name: `Vorlage «Webshop ${suffix}» löschen` }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Löschen" }).click();
  await expect(page.getByText("Vorlage gelöscht.")).toBeVisible();
  await expect(page.getByRole("combobox", { name: "Vorlage" })).toHaveValue("");
});

test("columns with unknown names are mapped by hand", async ({ page }, testInfo) => {
  const suffix = unique(testInfo.project.name);
  await page.goto("/articles/import");
  await page.getByLabel("Datei wählen").setInputFiles({
    name: "liste.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(`Spalte A;Spalte B\nKurs ${suffix};90\n`, "utf8"),
  });
  await expect(
    page.getByText("Spalten zuordnen: Es fehlt eine Spalte für Nummer oder Bezeichnung.").first(),
  ).toBeVisible();
  await expectAccessible(page);
  await page.getByLabel("Feld für die Spalte Spalte A").selectOption({ label: "Bezeichnung" });
  await page
    .getByLabel("Feld für die Spalte Spalte B")
    .selectOption({ label: "Preis (Firmenwährung)" });
  await expect(
    page
      .getByRole("region", { name: "Ergebnis des Testlaufs" })
      .getByText("1 neu · 0 aktualisiert · 0 übersprungen · 0 mit Fehlern"),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "1 Artikel importieren" })).toBeEnabled();
});

test("the public demo takes no files and says where importing works", async ({ page }) => {
  // The demo itself only differs in what /api/demo answers.
  await page.route("**/api/demo", async (route) => {
    const response = await route.fetch();
    const demo = (await response.json()) as Record<string, unknown>;
    await route.fulfill({ response, json: { ...demo, enabled: true } });
  });
  await page.goto("/invoices/import");
  await expect(
    page.getByRole("heading", { level: 1, name: "Alte Rechnungen übernehmen" }),
  ).toBeVisible();
  await expect(page.getByText("Der Import ist in der Demo ausgeschaltet")).toBeVisible();
  await expect(page.getByLabel("Datei wählen")).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Installationsanleitung" })).toHaveAttribute(
    "href",
    "https://rhinvoice.com/docs/de/getting-started/installation/",
  );
  // Every page of the demo leads back to the website.
  await expect(
    page.getByRole("complementary", { name: "Demo" }).getByRole("link", { name: "rhinvoice.com" }),
  ).toHaveAttribute("href", "https://rhinvoice.com/de/");
  await expectAccessible(page);
});
