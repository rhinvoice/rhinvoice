import type { components } from "@/api/client";
import { REPOSITORY_URL } from "@/lib/about";

export type SupportReport = components["schemas"]["SupportReportResponse"];

export const SUPPORT_EMAIL = "hello@rhinvoice.com";
/** On a server the log stays with Docker; the person reads it there. */
export const SERVER_LOG_COMMAND = "docker compose logs --tail 200 app";

const INSTALLATION = {
  desktop: "program for Windows and Mac",
  server: "Docker",
} as const satisfies Record<SupportReport["installation"], string>;

/** One line that says what runs where, at the top of every report. */
export function reportHeader(report: SupportReport): string {
  return `Rhinvoice ${report.version} · ${report.system} · ${INSTALLATION[report.installation]}`;
}

/** What the person copies: the header and the end of the log, ready to paste. */
export function reportText(report: SupportReport): string {
  const log = report.log === null || report.log === "" ? "(no log)" : report.log;
  return `${reportHeader(report)}\n--- end of rhinvoice.log ---\n${log}`;
}

/** A new bug report on GitHub with the version and the system filled in. */
export function issueUrl(report: SupportReport): string {
  const params = new URLSearchParams({
    template: "bug_report.yml",
    version: report.version,
    browser: reportHeader(report),
  });
  return `${REPOSITORY_URL}/issues/new?${params.toString()}`;
}
