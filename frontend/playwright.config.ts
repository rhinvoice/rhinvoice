import { defineConfig, devices } from "@playwright/test";

/**
 * E2E tests run inside the official Playwright container against the real
 * stack (see compose.e2e.yml) so that screenshots are identical everywhere.
 */
const baseURL = process.env.E2E_BASE_URL ?? "http://127.0.0.1:8000";
const authFile = "e2e/.auth/user.json";

export default defineConfig({
  testDir: "./e2e",
  outputDir: "./test-results",
  snapshotPathTemplate: "{testDir}/__screenshots__/{testFilePath}/{arg}-{projectName}{ext}",
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  // Locally a missing screenshot is written; in CI it fails, so baselines cannot get lost.
  updateSnapshots: process.env.CI ? "none" : "missing",
  expect: {
    // Rendering in the container is deterministic, so the tolerance can be tight.
    toHaveScreenshot: {
      maxDiffPixelRatio: 0.002,
      animations: "disabled",
      caret: "hide",
      // The version changes with every release; the screenshots compare the layout.
      stylePath: "./e2e/screenshot.css",
    },
  },
  use: {
    baseURL,
    locale: "de-CH",
    timezoneId: "Europe/Zurich",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "setup", testMatch: /global\.setup\.ts/ },
    {
      name: "desktop-light",
      dependencies: ["setup"],
      use: { ...devices["Desktop Chrome"], colorScheme: "light", storageState: authFile },
    },
    {
      name: "desktop-dark",
      dependencies: ["setup"],
      use: { ...devices["Desktop Chrome"], colorScheme: "dark", storageState: authFile },
    },
    {
      name: "mobile-light",
      dependencies: ["setup"],
      use: { ...devices["Pixel 7"], colorScheme: "light", storageState: authFile },
    },
    {
      name: "mobile-dark",
      dependencies: ["setup"],
      use: { ...devices["Pixel 7"], colorScheme: "dark", storageState: authFile },
    },
  ],
});
