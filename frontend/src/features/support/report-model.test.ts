import { describe, expect, it } from "vitest";

import {
  issueUrl,
  reportHeader,
  reportText,
  type SupportReport,
} from "@/features/support/report-model";

function report(overrides: Partial<SupportReport> = {}): SupportReport {
  return {
    version: "0.7.4",
    system: "Windows 11 (AMD64)",
    installation: "desktop",
    log: "INFO: started\nERROR: no printer",
    ...overrides,
  };
}

describe("reportText", () => {
  it("puts what runs where above the end of the log", () => {
    expect(reportText(report())).toBe(
      "Rhinvoice 0.7.4 · Windows 11 (AMD64) · program for Windows and Mac\n" +
        "--- end of rhinvoice.log ---\nINFO: started\nERROR: no printer",
    );
  });

  it("says so when there is no log", () => {
    expect(reportText(report({ log: "" }))).toMatch(/\(no log\)$/);
    expect(reportText(report({ installation: "server", log: null }))).toMatch(
      /^Rhinvoice 0\.7\.4 · Windows 11 \(AMD64\) · Docker\n.*\(no log\)$/s,
    );
  });
});

describe("issueUrl", () => {
  it("opens the bug report with the version and the system filled in", () => {
    const url = new URL(issueUrl(report()));
    expect(url.origin + url.pathname).toBe("https://github.com/rhinvoice/rhinvoice/issues/new");
    expect(url.searchParams.get("template")).toBe("bug_report.yml");
    expect(url.searchParams.get("version")).toBe("0.7.4");
    expect(url.searchParams.get("browser")).toBe(reportHeader(report()));
  });
});
