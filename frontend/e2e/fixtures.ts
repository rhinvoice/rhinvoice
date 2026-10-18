import { readFile } from "node:fs/promises";

import AxeBuilder from "@axe-core/playwright";
import { expect, test as base, type BrowserContext, type Page } from "@playwright/test";

export const ADMIN = {
  email: "admin@example.com",
  name: "Anna Muster",
  password: "correct horse battery staple",
} as const;

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

/** Wait until all running CSS animations and transitions have finished. */
export async function settle(page: Page): Promise<void> {
  await page.evaluate(() =>
    // Cancelled animations reject "finished"; they are settled as well.
    Promise.all(
      document.getAnimations().map((animation) => animation.finished.catch(() => undefined)),
    ),
  );
}

/**
 * WCAG 2.5.8: every visible target is at least 24 × 24 CSS px. Measured on the
 * element itself, independent of the scroll position. (axe's target-size rule
 * also reports targets that are momentarily partly scrolled under the fixed
 * mobile tab bar; focus visibility there is handled by scroll-padding, 2.4.11.)
 */
export async function expectTargetSizes(page: Page): Promise<void> {
  const small = await page
    .locator(
      "button:visible, a:visible, [role=button]:visible, input:visible, select:visible, [role=switch]:visible",
    )
    .evaluateAll((elements) =>
      elements
        // Exceptions of 2.5.8: inline links in text, controls whose (larger)
        // label is the actual target, and elements hidden from users.
        .filter((element) => !(element.tagName === "A" && element.closest("p, li") !== null))
        .filter(
          (element) => !(element instanceof HTMLInputElement && element.closest("label") !== null),
        )
        .filter((element) => element.closest("[aria-hidden=true]") === null)
        // Toasts beyond the visible limit or on their way out are not targets.
        .filter(
          (element) =>
            element.closest("[data-sonner-toast][data-visible=false], [data-removed=true]") ===
            null,
        )
        .map((element) => ({ element, box: element.getBoundingClientRect() }))
        // Half a pixel of tolerance for sub-pixel layout (e.g. transformed toasts).
        .filter(({ box }) => box.width > 0 && (box.width < 23.5 || box.height < 23.5))
        .map(
          ({ element, box }) =>
            `${String(Math.round(box.width))}×${String(Math.round(box.height))} ${element.outerHTML.slice(0, 100)}`,
        ),
    );
  expect(small, "targets smaller than 24 × 24 px").toEqual([]);
}

/** Run axe-core against the current page; any WCAG 2.2 AA violation fails the test. */
export async function expectAccessible(page: Page): Promise<void> {
  await settle(page);
  await expectTargetSizes(page);
  const results = await new AxeBuilder({ page })
    .withTags(WCAG_TAGS)
    .disableRules(["target-size"])
    // The document pages run no scripts, so axe cannot enter them; they are
    // checked on their own with expectDocumentAccessible.
    .exclude("iframe[data-paper]")
    .analyze();
  const summary = results.violations.map(
    (violation) =>
      `${violation.id} (${violation.impact ?? "n/a"}): ${violation.nodes
        .map((node) => node.target.join(" "))
        .join(", ")}`,
  );
  expect(summary, "axe-core WCAG violations").toEqual([]);
}

/** Wait until transient toasts have closed (they must not end up in screenshots). */
export async function waitForToastsToClose(page: Page): Promise<void> {
  await expect(page.locator("[data-sonner-toast]")).toHaveCount(0, { timeout: 15_000 });
}

/** Open a page of the app shell and wait until it is interactive. */
export async function openApp(page: Page, path: string, heading: string): Promise<void> {
  await page.goto(path);
  await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
}

/** A suffix that keeps test data of the four projects apart in the shared database. */
export function unique(projectName: string): string {
  return projectName.replace(/[^a-z]/g, "").slice(0, 12);
}

export const HEADERS = { "X-Rhinvoice-Client": "e2e" };

/** The session that the global setup saved (playwright.config.ts). */
export const AUTH_FILE = "e2e/.auth/user.json";

type Cookies = Parameters<BrowserContext["addCookies"]>[0];

/**
 * Answer this page's sign-ins with the session of the global setup.
 *
 * The server allows 10 sign-ins per minute and address (ADR 0034), and all projects
 * run from one address: only the test of the login itself signs in for real. Tests
 * of what happens around a sign-in (redirects, an ended session) use this instead.
 */
export async function signInWithSetupSession(page: Page): Promise<void> {
  const saved = JSON.parse(await readFile(AUTH_FILE, "utf-8")) as { cookies: Cookies };
  await page.route("**/api/auth/login", async (route) => {
    await page.context().addCookies(saved.cookies);
    await route.fulfill({ response: await page.request.get("/api/auth/me") });
  });
}

export async function post<T>(page: Page, path: string, data: unknown): Promise<T> {
  const response = await page.request.post(path, { data, headers: HEADERS });
  expect(response.ok(), `${path}: ${await response.text()}`).toBe(true);
  return (await response.json()) as T;
}

/** A date relative to today in the browser's time zone (playwright.config.ts). */
export function isoDaysFromToday(days: number): string {
  // en-CA formats as YYYY-MM-DD; calendar arithmetic in UTC avoids DST shifts.
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Zurich" }).format(new Date());
  const date = new Date(`${today}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

export async function createCustomer(page: Page, name: string): Promise<string> {
  const customer = await post<{ id: string }>(page, "/api/customers", {
    kind: "company",
    company_name: name,
    address: {
      street: "Marktgasse",
      house_number: "5",
      postal_code: "3011",
      city: "Bern",
      country: "CH",
    },
  });
  return customer.id;
}

/** Customer of the overdue invoice created by the global setup. */
export const OVERDUE_CUSTOMER = "Saumselig GmbH";

export const test = base;
export { expect };

/** Check the print page of a document (the HTML behind preview and PDF) on its own. */
export async function expectDocumentAccessible(page: Page, documentId: string): Promise<void> {
  const response = await page.request.get(`/api/documents/${documentId}/html`);
  expect(response.ok()).toBe(true);
  const checker = await page.context().newPage();
  try {
    await checker.setContent(await response.text());
    const results = await new AxeBuilder({ page: checker }).withTags(WCAG_TAGS).analyze();
    expect(results.violations.map((violation) => violation.id)).toEqual([]);
  } finally {
    await checker.close();
  }
}
