import { expect, expectAccessible, openApp, test, unique } from "./fixtures";

test("settings show the security section", async ({ page }) => {
  await page.goto("/settings?tab=security");
  await expect(page).toHaveTitle("Einstellungen · Rhinvoice");
  await expect(page.getByRole("heading", { name: "Passwort ändern" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Zwei-Faktor-Authentifizierung" })).toBeVisible();
  await page.getByRole("button", { name: "Speichern" }).click();
  await expect(page.getByLabel("Neues Passwort")).toHaveAttribute("aria-invalid", "true");
  await expectAccessible(page);
  await expect(page).toHaveScreenshot("settings.png");
});

test("single-key shortcuts can be turned off (WCAG 2.1.4)", async ({ page, isMobile }) => {
  test.skip(isMobile, "keyboard shortcuts are a desktop feature");
  await openApp(page, "/settings?tab=interaction", "Einstellungen");
  const toggle = page.getByRole("switch", { name: "Einzeltasten-Kürzel" });
  await expect(toggle).toBeChecked();
  await toggle.click();
  await expect(toggle).not.toBeChecked();
  await page.locator("body").click({ position: { x: 5, y: 300 } });
  await page.keyboard.press("n");
  await expect(page).toHaveURL(/\/settings\?tab=interaction$/);
  await page.keyboard.press("ControlOrMeta+k");
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await toggle.click();
  await expect(toggle).toBeChecked();
});

test("text templates and legal notices are managed in the settings", async ({ page }, testInfo) => {
  const name = `Gruss ${unique(testInfo.project.name)}`;
  await page.goto("/settings?tab=texts");
  await expect(page.getByRole("tab", { name: "Texte", selected: true })).toBeVisible();
  // English quotes: the invoice editor of other tests does not see these templates.
  await page
    .getByRole("group", { name: "Dokumentart" })
    .getByRole("button", { name: "Angebot" })
    .click();
  await page
    .getByRole("group", { name: "Sprache" })
    .getByRole("button", { name: "Englisch" })
    .click();
  const closing = page.getByRole("region", { name: "Schlusstext" });
  await expect(closing.getByText("Validity")).toBeVisible();

  await closing.getByRole("button", { name: "Hinzufügen Schlusstext" }).click();
  const dialog = page.getByRole("dialog", { name: /Neuer Textbaustein/ });
  await dialog.getByLabel("Name").fill(name);
  await dialog.getByLabel("Text").fill("Kind regards until {bis}");
  await dialog.getByRole("button", { name: "Speichern" }).click();
  await expect(dialog.getByText(/^Unbekannter Platzhalter/)).toBeVisible();
  await expectAccessible(page);
  await dialog.getByLabel("Text").fill("Valid until ");
  await dialog
    .getByRole("button", { name: "Platzhalter für Fälligkeit oder Gültigkeit einfügen" })
    .click();
  await expect(dialog.getByLabel("Text")).toHaveValue("Valid until {faellig}");
  await dialog.getByRole("button", { name: "Speichern" }).click();
  await expect(dialog).toBeHidden();
  await expect(closing.getByText(name)).toBeVisible();

  await closing.getByRole("button", { name: `«${name}» nach oben` }).click();
  await closing.getByRole("button", { name: `«${name}» löschen` }).click();
  await page
    .getByRole("alertdialog", { name: "Textbaustein löschen?" })
    .getByRole("button", { name: "Löschen" })
    .click();
  await expect(page.getByText("Textbaustein gelöscht")).toBeVisible();
  await expect(closing.getByText(name)).toHaveCount(0);

  // The reverse charge notice in English: own wording, then back to the suggestion.
  const notice = page.getByLabel("Reverse Charge");
  await expect(notice).toHaveValue("Reverse charge: the recipient is liable for the VAT.");
  await notice.fill("Reverse charge – VAT to be accounted for by the recipient.");
  await page.getByRole("button", { name: "Speichern Reverse Charge" }).click();
  await expect(page.getByText("Eigener Wortlaut.")).toBeVisible();
  await page.getByRole("button", { name: "Vorschlag wiederherstellen Reverse Charge" }).click();
  await expect(notice).toHaveValue("Reverse charge: the recipient is liable for the VAT.");
});

test("the backup settings say when backups are not set up", async ({ page }) => {
  // The E2E stack runs without the backup container.
  await page.goto("/settings?tab=backup");
  await expect(page.getByRole("tab", { name: "Backup", selected: true })).toBeVisible();
  await expect(page.getByText("Nicht eingerichtet", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Anleitung öffnen" })).toHaveAttribute(
    "href",
    "https://rhinvoice.com/docs/de/operations/backup/",
  );
  await expect(page.getByRole("button", { name: "Jetzt sichern" })).toHaveCount(0);
  await expectAccessible(page);

  await page.goto("/");
  const card = page.getByRole("region", { name: "Backup" });
  await expect(card.getByText("Nicht eingerichtet", { exact: true })).toBeVisible();
  await card.getByRole("link", { name: "Backup prüfen" }).click();
  await expect(page).toHaveURL(/\/settings\?tab=backup$/);
});

test("the backup settings list the runs and allow another try after a failure", async ({
  page,
}) => {
  const runs = [
    {
      id: 3,
      started_at: "2026-10-11T09:00:00Z",
      finished_at: "2026-10-11T09:00:30Z",
      reason: "manual",
      status: "failed",
      snapshot_id: null,
      data_added: null,
      message: "Fatal: repository not reachable",
    },
    {
      id: 2,
      started_at: "2026-10-11T08:00:00Z",
      finished_at: "2026-10-11T08:00:20Z",
      reason: "document",
      status: "succeeded",
      snapshot_id: "52365e00",
      data_added: 48_000,
      message: null,
    },
  ];
  const state = {
    state: "current",
    last_success: runs[1],
    // Requested before the failed run: the request stays open, a new try is allowed.
    requested_at: "2026-10-11T08:59:00Z",
    runs,
  };
  await page.route("**/api/backup", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({
        status: 202,
        json: { ...state, requested_at: "2026-10-11T09:30:00Z" },
      });
    } else {
      await route.fulfill({ json: state });
    }
  });
  await page.goto("/settings?tab=backup");
  await expect(
    page.getByText("Letzter Versuch fehlgeschlagen: Fatal: repository not reachable"),
  ).toBeVisible();
  await expect(page.getByRole("cell", { name: "+48 kB" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Nach Ausstellen oder Storno" })).toBeVisible();
  await expectAccessible(page);
  await page.getByRole("button", { name: "Jetzt sichern" }).click();
  await expect(page.getByText("Backup angefordert.")).toBeVisible();
  await expect(
    page.getByRole("status").filter({ hasText: "Angefordert, startet in Kürze." }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Jetzt sichern" })).toBeDisabled();
});

test("the program without Docker sets up its backup folder and recovery key", async ({ page }) => {
  const onedrive = "C:\\Users\\anna\\OneDrive\\Rhinvoice-Backup";
  const key = "K7QM-2XWP-9DTA-F4NR-H8JC-3VLS-B6YE-Q5ZU";
  let setup = {
    folder: null as string | null,
    suggestions: [{ name: "OneDrive", path: onedrive }],
    key_confirmed: false,
  };
  let backup = {
    state: "not_set_up",
    last_success: null,
    requested_at: null as string | null,
    runs: [],
  };
  await page.route("**/api/backup", (route) => route.fulfill({ json: backup }));
  await page.route("**/api/backup/setup", async (route) => {
    if (route.request().method() !== "PUT") {
      await route.fulfill({ json: setup });
      return;
    }
    const { folder } = route.request().postDataJSON() as { folder: string };
    if (folder !== onedrive) {
      const reason = "the folder cannot be created: Permission denied";
      await route.fulfill({
        status: 422,
        json: {
          error: { code: "backup_folder_unusable", message: reason, details: { folder: reason } },
        },
      });
      return;
    }
    setup = { ...setup, folder };
    backup = { ...backup, requested_at: "2026-10-14T09:00:00Z" };
    await route.fulfill({ json: { key } });
  });
  await page.route("**/api/backup/key", (route) => route.fulfill({ json: { key } }));
  await page.route("**/api/backup/key/confirmed", async (route) => {
    setup = { ...setup, key_confirmed: true };
    await route.fulfill({ json: setup });
  });

  await openApp(page, "/settings?tab=backup", "Einstellungen");
  await expect(page.getByRole("heading", { name: "Backup einrichten" })).toBeVisible();
  await expect(page.getByRole("radio", { name: /OneDrive/ })).toBeChecked();
  await expect(page.getByRole("link", { name: "Anleitung öffnen" })).toHaveCount(0);
  await page.getByRole("radio", { name: /Anderer Ordner/ }).check();
  await page.getByRole("button", { name: "Weiter zum Schlüssel" }).click();
  await expect(page.getByLabel("Pfad des Ordners")).toHaveAttribute("aria-invalid", "true");
  await page.getByLabel("Pfad des Ordners").fill("Z:\\Backup");
  await page.getByRole("button", { name: "Weiter zum Schlüssel" }).click();
  await expect(page.getByRole("alert")).toHaveText(
    "Dieser Ordner lässt sich nicht verwenden: the folder cannot be created: Permission denied",
  );
  await expectAccessible(page);

  await page.getByRole("radio", { name: /OneDrive/ }).check();
  await page.getByRole("button", { name: "Weiter zum Schlüssel" }).click();
  await expect(
    page.getByRole("heading", { name: "Ihr Wiederherstellungs-Schlüssel" }),
  ).toBeVisible();
  const shown = page.getByRole("group", { name: "Wiederherstellungs-Schlüssel" });
  await expect(shown).toContainText("K7QM");
  await expect(shown).toContainText("Q5ZU");
  await expect(page.getByText(`Die Backups gehen nach ${onedrive}.`)).toBeVisible();
  await expect(
    page.getByRole("status").filter({ hasText: "Angefordert, startet in Kürze." }),
  ).toBeVisible();
  // Before the first backup ran, the API refuses one by hand: no button, a hint instead.
  await expect(page.getByRole("button", { name: "Jetzt sichern" })).toHaveCount(0);
  await expect(page.getByText(/Das erste Backup startet in Kürze/)).toBeVisible();
  const finish = page.getByRole("button", { name: "Backup einrichten" });
  await expect(finish).toBeDisabled();
  await expectAccessible(page);
  await page.getByLabel("Ich habe den Schlüssel sicher aufbewahrt.").check();
  await finish.click();
  await expect(page.getByText("Backup eingerichtet. Das erste startet in Kürze.")).toBeVisible();
  await expect(shown).toHaveCount(0);

  // Later: the key on request, another folder.
  await page.getByRole("button", { name: "Schlüssel anzeigen" }).click();
  await expect(shown).toContainText("H8JC");
  await page.getByRole("button", { name: "Schlüssel ausblenden" }).click();
  await expect(shown).toHaveCount(0);
  await page.getByRole("button", { name: "Ordner ändern" }).click();
  await expect(page.getByRole("heading", { name: "Anderen Ordner wählen" })).toBeVisible();
  await expect(page.getByRole("radio", { name: /OneDrive/ })).toBeChecked();
  await expectAccessible(page);
  await page.getByRole("button", { name: "Abbrechen" }).click();
  await expect(page.getByRole("heading", { name: "Anderen Ordner wählen" })).toHaveCount(0);
});

test("the print template is chosen with a live preview", async ({ page }) => {
  await page.goto("/settings?tab=print");
  await expect(page.getByRole("tab", { name: "Druckvorlage", selected: true })).toBeVisible();
  const paper = page.frameLocator('iframe[title="Vorschau der Druckvorlage"]');
  await expect(paper.locator("body.template-modern")).toBeAttached();
  await page.getByRole("radio", { name: "Klassisch" }).check();
  await page.getByRole("radio", { name: "Alle Konten" }).check();
  await expect(paper.locator("body.template-classic")).toBeAttached();
  await expect(page.getByRole("switch", { name: "E-Rechnung im PDF (ZUGFeRD)" })).toBeChecked();
  await expectAccessible(page);
  // Saved for everyone: put the default back afterwards.
  await page.getByRole("button", { name: "Speichern" }).click();
  await expect(page.getByText("Gespeichert", { exact: true })).toBeVisible();
  await page.getByRole("radio", { name: "Modern" }).check();
  await page.getByRole("radio", { name: "Nur Rechnungswährung" }).check();
  await page.getByRole("button", { name: "Speichern" }).click();
  await expect(page.getByRole("button", { name: "Speichern" })).toBeDisabled();
});
