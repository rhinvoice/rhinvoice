import type { Locale } from "@/lib/locale";

/** Where Rhinvoice comes from: its version, its home and its maker. */
export const APP_VERSION: string = import.meta.env.VITE_APP_VERSION;

export const REPOSITORY_URL = "https://github.com/rhinvoice/rhinvoice";
export const ISSUES_URL = `${REPOSITORY_URL}/issues/new/choose`;
export const CHANGELOG_URL = `${REPOSITORY_URL}/blob/main/CHANGELOG.md`;
export const LICENSE_URL = `${REPOSITORY_URL}/blob/main/LICENSE`;

export const WEBSITE_URL = "https://rhinvoice.com/";
export const DOCS_URL = "https://rhinvoice.com/docs/";

/** The legal notice and privacy notice of rhinvoice.com and its public demos. */
export function legalUrls(locale: Locale): { notice: string; privacy: string } {
  return locale.startsWith("de")
    ? { notice: `${WEBSITE_URL}de/impressum/`, privacy: `${WEBSITE_URL}de/datenschutz/` }
    : { notice: `${WEBSITE_URL}legal-notice/`, privacy: `${WEBSITE_URL}privacy/` };
}

/** rhinvoice.com, in German for the German locales. */
export function websiteUrl(locale: Locale): string {
  return `${WEBSITE_URL}${locale.startsWith("de") ? "de/" : ""}`;
}

/** A page of the user docs (e.g. "operations/backup"), in German for the German locales. */
export function docsUrl(page: string, locale: Locale): string {
  return `${DOCS_URL}${locale.startsWith("de") ? "de/" : ""}${page}/`;
}

export const MAKER = "webberz";
export const MAKER_URL = "https://www.webberz.ch";
