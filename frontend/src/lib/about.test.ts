import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import {
  APP_VERSION,
  CHANGELOG_URL,
  ISSUES_URL,
  LICENSE_URL,
  REPOSITORY_URL,
  docsUrl,
  legalUrls,
  websiteUrl,
} from "@/lib/about";

describe("about", () => {
  it("shows the version of package.json", () => {
    const pkg = JSON.parse(readFileSync("package.json", "utf8")) as { version: string };
    expect(APP_VERSION).toBe(pkg.version);
  });

  it("links into the repository", () => {
    expect(REPOSITORY_URL).toBe("https://github.com/rhinvoice/rhinvoice");
    for (const url of [ISSUES_URL, CHANGELOG_URL, LICENSE_URL]) {
      expect(url.startsWith(`${REPOSITORY_URL}/`)).toBe(true);
    }
  });

  it("links to the website in the language of the interface", () => {
    expect(websiteUrl("de-CH")).toBe("https://rhinvoice.com/de/");
    expect(websiteUrl("en")).toBe("https://rhinvoice.com/");
  });

  it("names the legal pages of the website", () => {
    expect(legalUrls("de-AT")).toEqual({
      notice: "https://rhinvoice.com/de/impressum/",
      privacy: "https://rhinvoice.com/de/datenschutz/",
    });
    expect(legalUrls("en")).toEqual({
      notice: "https://rhinvoice.com/legal-notice/",
      privacy: "https://rhinvoice.com/privacy/",
    });
  });

  it("links into the docs in the language of the interface", () => {
    expect(docsUrl("operations/backup", "de-AT")).toBe(
      "https://rhinvoice.com/docs/de/operations/backup/",
    );
    expect(docsUrl("operations/backup", "en")).toBe(
      "https://rhinvoice.com/docs/operations/backup/",
    );
  });
});
