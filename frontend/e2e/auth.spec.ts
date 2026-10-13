import { ADMIN, expect, expectAccessible, openApp, test } from "./fixtures";

test.describe("authentication", () => {
  test.use({ storageState: { cookies: [], origins: [] } });

  test("redirects anonymous visitors to the login page", async ({ page }) => {
    await page.goto("/customers");
    await expect(page).toHaveURL(/\/login\?redirect=%2Fcustomers/);
    await expect(page).toHaveTitle("Anmelden · Rhinvoice");
    await expectAccessible(page);
    await expect(page).toHaveScreenshot("login.png");
  });

  test("switches the language and names version and maker", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByText(/^Rhinvoice \d+\.\d+\.\d+$/)).toBeVisible();
    await expect(page.getByRole("link", { name: /made by webberz/ })).toHaveAttribute(
      "href",
      "https://www.webberz.ch",
    );
    await expect(page.getByRole("link", { name: /Open Source/ })).toHaveAttribute(
      "href",
      "https://github.com/rhinvoice/rhinvoice",
    );
    await page.getByRole("button", { name: "Sprache" }).click();
    await expect(page.getByRole("menuitemradio", { name: "Deutsch (Schweiz)" })).toBeChecked();
    await page.getByRole("menuitemradio", { name: "English" }).click();
    await expect(page).toHaveTitle("Log in · Rhinvoice");
    await expect(page.locator("html")).toHaveAttribute("lang", "en");
    await page.reload();
    await expect(page.getByRole("button", { name: "Log in" })).toBeVisible();
    await expectAccessible(page);
  });

  test("validates the form and shows an error summary", async ({ page }) => {
    await page.goto("/login");
    await page.getByRole("button", { name: "Anmelden" }).click();
    const summary = page
      .getByRole("alert")
      .filter({ hasText: "2 Angaben müssen korrigiert werden" });
    await expect(summary).toBeVisible();
    await expect(summary).toBeFocused();
    await expect(page.getByLabel("E-Mail-Adresse")).toHaveAttribute("aria-invalid", "true");
    await expectAccessible(page);
  });

  test("rejects wrong credentials and logs in with correct ones", async ({ page }) => {
    await page.goto("/login?redirect=%2Fsettings");
    await page.getByLabel("E-Mail-Adresse").fill(ADMIN.email);
    await page.getByLabel("Passwort").fill("definitely the wrong password");
    await page.getByRole("button", { name: "Anmelden" }).click();
    await expect(page.getByText("E-Mail-Adresse oder Passwort ist falsch.")).toBeVisible();

    // Pasting into the password field must work (WCAG 3.3.8).
    await page.getByLabel("Passwort").fill(ADMIN.password);
    await page.getByRole("button", { name: "Anmelden" }).click();
    await expect(page).toHaveURL(/\/settings$/);
    await expect(page.getByRole("heading", { level: 1, name: "Einstellungen" })).toBeVisible();
  });

  test("ignores external redirect targets", async ({ page }) => {
    await page.goto("/login?redirect=https%3A%2F%2Fevil.example");
    await page.getByLabel("E-Mail-Adresse").fill(ADMIN.email);
    await page.getByLabel("Passwort").fill(ADMIN.password);
    await page.getByRole("button", { name: "Anmelden" }).click();
    await expect(page).toHaveURL(/\/$/);
  });
});

test("a session that ends while the app is open leads to the login, which says why", async ({
  page,
  baseURL,
}) => {
  await openApp(page, "/", "Übersicht");
  await page.waitForLoadState("networkidle");
  // The server no longer knows the session: expired, logged out elsewhere, or a demo reset.
  await page.context().addCookies([{ name: "rhinvoice_session", value: "ended", url: baseURL }]);
  const nav = page.getByRole("navigation", { name: "Hauptnavigation" }).filter({ visible: true });
  await nav.getByRole("link", { name: "Kunden" }).first().click();
  // Whichever request notices it first (the click, or the dashboard polling) leads there.
  await expect(page).toHaveURL(/\/login\?redirect=%2F(customers)?&expired=true$/);
  await expect(page.getByRole("status").filter({ hasText: "Sitzung ist abgelaufen" })).toHaveText(
    "Ihre Sitzung ist abgelaufen. Bitte melden Sie sich erneut an.",
  );
  // Not the message of a wrong password.
  await expect(page.getByText("E-Mail-Adresse oder Passwort ist falsch.")).toHaveCount(0);
  await expectAccessible(page);
  await page.getByLabel("E-Mail-Adresse").fill(ADMIN.email);
  await page.getByLabel("Passwort").fill(ADMIN.password);
  await page.getByRole("button", { name: "Anmelden" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(/^(Kunden|Übersicht)$/);

  // In the public demo the session ends with the hourly reset, and the login says so.
  await page.route("**/api/demo", async (route) => {
    const response = await route.fetch();
    const demo = (await response.json()) as Record<string, unknown>;
    await route.fulfill({ response, json: { ...demo, enabled: true, reset_minutes: 60 } });
  });
  await page.goto("/login?redirect=%2F&expired=true");
  await expect(page.getByRole("status").filter({ hasText: "zurückgesetzt" })).toHaveText(
    "Die Demo wurde zurückgesetzt, wie alle 60 Minuten. Dabei werden alle abgemeldet: Bitte melden Sie sich erneut an.",
  );
});
