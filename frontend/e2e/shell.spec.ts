import { expect, expectAccessible, openApp, test } from "./fixtures";

test.describe("app shell", () => {
  test("shows the dashboard with a skip link and one h1", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveTitle("Übersicht · Rhinvoice");
    await expect(page.getByRole("heading", { level: 1 })).toHaveCount(1);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Übersicht");
    // Earlier specs created documents: wait for the figures, then mask the data.
    await expect(page.getByRole("region", { name: "Kennzahlen in CHF" })).toBeVisible();
    await expectAccessible(page);
    // Layout and labels are compared; amounts, counts, the chart and the
    // activity list depend on the documents of earlier specs.
    await expect(page).toHaveScreenshot("dashboard.png", {
      mask: [
        page.locator("[data-cockpit] .tabular-nums"),
        page.locator("[data-cockpit] [data-slot=card] .text-xs"),
        page.locator("[data-cockpit] [data-slot=card] a"),
        page.locator("[data-cockpit] figure"),
        page.locator("[data-cockpit] ol"),
        page.locator("[data-cockpit] ul"),
        page.locator("[data-cockpit] dl"),
      ],
    });
    await page.keyboard.press("Tab");
    const skip = page.getByRole("link", { name: "Zum Inhalt springen" });
    await expect(skip).toBeFocused();
    await expect(skip).toBeInViewport();
    await page.keyboard.press("Enter");
    await expect(page.locator("main#main")).toBeFocused();
  });

  test("navigates with the sidebar or the mobile tab bar", async ({ page, isMobile }) => {
    await openApp(page, "/", "Übersicht");
    const nav = page.getByRole("navigation", { name: "Hauptnavigation" }).filter({ visible: true });
    await nav.getByRole("link", { name: "Kunden" }).first().click();
    await expect(page).toHaveURL(/\/customers$/);
    await expect(page.getByRole("heading", { level: 1, name: "Kunden" })).toBeVisible();
    await expect(nav.getByRole("link", { name: "Kunden" }).first()).toHaveAttribute(
      "aria-current",
      "page",
    );
    if (isMobile) {
      await page.getByRole("button", { name: "Menü öffnen" }).click();
      const drawer = page.getByRole("dialog");
      await expect(drawer).toBeVisible();
      await expectAccessible(page);
      await drawer.getByRole("link", { name: "Einstellungen" }).click();
      await expect(drawer).toBeHidden();
      await expect(page).toHaveURL(/\/settings$/);
    }
  });

  test("opens the command palette with the keyboard and navigates", async ({ page, isMobile }) => {
    test.skip(isMobile, "keyboard shortcuts are a desktop feature");
    await openApp(page, "/", "Übersicht");
    // The dashboard behind the palette must have finished loading its data.
    await expect(page.getByRole("region", { name: "Kennzahlen in CHF" })).toBeVisible();
    await page.keyboard.press("ControlOrMeta+k");
    const palette = page.getByRole("dialog");
    await expect(palette).toBeVisible();
    await expectAccessible(page);
    await expect(page).toHaveScreenshot("command-palette.png", {
      mask: [page.locator("main [data-slot=card]")],
    });
    await page.keyboard.type("Artikel");
    await palette.getByRole("option", { name: /^Artikel(?! importieren)/ }).click();
    await expect(palette).toBeHidden();
    await expect(page).toHaveURL(/\/articles$/);
  });

  test("supports single key shortcuts and the shortcut overview", async ({ page, isMobile }) => {
    test.skip(isMobile, "keyboard shortcuts are a desktop feature");
    await openApp(page, "/", "Übersicht");
    await page.keyboard.press("Shift+?");
    const dialog = page.getByRole("dialog", { name: "Tastaturkürzel" });
    await expect(dialog).toBeVisible();
    await expectAccessible(page);
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    await page.keyboard.press("g");
    await page.keyboard.press("s");
    await expect(page.getByRole("heading", { level: 1, name: "Einstellungen" })).toBeVisible();
    await expect(page).toHaveURL(/\/settings$/);
    await page.keyboard.press("n");
    await expect(page).toHaveURL(/\/invoices\/new$/);
  });

  test("switches the colour scheme", async ({ page }) => {
    await openApp(page, "/", "Übersicht");
    await page.getByRole("button", { name: "Farbschema" }).click();
    await page.getByRole("menuitemradio", { name: "Dunkel" }).click();
    await expect(page.locator("html")).toHaveClass(/dark/);
    await page.reload();
    await expect(page.locator("html")).toHaveClass(/dark/);
    await page.getByRole("button", { name: "Farbschema" }).click();
    await page.getByRole("menuitemradio", { name: "System" }).click();
  });

  test("switches the interface language", async ({ page }) => {
    await openApp(page, "/", "Übersicht");
    await page.getByRole("button", { name: "Sprache" }).click();
    await page.getByRole("menuitemradio", { name: "English" }).click();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Overview");
    await page.reload();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Overview");
    await page.getByRole("button", { name: "Language" }).click();
    await page.getByRole("menuitemradio", { name: "Deutsch (Österreich)" }).click();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Übersicht");
    await expect(page.locator("html")).toHaveAttribute("lang", "de-AT");
  });

  test("tells version, licence and maker", async ({ page, isMobile }) => {
    await openApp(page, "/", "Übersicht");
    if (isMobile) {
      await page.getByRole("button", { name: "Konto" }).click();
      await page.getByRole("menuitem", { name: "Über Rhinvoice" }).click();
    } else {
      await page.getByRole("button", { name: /^Über Rhinvoice:.*by webberz/ }).click();
    }
    const dialog = page.getByRole("dialog", { name: "Über Rhinvoice" });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText(/^Version \d+\.\d+\.\d+$/)).toBeVisible();
    await expect(
      dialog.getByRole("link", { name: /GNU Affero General Public License/ }),
    ).toHaveAttribute("href", "https://github.com/rhinvoice/rhinvoice/blob/main/LICENSE");
    await expect(dialog.getByRole("link", { name: /Fehler melden/ })).toHaveAttribute(
      "href",
      "https://github.com/rhinvoice/rhinvoice/issues/new/choose",
    );
    await expect(dialog.getByRole("link", { name: /made by webberz/ })).toHaveAttribute(
      "href",
      "https://www.webberz.ch",
    );
    await expectAccessible(page);
    await expect(dialog).toHaveScreenshot("about.png");
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
  });

  test("has interactive targets of at least 24 × 24 px (WCAG 2.5.8)", async ({ page }) => {
    await openApp(page, "/", "Übersicht");
    const small = await page
      .locator("button:visible, a:visible, [role=button]:visible")
      .evaluateAll((elements) =>
        elements
          .map((element) => ({ element, box: element.getBoundingClientRect() }))
          .filter(({ box }) => box.width < 24 || box.height < 24)
          .map(({ element }) => element.outerHTML.slice(0, 80)),
      );
    expect(small).toEqual([]);
    await page.keyboard.press("Tab");
    const skip = await page
      .getByRole("link", { name: "Zum Inhalt springen" })
      .evaluate((element) => element.getBoundingClientRect());
    expect(skip.width).toBeGreaterThanOrEqual(24);
    expect(skip.height).toBeGreaterThanOrEqual(24);
  });
});
