import { expect, expectAccessible, openApp, test } from "./fixtures";

test("the dashboard lists the setup steps until they are done", async ({ page }) => {
  await openApp(page, "/", "Übersicht");
  const checklist = page.getByRole("region", { name: "Willkommen bei Rhinvoice" });
  await expect(checklist).toBeVisible();
  await expect(checklist.getByText(/^Einrichtung · \d von 6 erledigt$/)).toBeVisible();
  // The company and its bank account exist (global setup).
  await expect(checklist.getByText("Land und Firma – erledigt")).toBeAttached();
  await expect(checklist.getByText("Bankkonto erfassen – erledigt")).toBeAttached();
  await expect(checklist.getByText("Backup einrichten – offen")).toBeAttached();
  await expectAccessible(page);

  const numbering = checklist.getByRole("button", { name: "Prüfen" });
  if (await numbering.isVisible()) {
    await numbering.click();
    await expect(page.getByRole("tab", { name: "Nummernkreise", selected: true })).toBeVisible();
    await page.goBack();
  }
  await expect(checklist.getByText("Nummernkreise prüfen – erledigt")).toBeAttached();

  // Hiding is permanent; here only the answer of the server is played back.
  await page.route("**/api/onboarding/dismiss", async (route) => {
    const response = await route.fetch({
      method: "GET",
      url: route.request().url().replace("/dismiss", ""),
    });
    const body = (await response.json()) as Record<string, unknown>;
    await route.fulfill({ json: { ...body, dismissed: true } });
  });
  await checklist.getByRole("button", { name: "Checkliste ausblenden" }).click();
  await expect(checklist).toBeHidden();
});

test("the wizard can be left for later", async ({ page }) => {
  // A new installation: no company yet.
  await page.route("**/api/company", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({
        status: 404,
        json: { error: { code: "not_found", message: "no company", details: {} } },
      });
    } else {
      await route.fallback();
    }
  });
  await page.goto("/");
  await expect(page).toHaveURL(/\/welcome$/);
  await page.getByRole("radio", { name: /^Deutschland/ }).check();
  await expect(page.getByText("Kleinunternehmer nach § 19 UStG")).toBeVisible();
  await page.getByRole("button", { name: "Später einrichten" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Übersicht" })).toBeVisible();
  // The browser remembers the choice: the overview no longer sends it to the wizard.
  await page.reload();
  await expect(page.getByRole("heading", { level: 1, name: "Übersicht" })).toBeVisible();
});

test("the wizard is left out once the company exists", async ({ page }) => {
  await page.goto("/welcome");
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("heading", { level: 1, name: "Übersicht" })).toBeVisible();
});
