import { expect, expectAccessible, test } from "./fixtures";

test.use({ storageState: { cookies: [], origins: [] } });

test("on a server the page names the commands for the administrator", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("link", { name: "Passwort vergessen?" }).click();
  await expect(page).toHaveTitle("Passwort vergessen · Rhinvoice");
  await expect(
    page.getByText(
      "docker compose exec app rhinvoice user reset-password --email name@example.com",
    ),
  ).toBeVisible();
  await expect(page.getByText("docker compose exec app rhinvoice user list")).toBeVisible();
  await expectAccessible(page);
  await expect(page).toHaveScreenshot("password-reset-server.png");
  await page.getByRole("link", { name: "Zurück zur Anmeldung" }).click();
  await expect(page).toHaveURL(/\/login/);
});

test("without Docker a code from the data folder sets a new password", async ({ page }) => {
  // The Docker stack under test has no data folder for codes: the installation without
  // Docker only differs in what these requests answer.
  const location = "C:\\Users\\Anna\\AppData\\Local\\Rhinvoice\\Rhinvoice-Passwort-Password.txt";
  await page.route("**/api/auth/password-reset", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({ json: { method: "file", location } });
    } else {
      await route.fulfill({ status: 204 });
    }
  });
  let tries = 0;
  await page.route("**/api/auth/password-reset/confirm", async (route) => {
    tries += 1;
    await (tries === 1
      ? route.fulfill({
          status: 409,
          json: {
            error: {
              code: "reset_code_invalid",
              message: "the e-mail address or the code is not valid",
            },
          },
        })
      : route.fulfill({ status: 204 }));
  });
  await page.goto("/password-reset");
  await page.getByRole("button", { name: "Code anfordern" }).click();
  await expect(page.getByText(location)).toBeVisible();
  await expect(page.getByRole("button", { name: "Neuen Code anfordern" })).toBeVisible();

  await page.getByRole("button", { name: "Passwort speichern" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "3 Angaben" })).toBeFocused();

  await page.getByLabel("E-Mail-Adresse").fill("anna@example.com");
  await page.getByLabel("Code", { exact: true }).fill("K7QM2-XWP9D");
  await page.getByLabel("Neues Passwort").fill("a new and long passphrase");
  await page.getByRole("button", { name: "Passwort speichern" }).click();
  await expect(page.getByText(/Code stimmt nicht/)).toBeVisible();
  await expectAccessible(page);
  await expect(page).toHaveScreenshot("password-reset-file.png");

  await page.getByRole("button", { name: "Passwort speichern" }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "Das Passwort ist geändert." }),
  ).toBeVisible();
  await expectAccessible(page);
  await page.getByRole("link", { name: "Zur Anmeldung" }).click();
  await expect(page).toHaveURL(/\/login/);
});
