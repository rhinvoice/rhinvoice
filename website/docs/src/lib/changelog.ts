/**
 * The release notes of the docs: CHANGELOG.md of the repository in English and its German twin
 * src/data/CHANGELOG.de.md, read at build time. Both carry the same version headings
 * (scripts/check.py makes sure).
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { marked } from "marked";

/** The builds run in website/docs; the repository's changelog lies two folders up. */
const SOURCES = {
  en: resolve(process.cwd(), "../../CHANGELOG.md"),
  de: resolve(process.cwd(), "src/data/CHANGELOG.de.md"),
} as const;

export type ChangelogLang = keyof typeof SOURCES;

export interface Release {
  readonly version: string;
  readonly date: string;
  /** The heading's id on the release notes page, e.g. "v0-5-0". */
  readonly anchor: string;
  readonly sections: readonly { readonly title: string; readonly html: string }[];
}

const RELEASE = /^## \[(\d+\.\d+\.\d+)\](?: – (\d{4}-\d{2}-\d{2}))?\s*$/;
const SECTION = /^### (.+?)\s*$/;

export function anchorOf(version: string): string {
  return `v${version.replaceAll(".", "-")}`;
}

/** Parse a changelog in the "Keep a Changelog" shape; unreleased changes are left out. */
export function parseChangelog(text: string): Release[] {
  const releases: { version: string; date: string; sections: { title: string; lines: string[] }[] }[] = [];
  let skipping = true;
  for (const line of text.split("\n")) {
    const release = RELEASE.exec(line);
    if (release) {
      releases.push({ version: release[1] ?? "", date: release[2] ?? "", sections: [] });
      skipping = false;
      continue;
    }
    if (line.startsWith("## ")) {
      // "## [Unreleased]" and anything else that is no release.
      skipping = true;
      continue;
    }
    const current = releases.at(-1);
    if (skipping || current === undefined) continue;
    const section = SECTION.exec(line);
    if (section) {
      current.sections.push({ title: section[1] ?? "", lines: [] });
    } else {
      current.sections.at(-1)?.lines.push(line);
    }
  }
  return releases.map(({ version, date, sections }) => ({
    version,
    date,
    anchor: anchorOf(version),
    sections: sections.map(({ title, lines }) => ({
      title,
      html: marked.parse(lines.join("\n").trim(), { async: false }),
    })),
  }));
}

export function releases(lang: ChangelogLang): Release[] {
  return parseChangelog(readFileSync(SOURCES[lang], "utf8"));
}

/** Where a version's notes are, for "since version …" badges. */
export function releaseHref(version: string, lang: string): string {
  const base = lang === "de" ? "/docs/de/help/changelog/" : "/docs/help/changelog/";
  return `${base}#${anchorOf(version)}`;
}
