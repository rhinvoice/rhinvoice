import {
  createCustomer,
  expect,
  expectAccessible,
  expectDocumentAccessible,
  openApp,
  post,
  test,
  unique,
  waitForToastsToClose,
} from "./fixtures";

test.describe.configure({ mode: "serial" });

/** A one-page PDF with a line of text, enough for a browser to open it. */
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
  return Buffer.from(body);
}

test("pass-through items print apart and third-party invoices go with the invoice", async ({
  page,
  isMobile,
}, testInfo) => {
  test.setTimeout(90_000);
  const suffix = unique(testInfo.project.name);
  const customerId = await createCustomer(page, `Durchlauf ${suffix} AG`);
  const draft = await post<{ id: string }>(page, "/api/documents", {
    type: "invoice",
    customer_id: customerId,
    lines: [
      { description: "Buchhaltung", quantity: "4", unit: "HUR", unit_price: "120" },
      { description: "Gründungsgebühr Handelsregister", quantity: "1", unit_price: "250.35" },
    ],
  });
  await openApp(page, `/documents/${draft.id}`, "Rechnung (Entwurf)");

  // The fee is marked as a pass-through item: the hint names the condition.
  await page.getByRole("button", { name: /^Position 2 bearbeiten/ }).click();
  const tax = page.locator("#lines-1-tax");
  await tax.selectOption("pass_through");
  await expect(tax.locator("option:checked")).toHaveText("Durchlaufender Posten (ohne MWST)");
  await expect(tax).toHaveAccessibleDescription(
    "Nur wenn die Fremdrechnung auf den Namen Ihres Kunden lautet.",
  );
  // Goods or services do not matter for it.
  await expect(page.locator("#lines-1-supply")).toHaveCount(0);
  await expectAccessible(page);
  await page.getByRole("button", { name: "Übernehmen" }).click();

  // The list of positions says which line it is.
  await expect(page.getByRole("button", { name: /^Position 2 bearbeiten/ })).toContainText(
    "Durchlaufend",
  );
  // 480 + 8.1 % VAT = 518.90, plus 250.35 outside the VAT: 769.25.
  await expect(page.getByText("CHF 769.25")).toBeVisible();
  if (isMobile) await page.getByRole("button", { name: "Vorschau" }).click();
  const paper = page.frameLocator('iframe[title="Vorschau: Rechnung"]');
  await expect(paper.getByText("MWST 8.1 % auf 480.00")).toBeVisible();
  await expect(
    paper.getByText("Durchlaufende Posten (im Namen und auf Rechnung des Kunden bezahlt)"),
  ).toBeVisible();
  await expect(paper.locator(".pass-through")).toHaveText(
    /Gründungsgebühr Handelsregister\s*250\.35/,
  );
  await expect(paper.locator("table.lines")).not.toContainText("Gründungsgebühr");
  if (isMobile) {
    await page.getByRole("button", { name: "Bearbeiten" }).click();
  } else {
    // A click on the item in the block opens it, like positions in the table.
    await paper.locator('.pass-through[data-index="1"]').click();
    await expect(page.locator("#lines-1-description")).toBeFocused();
    await page.locator("#lines-1-description").press("Escape");
  }

  // The third-party invoice goes with the draft; it can be removed until issuing.
  await page.getByText("Anhänge", { exact: true }).click();
  const attach = page.getByLabel("PDF hinzufügen");
  await attach.setInputFiles([
    { name: "Handelsregister.pdf", mimeType: "application/pdf", buffer: pdf("Handelsregister") },
    { name: "Irrtum.pdf", mimeType: "application/pdf", buffer: pdf("Irrtum") },
  ]);
  await expect(page.getByText("2 PDFs angehängt.")).toBeVisible();
  await expect(page.getByRole("link", { name: /Irrtum\.pdf/ })).toBeVisible();
  // Keyboard: on phones a tap here would leave the pointer on the toasts, which then stay open.
  await page.getByRole("button", { name: "«Irrtum.pdf» entfernen" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("«Irrtum.pdf» entfernt.")).toBeVisible();
  await expect(page.getByRole("link", { name: /Irrtum\.pdf/ })).toHaveCount(0);
  await expect(page.getByText("1 PDF", { exact: true })).toBeVisible();
  await expectAccessible(page);
  await waitForToastsToClose(page);
  await expect(page).toHaveScreenshot("pass-through-editor.png", {
    // The customer number and the draft dates depend on other tests; the date is today's.
    mask: [
      page.getByRole("region", { name: "Kunde" }),
      paper.locator(".meta"),
      page.locator("#issue_date"),
    ],
  });

  // Not a PDF: refused with a clear message.
  await attach.setInputFiles({ name: "Foto.png", mimeType: "image/png", buffer: Buffer.from("x") });
  await expect(page.getByText("Das ist keine PDF-Datei.")).toBeVisible();
  await page.getByRole("button", { name: "Ausstellen" }).click();
  await page
    .getByRole("alertdialog", { name: "Rechnung ausstellen?" })
    .getByRole("button", { name: "Ausstellen" })
    .click();
  await expect(page.getByText(/^Rechnung .+ ausgestellt\.$/)).toBeVisible();

  // Issued, the attachment stays with the invoice and cannot be removed.
  const attachments = page.getByRole("region", { name: "Anhänge" });
  await expect(attachments.getByRole("link", { name: /Handelsregister\.pdf/ })).toBeVisible();
  await expect(attachments.getByRole("button")).toHaveCount(0);
  // The program window hands new tabs to a browser without the login: there, a click saves.
  await page.evaluate(() => Object.assign(window, { pywebview: {} }));
  const saved = page.waitForEvent("download");
  // Keyboard: on phones the toast of the refused file still lies over the link.
  await attachments.getByRole("link", { name: /Handelsregister\.pdf/ }).focus();
  await page.keyboard.press("Enter");
  expect((await saved).suggestedFilename()).toBe("Handelsregister.pdf");
  expect(page.context().pages()).toHaveLength(1);
  await page.getByRole("button", { name: "Details" }).click();
  const totals = page.getByRole("region", { name: "Summen" });
  await expect(totals.getByText("Durchlaufende Posten")).toBeVisible();
  await expect(totals.getByText("CHF 250.35")).toBeVisible();
  await expectAccessible(page);
  await expectDocumentAccessible(page, draft.id);
});

test("PDFs chosen for a new invoice are attached when it is first saved", async ({
  page,
}, testInfo) => {
  const suffix = unique(testInfo.project.name);
  const customerId = await createCustomer(page, `Neu ${suffix} AG`);
  await openApp(page, `/invoices/new?customer=${customerId}`, "Neue Rechnung");
  await page.locator("#lines-0-description").fill("Gründungsgebühr Handelsregister");
  await page.locator("#lines-0-unit_price").fill("250.35");

  // The section is there before the first save; the files wait in the browser.
  await page.getByText("Anhänge", { exact: true }).click();
  await page.getByLabel("PDF hinzufügen").setInputFiles([
    { name: "Handelsregister.pdf", mimeType: "application/pdf", buffer: pdf("Handelsregister") },
    { name: "Irrtum.pdf", mimeType: "application/pdf", buffer: pdf("Irrtum") },
  ]);
  await expect(page.getByText("2 PDFs", { exact: true })).toBeVisible();
  await expect(page.getByText(/^Sie werden mit dem ersten Speichern angehängt\./)).toBeVisible();
  await page.getByRole("button", { name: "«Irrtum.pdf» entfernen" }).click();
  await expect(page.getByText("Irrtum.pdf")).toHaveCount(0);
  await expect(page.getByText("1 PDF", { exact: true })).toBeVisible();
  await expectAccessible(page);

  await page.getByRole("button", { name: "Speichern" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Rechnung (Entwurf)" })).toBeVisible();
  await expect(page.getByText("Entwurf gespeichert.")).toBeVisible();
  await page.getByText("Anhänge", { exact: true }).click();
  await expect(page.getByRole("link", { name: /Handelsregister\.pdf/ })).toBeVisible();
  await expect(page.getByRole("link", { name: /Irrtum\.pdf/ })).toHaveCount(0);
  await expect(page.getByText("1 PDF", { exact: true })).toBeVisible();
});

test("issuing a new invoice with PDFs runs once, however often the buttons are clicked", async ({
  page,
}, testInfo) => {
  const suffix = unique(testInfo.project.name);
  const customerId = await createCustomer(page, `Einmal ${suffix} AG`);
  // A slow upload: saving, attaching and issuing take a while, as with large files.
  let release: () => void = () => undefined;
  const uploaded = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/documents/*/files", async (route) => {
    await uploaded;
    await route.continue();
  });
  await openApp(page, `/invoices/new?customer=${customerId}`, "Neue Rechnung");
  await page.locator("#lines-0-description").fill("Gründungsgebühr Handelsregister");
  await page.locator("#lines-0-unit_price").fill("250.35");
  await page.getByText("Anhänge", { exact: true }).click();
  await page
    .getByLabel("PDF hinzufügen")
    .setInputFiles({ name: "Notar.pdf", mimeType: "application/pdf", buffer: pdf("Notar") });

  const issue = page.getByRole("button", { name: "Ausstellen", exact: true });
  await issue.click();
  // Several clicks at once, while the dialog closes.
  await page
    .getByRole("alertdialog", { name: "Rechnung ausstellen?" })
    .getByRole("button", { name: "Ausstellen" })
    .click({ clickCount: 3 });
  // The draft exists and the upload waits: everything stays locked, the clicked button spins.
  await expect(issue).toBeDisabled();
  await expect(issue.locator(".lucide-loader-circle")).toHaveCount(1);
  await expect(page.getByRole("button", { name: /^Speichern/ })).toBeDisabled();
  await expect(page.getByRole("button", { name: "«Notar.pdf» entfernen" })).toBeDisabled();
  await expect(page.getByText("Wird gespeichert …")).toBeVisible();
  await page.keyboard.press("ControlOrMeta+Enter");
  release();

  await expect(page.getByText(/^Rechnung .+ ausgestellt\.$/)).toBeVisible();
  const documents = (await (
    await page.request.get(`/api/documents?customer_id=${customerId}`)
  ).json()) as { total: number };
  expect(documents.total).toBe(1);
  await expect(
    page.getByRole("region", { name: "Anhänge" }).getByRole("link", { name: /Notar\.pdf/ }),
  ).toBeVisible();
});
