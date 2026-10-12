import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

import { expect, expectAccessible, openApp, test, unique, waitForToastsToClose } from "./fixtures";

/** A one-page PDF with a line of text, small enough to write by hand. */
function pdf(text: string): Buffer {
  const stream = `BT /F1 18 Tf 72 720 Td (${text}) Tj ET`;
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
    `<< /Length ${String(stream.length)} >>\nstream\n${stream}\nendstream`,
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
  ];
  let body = "%PDF-1.4\n";
  const offsets: number[] = [];
  objects.forEach((object, index) => {
    offsets.push(body.length);
    body += `${String(index + 1)} 0 obj\n${object}\nendobj\n`;
  });
  const xref = body.length;
  body += `xref\n0 ${String(objects.length + 1)}\n0000000000 65535 f \n`;
  for (const offset of offsets) body += `${String(offset).padStart(10, "0")} 00000 n \n`;
  body += `trailer\n<< /Size ${String(objects.length + 1)} /Root 1 0 R >>\nstartxref\n${String(xref)}\n%%EOF\n`;
  return Buffer.from(body, "latin1");
}

test("old invoices are taken over with their PDF files", async ({ page }, testInfo) => {
  const suffix = unique(testInfo.project.name);
  // Numbers of their own per browser project: the projects share one database.
  const number = (n: number) => `ALT-${suffix}-${String(1000 + n)}`;
  const customer = `Altkunde ${suffix} AG`;
  const folder = testInfo.outputPath("IN");
  await mkdir(path.join(folder, "2015"), { recursive: true });
  await writeFile(path.join(folder, "2015", `Rechnung ${number(1)}.pdf`), pdf(number(1)));
  await writeFile(path.join(folder, "2015", `Mahnung ${number(1)}.pdf`), pdf("Mahnung"));
  await writeFile(path.join(folder, "2015", `Rechnung ${number(2)}.pdf`), pdf(number(2)));
  await writeFile(path.join(folder, "2015", "Scan_0042.pdf"), pdf("Scan"));
  await writeFile(path.join(folder, "notes.txt"), "not an invoice");

  await openApp(page, "/invoices", "Rechnungen");
  await page.getByRole("link", { name: "Importieren" }).click();
  await expect(
    page.getByRole("heading", { level: 1, name: "Alte Rechnungen übernehmen" }),
  ).toBeVisible();
  await expectAccessible(page);

  await page.getByLabel("Ordner wählen").setInputFiles(folder);
  await expect(page.getByText(/^4 PDF-Dateien · /)).toBeVisible();
  // As older programs export them: a counter as "Rechnungsnummer", the number in the title.
  await page.getByLabel("Datei wählen", { exact: true }).setInputFiles({
    name: "Rechnungen.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      [
        "Rechnungsnummer;Betreff;Rechnungsdatum;Kunde;PLZ;Ort;Netto;Betrag;Offen",
        `1;Rechnung ${number(1)};14.02.2015;${customer};3011;Bern;1200.00;1296.00;0`,
        `2;Rechnung ${number(2)};20.02.2015;${customer};3011;Bern;100.00;108.00;108.00`,
        `3;Rechnung ${number(3)};21.02.2015;${customer};3011;Bern;0;0;0`,
      ].join("\r\n"),
      "utf8",
    ),
  });
  const result = page.getByRole("region", { name: "Ergebnis des Testlaufs" });
  await expect(
    result.getByText("2 neu · 0 aktualisiert · 0 übersprungen · 1 mit Fehlern"),
  ).toBeVisible();
  await expect(page.getByRole("cell", { name: /Gesamtbetrag «0»: Betrag ist null/ })).toBeVisible();
  await page.getByRole("button", { name: /^Alle/ }).click();
  await expect(
    page.getByRole("cell", {
      name: new RegExp(`^Rechnung ${number(1)}\\.pdf ?IN/2015 · \\+ 1 Anhang$`),
    }),
  ).toBeVisible();
  await expect(page.getByRole("cell", { name: "Kunde neu angelegt (archiviert)" })).toBeVisible();
  await page.getByText("1 Datei gehört zu keiner Rechnung der Liste").click();
  await expect(page.getByText("IN/2015/Scan_0042.pdf")).toBeVisible();
  await expectAccessible(page);
  // The accessibility check scrolls through the page; the screenshot shows the result.
  await result.scrollIntoViewIfNeeded();
  await expect(page).toHaveScreenshot("invoice-import.png", {
    // The next number depends on the invoices of other tests.
    mask: [page.getByText(/^Die nächste Rechnung/)],
  });

  await page.getByRole("button", { name: "2 Rechnungen übernehmen" }).click();
  await expect(page.getByRole("heading", { name: "Import abgeschlossen" })).toBeVisible();
  await waitForToastsToClose(page);
  await page.getByRole("link", { name: "Zu den Rechnungen" }).click();
  await page.getByRole("searchbox", { name: /durchsuchen/ }).fill(number(1));
  const row = page.getByRole("row").filter({ hasText: number(1) });
  await expect(row.getByText("Übernommen")).toBeVisible();
  await row.getByRole("link", { name: number(1) }).click();

  // The invoice is its original PDF, with the reminder as attachment.
  await expect(
    page.getByRole("heading", { level: 1, name: `Rechnung ${number(1)}` }),
  ).toBeVisible();
  await expect(page.getByText("Übernommen", { exact: true })).toBeVisible();
  await expect(page.locator(`iframe[title="Rechnung ${number(1)} · Original-PDF"]`)).toBeVisible();
  const attachments = page.getByRole("region", { name: "Anhänge" });
  await expect(attachments.getByRole("link", { name: /Mahnung/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "Drucken" })).toHaveCount(0);
  // Nothing is built from an imported invoice: no duplicate, cancellation or recurring plan.
  await expect(page.getByRole("button", { name: "Weitere Aktionen" })).toHaveCount(0);
  await expectAccessible(page);
  const original = await page.request.get(
    `/api/documents/${page.url().split("/").at(-1) ?? ""}/pdf`,
  );
  expect((await original.body()).toString("latin1")).toContain(`(${number(1)}) Tj`);

  await page.getByRole("button", { name: "Details" }).click();
  await expect(
    page.getByText("Zahlungsdatum aus dem früheren Programm nicht bekannt", { exact: false }),
  ).toBeVisible();
  await expectAccessible(page);
});

test("an imported invoice without PDF takes one afterwards", async ({ page }, testInfo) => {
  const suffix = unique(testInfo.project.name);
  const number = `OHNE-${suffix}-2001`;
  await openApp(page, "/invoices/import", "Alte Rechnungen übernehmen");
  await page.getByLabel("Datei wählen", { exact: true }).setInputFiles({
    name: "Rechnungen.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      `Nummer;Datum;Kunde;PLZ;Ort;Betrag\r\n${number};01.03.2016;Ohne PDF ${suffix} AG;3011;Bern;54\r\n`,
    ),
  });
  await page.getByRole("button", { name: "1 Rechnung übernehmen" }).click();
  await expect(page.getByRole("heading", { name: "Import abgeschlossen" })).toBeVisible();
  await page.getByRole("link", { name: "Zu den Rechnungen" }).click();
  await page.getByRole("searchbox", { name: /durchsuchen/ }).fill(number);
  await page.getByRole("link", { name: number }).click();
  await page.getByRole("button", { name: "Dokument" }).click();

  await expect(page.getByText("Noch kein PDF")).toBeVisible();
  await expectAccessible(page);
  await page.getByLabel("PDF hinzufügen").setInputFiles({
    name: "Scan_0042.pdf",
    mimeType: "application/pdf",
    buffer: pdf(number),
  });
  // A file added stays for good: Rhinvoice asks first.
  const confirm = page.getByRole("alertdialog", { name: "PDF hinzufügen?" });
  await expect(confirm.getByText(/«Scan_0042\.pdf» wird dauerhaft/)).toBeVisible();
  await expectAccessible(page);
  await confirm.getByRole("button", { name: "PDF hinzufügen" }).click();
  await expect(page.getByText("PDF hinzugefügt.")).toBeVisible();
  await expect(page.locator(`iframe[title="Rechnung ${number} · Original-PDF"]`)).toBeVisible();
  // Further files become attachments.
  await page.getByLabel("Datei anhängen").setInputFiles({
    name: "Mahnung.pdf",
    mimeType: "application/pdf",
    buffer: pdf("Mahnung"),
  });
  await page
    .getByRole("alertdialog", { name: "Datei anhängen?" })
    .getByRole("button", { name: "Datei anhängen" })
    .click();
  await expect(page.getByText("Datei hinzugefügt.")).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Anhänge" }).getByRole("link", { name: /Mahnung\.pdf/ }),
  ).toBeVisible();
  await waitForToastsToClose(page);
  await expectAccessible(page);
});
