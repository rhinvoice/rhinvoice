import { expect, openApp, test } from "./fixtures";

// Pages reached from a list lead back to it above their title, as the documents do.
const PAGES = [
  { path: "/dunning", title: "Mahnwesen", back: "Rechnungen" },
  { path: "/recurring", title: "Wiederkehrende Rechnungen", back: "Rechnungen" },
  { path: "/invoices/import", title: "Alte Rechnungen übernehmen", back: "Rechnungen" },
  { path: "/customers/import", title: "Kunden importieren", back: "Kunden" },
  { path: "/articles/import", title: "Artikel importieren", back: "Artikel" },
] as const;

for (const { path, title, back } of PAGES) {
  test(`${title} leads back to ${back}`, async ({ page }) => {
    await openApp(page, path, title);
    // The sidebar links to the same list; the way back sits in the page itself.
    await page.getByRole("main").getByRole("link", { name: back, exact: true }).click();
    await expect(page.getByRole("heading", { level: 1, name: back, exact: true })).toBeVisible();
  });
}
