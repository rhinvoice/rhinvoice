#!/usr/bin/env python3
"""Check the docs beyond what the build checks: content rules, then the built site.

    python3 scripts/check.py content   # before the build: pages, frontmatter, wording
    python3 scripts/check.py links     # after the build: every link into /docs/ leads to a page

The rules come from WRITING.md. A failed rule prints the file and what to change.
"""

from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "src" / "content" / "docs"
CHANGELOG = ROOT.parent.parent / "CHANGELOG.md"
CHANGELOG_DE = ROOT / "src" / "data" / "CHANGELOG.de.md"
VERSION_HEADING = re.compile(r"^## \[.+?\].*$", re.M)
RELEASE = re.compile(r"^## \[(\d+\.\d+\.\d+)\]", re.M)
SINCE = re.compile(r'^since:\s*"?([\d.]+)"?\s*$|<Since version="([\d.]+)"', re.M)
DIST = ROOT.parent / "dist" / "docs"
SITE = ROOT.parent / "dist"

TITLE_MAX = 65
DESCRIPTION_RANGE = (110, 170)
FAQ_MIN = 3
# Drafts are not published.
FORBIDDEN = re.compile(r"\b(TODO|TBD|lorem)\b", re.IGNORECASE)


def frontmatter(text: str) -> dict[str, str] | None:
    """The top-level scalar fields of a page's YAML frontmatter (enough for these checks)."""
    match = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if match is None:
        return None
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        top = re.match(r"([a-z_]+):\s*(.*)$", line)
        if top is not None:
            fields[top.group(1)] = top.group(2).strip().strip("\"'")
    fields["faq_count"] = str(len(re.findall(r"^\s+- q:", match.group(1), re.M)))
    return fields


def _outside_quotes(text: str) -> str:
    """The text without «quotations» and > block quotes: a quoted German notice keeps its «ß»."""
    text = re.sub(r"«[^»]*»", "", text)
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith(">"))


def check_changelog() -> list[str]:
    """The German release notes carry the same version headings as CHANGELOG.md, in order."""
    if not CHANGELOG_DE.is_file():
        return [f"{CHANGELOG_DE.relative_to(ROOT)}: the German release notes are missing"]
    english = VERSION_HEADING.findall(CHANGELOG.read_text(encoding="utf-8"))
    german = VERSION_HEADING.findall(CHANGELOG_DE.read_text(encoding="utf-8"))
    if english == german:
        return []
    missing = [heading for heading in english if heading not in german]
    extra = [heading for heading in german if heading not in english]
    detail = f"missing {missing}" if missing else f"not in CHANGELOG.md {extra}" if extra else "order differs"
    return [f"{CHANGELOG_DE.relative_to(ROOT)}: version headings differ from CHANGELOG.md, {detail}"]


def check_content() -> list[str]:
    problems: list[str] = check_changelog()
    released = set(RELEASE.findall(CHANGELOG.read_text(encoding="utf-8")))
    pages = sorted(CONTENT.rglob("*.md*"))
    english = {p.relative_to(CONTENT) for p in pages if p.relative_to(CONTENT).parts[0] != "de"}
    german = {p.relative_to(CONTENT / "de") for p in pages if p.relative_to(CONTENT).parts[0] == "de"}
    for missing in sorted(english - german):
        problems.append(f"de/{missing}: the German page is missing")
    for missing in sorted(german - english):
        problems.append(f"{missing}: the English page is missing")
    for page in pages:
        name = page.relative_to(CONTENT)
        text = page.read_text(encoding="utf-8")
        fields = frontmatter(text)
        if fields is None:
            problems.append(f"{name}: no frontmatter")
            continue
        title, description = fields.get("title", ""), fields.get("description", "")
        if not title or len(title) > TITLE_MAX:
            problems.append(f"{name}: title must have 1 to {TITLE_MAX} characters ({len(title)})")
        low, high = DESCRIPTION_RANGE
        if not low <= len(description) <= high:
            problems.append(f"{name}: description should have {low}–{high} characters ({len(description)})")
        if int(fields["faq_count"]) < FAQ_MIN:
            problems.append(f"{name}: at least {FAQ_MIN} questions in faq")
        elif "<Faq />" not in text:
            problems.append(f"{name}: the faq is not shown, add <Faq /> at the end")
        for match in SINCE.finditer(text):
            version = match.group(1) or match.group(2)
            if version not in released:
                problems.append(f"{name}: since version {version} is no release in CHANGELOG.md")
        if (found := FORBIDDEN.search(text)) is not None:
            problems.append(f"{name}: must not contain «{found.group(0)}»")
        if name.parts[0] == "de" and "ß" in _outside_quotes(text):
            problems.append(f"{name}: Swiss spelling, write «ss» instead of «ß»")
    return problems


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        href = dict(attrs).get("href")
        if tag == "a" and href is not None:
            self.links.append(href)


def check_links() -> list[str]:
    problems: list[str] = []
    if not DIST.is_dir():
        return [f"{DIST}: build the docs first (pnpm build)"]
    for html in sorted(DIST.rglob("*.html")):
        parser = _Links()
        parser.feed(html.read_text(encoding="utf-8"))
        for href in parser.links:
            path = href.split("#")[0].split("?")[0]
            if path.startswith("/docs/"):
                target = DIST / path.removeprefix("/docs/")
            elif path.startswith("/") and (SITE / "index.html").is_file():
                # A page of the landing site, checked once build.py has built it next to the docs.
                target = SITE / path.removeprefix("/")
            else:
                continue
            if not (target / "index.html").is_file() and not target.is_file():
                problems.append(f"{html.relative_to(DIST)}: link to {href} leads nowhere")
    return problems


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    checks = {"content": check_content, "links": check_links}
    if mode not in checks:
        print(__doc__)
        return 2
    problems = checks[mode]()
    for problem in problems:
        print(f"✗ {problem}")
    if not problems:
        print(f"✔ docs {mode} ok")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
