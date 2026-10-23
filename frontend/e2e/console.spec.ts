import { createCustomer, expect, openApp, test, unique } from "./fixtures";

// Playwright's traces and frame locators inject scripts into the sandboxed paper frame,
// which Chromium reports as blocked; without them only the app's own messages remain.
test.use({ trace: "off" });

test("the editor and its paper preview run without script errors", async ({
  page,
  isMobile,
}, testInfo) => {
  // Phones show the paper on a tab of its own; one layout is enough here.
  test.skip(isMobile, "desktop layout only");
  const problems: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") problems.push(message.text());
  });
  page.on("pageerror", (error) => problems.push(error.message));
  const customerName = `Konsole ${unique(testInfo.project.name)} AG`;
  await createCustomer(page, customerName);
  await openApp(page, "/invoices/new", "Neue Rechnung");
  await page.getByRole("combobox", { name: "Kunde suchen" }).fill(customerName);
  await page.getByRole("option", { name: new RegExp(customerName) }).click();
  await page.locator("#lines-0-description").fill("Beratung");
  await page.locator("#lines-0-unit_price").fill("100");
  await expect(page.locator("iframe[data-paper]")).toHaveAttribute("srcdoc", /Beratung/);
  expect(problems).toEqual([]);
});
