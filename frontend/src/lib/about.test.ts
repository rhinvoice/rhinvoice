import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import {
  APP_VERSION,
  CHANGELOG_URL,
  IMPORT_GUIDE_URL,
  INSTALL_URL,
  ISSUES_URL,
  LICENSE_URL,
  REPOSITORY_URL,
} from "@/lib/about";

describe("about", () => {
  it("shows the version of package.json", () => {
    const pkg = JSON.parse(readFileSync("package.json", "utf8")) as { version: string };
    expect(APP_VERSION).toBe(pkg.version);
  });

  it("links into the repository", () => {
    expect(REPOSITORY_URL).toBe("https://github.com/rhinvoice/rhinvoice");
    for (const url of [ISSUES_URL, CHANGELOG_URL, LICENSE_URL, INSTALL_URL, IMPORT_GUIDE_URL]) {
      expect(url.startsWith(`${REPOSITORY_URL}/`)).toBe(true);
    }
  });
});
