#!/usr/bin/env python3
"""
rhinvoice.com — build the deployable folder (adapted from the build of webberz.ch).

    python3 website/build.py

Reads  website/site/   (the documented source — this is what you edit)
Writes website/dist/   (what GitHub Pages serves; not versioned)

What happens:
  *.css   comments removed, whitespace collapsed
  *.js    minified and mangled with terser (npm i -g terser)
  *.html  comments removed, indentation dropped; <pre> keeps its lines
  fonts, stylesheet and script get a content hash in their names.

The ASCII wordmark at the top of every HTML file is kept on purpose —
it is the only comment that survives.
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

SOURCE = Path(__file__).parent / "site"
DIST = Path(__file__).parent / "dist"
SKIP_FILES = {"README.md", ".DS_Store"}


def strip_comments(text, start="/*", end="*/"):
    """Strip block comments without touching quoted strings."""
    out = []
    i, n = 0, len(text)
    quote = None
    while i < n:
        c = text[i]
        if quote:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == quote:
                quote = None
            i += 1
            continue
        if c in "\"'`":
            quote = c
            out.append(c)
            i += 1
            continue
        if text.startswith(start, i):
            stop = text.find(end, i + len(start))
            i = n if stop == -1 else stop + len(end)
            continue
        out.append(c)
        i += 1
    return "".join(out)


def css_minify(text):
    """Block aware: selectors and declarations have different safe rules.

    Never touch whitespace around + - * / — CSS math needs it, and
    clamp(1rem, 0.95rem + 0.22vw, 1.115rem) silently dies without it.
    Never collapse ":" in selectors either, only inside declarations.
    """
    text = strip_comments(text)
    text = re.sub(r"\s+", " ", text).strip()

    out = []
    i, n = 0, len(text)
    while i < n:
        lbrace = text.find("{", i)
        if lbrace == -1:
            out.append(text[i:].strip())
            break
        sel = text[i:lbrace].strip()
        sel = re.sub(r"\s*([,>])\s*", r"\1", sel)
        rbrace = text.find("}", lbrace)
        if rbrace == -1:
            rbrace = n
        body = text[lbrace + 1:rbrace].strip()
        if "{" in body:                      # @media and friends
            out.append(sel + "{")
            i = lbrace + 1
            continue
        body = re.sub(r"\s*;\s*", ";", body)
        body = re.sub(r"\s*:\s*", ":", body)
        body = re.sub(r",\s+", ",", body)
        body = body.rstrip(";")
        out.append(sel + "{" + body + "}")
        i = rbrace + 1
    return "".join(out)


def js_minify(path):
    r = subprocess.run(
        ["terser", str(path), "--compress", "--mangle", "--format", "comments=false"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        print(f"  ! terser failed on {path.name}, using the original:\n{r.stderr[:300]}")
        return path.read_text(encoding="utf-8")
    return r.stdout




# Elements whose surrounding whitespace never shows up on screen.
# Everything not listed here is treated as inline, where a space between
# two tags is real text and must survive.
BLOCK = (
    "html head body div section article aside header footer main nav form picture source "
    "h1 h2 h3 h4 h5 h6 p ul ol li dl dt dd table thead tbody tr td th "
    "figure figcaption details summary fieldset legend script style link "
    "meta title address blockquote hr br svg g path rect line circle text "
    "polyline polygon defs"
).split()
BLOCK_RE = "|".join(BLOCK)


def html_minify(text):
    """Strip comments (except the ASCII wordmark) and all needless whitespace.

    Whitespace between two block elements renders as nothing, so it goes.
    Whitespace next to an inline element is real text and stays — collapsed
    to a single space. Getting this wrong glues words together, which is why
    every build is pixel-compared against site/.
    """
    kept = []

    def keep(m):
        if "█" in m.group(0):
            kept.append(m.group(0))
            return f"\x00{len(kept)-1}\x00"
        return ""

    text = re.sub(r"<!--.*?-->", keep, text, flags=re.S)

    # <pre> shows its whitespace: set it aside like the wordmark.
    pres = []

    def keep_pre(m):
        pres.append(m.group(0))
        return f"\x01{len(pres)-1}\x01"

    text = re.sub(r"<pre\b.*?</pre>", keep_pre, text, flags=re.S)

    # collapse every run of whitespace to one space
    text = re.sub(r"\s+", " ", text)
    # drop it entirely where both neighbours are block level
    text = re.sub(rf"(</(?:{BLOCK_RE})>|<(?:{BLOCK_RE})\b[^>]*>)\s+(?=<)", r"\1", text)
    text = re.sub(rf"\s+(?=</?(?:{BLOCK_RE})\b)", "", text)

    for i, b in enumerate(pres):
        text = text.replace(f"\x01{i}\x01", b)
    for i, b in enumerate(kept):
        text = text.replace(f"\x00{i}\x00", "\n" + b + "\n")
    return text.strip() + "\n"


def fingerprint():
    """Put a content hash into asset filenames and rewrite every reference.

    Without this, main.css keeps its name forever and browsers hold the old
    file for as long as the cache header says. With it, a changed file gets
    a new name, so it can be cached for a year and still update instantly.
    Fonts first — the stylesheet points at them.
    """
    import hashlib

    def short_hash(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()[:8]

    renamed = {}

    def add_hash(path):
        new_name = f"{path.stem}.{short_hash(path)}{path.suffix}"
        target = path.with_name(new_name)
        path.rename(target)
        renamed[path.name] = new_name
        return target

    def rewrite_refs(files, pairs):
        for d in files:
            t = d.read_text(encoding="utf-8")
            o = t
            for old_n, new_n in pairs.items():
                t = t.replace(old_n, new_n)
            if t != o:
                d.write_text(t, encoding="utf-8")

    css_files = list((DIST / "assets/css").glob("*.css"))
    html_files = list(DIST.rglob("*.html"))

    # 1. Fonts — only the stylesheet and the preload line in the HTML point at them
    fonts = {}
    for f in sorted((DIST / "assets/fonts").glob("*.woff2")):
        old_n = f.name
        fonts[old_n] = add_hash(f).name
    rewrite_refs(css_files + html_files, fonts)

    # 2. Stylesheet and script — only the HTML points at them
    others = {}
    for f in sorted((DIST / "assets/css").glob("*.css")) + sorted((DIST / "assets/js").glob("*.js")):
        others[f.name] = add_hash(f).name
    rewrite_refs(html_files, others)

    print("\n  Versioned filenames:")
    for a, b in {**fonts, **others}.items():
        print(f"    {a:28} -> {b}")


RELEASE_API = "https://api.github.com/repos/rhinvoice/rhinvoice/releases/latest"
SIZE = re.compile(r'<span class="dl-size" data-release-size="([^"]+)"></span>')
VERSION = "<span data-release-version></span>"


def latest_release():
    """Version and file sizes of the newest GitHub release, or None (offline, none yet).

    The page shows them next to the download buttons. They are put in here, at build
    time, so that visitors' browsers never ask GitHub themselves.
    """
    import json
    import os
    import urllib.request

    request = urllib.request.Request(RELEASE_API, headers={"Accept": "application/vnd.github+json"})
    if token := os.environ.get("GITHUB_TOKEN"):
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            release = json.load(response)
    except (OSError, ValueError) as error:
        print(f"  no release facts ({error}): the buttons show no size")
        return None
    sizes = {asset["name"]: asset["size"] for asset in release.get("assets", [])}
    return release["tag_name"].removeprefix("v"), sizes


def fill_release(text, release):
    """Put version and sizes into their placeholders; without a release, drop them."""
    version, sizes = release or ("", {})

    def size(match):
        found = sizes.get(match.group(1))
        if found is None:
            return ""
        return f' <span class="dl-size">{round(found / 1024 / 1024)} MB</span>'

    text = SIZE.sub(size, text)
    return text.replace(VERSION, f" {version}" if version else "")


# French and Italian pages were machine-translated. Each says so at the top, in its own
# language, with a way to report a wrong translation: one text here instead of a copy per page.
# A page asks for it with <div data-machine-translated></div> right after the skip link.
NOTICE = "<div data-machine-translated></div>"
MACHINE_TRANSLATED = {
    "fr": ("Cette page a été traduite automatiquement. Vos remarques sont les bienvenues :",
           "signaler une erreur de traduction sur GitHub", "ou écrire à", "French"),
    "it": ("Questa pagina è stata tradotta automaticamente. Le segnalazioni sono benvenute:",
           "segnalare un errore di traduzione su GitHub", "oppure scrivere a", "Italian"),
}


def fill_machine_translated(text):
    """Put the machine translation notice where the page asks for it, or fail the build."""
    if NOTICE not in text:
        return text
    from html import escape
    from urllib.parse import urlencode

    lang = re.search(r'<html lang="([a-z]+)"', text).group(1)
    page = re.search(r'<link rel="canonical" href="([^"]+)">', text).group(1)
    if lang not in MACHINE_TRANSLATED:
        sys.exit(f"no machine translation notice for language {lang!r} ({page})")
    lead, link, mail, language = MACHINE_TRANSLATED[lang]
    query = urlencode({"template": "translation.yml", "language": language, "page": page})
    href = escape(f"https://github.com/rhinvoice/rhinvoice/issues/new?{query}")
    notice = (
        f'<div class="mt-notice"><p class="wrap">{lead} <a href="{href}">{link}</a> {mail} '
        f'<span class="tabular">hello@rhinvoice.com</span>.</p></div>'
    )
    return text.replace(NOTICE, notice)


def main():
    if not SOURCE.is_dir():
        sys.exit(f"site/ not found at {SOURCE}")
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir()

    release = latest_release()
    if release:
        print(f"  release {release[0]}: " + ", ".join(f"{name} {size}" for name, size in release[1].items()))

    size_before = size_after = 0
    for src in sorted(SOURCE.rglob("*")):
        if src.is_dir() or src.name in SKIP_FILES:
            continue
        # editor leftovers (vim swap files, backups) never go on the server
        if src.suffix in {".swp", ".swo"} or src.name.endswith("~"):
            continue
        dst = DIST / src.relative_to(SOURCE)
        dst.parent.mkdir(parents=True, exist_ok=True)
        old = src.stat().st_size
        size_before += old

        if src.suffix == ".css":
            dst.write_text(css_minify(src.read_text(encoding="utf-8")), encoding="utf-8")
        elif src.suffix == ".js":
            dst.write_text(js_minify(src), encoding="utf-8")
        elif src.suffix == ".html":
            text = fill_machine_translated(fill_release(src.read_text(encoding="utf-8"), release))
            dst.write_text(html_minify(text), encoding="utf-8")
        else:
            shutil.copy2(src, dst)

        new = dst.stat().st_size
        size_after += new
        if src.suffix in (".css", ".js", ".html"):
            print(f"  {str(src.relative_to(SOURCE)):46} {old:7} -> {new:7}  ({100 - new * 100 // old:2}% smaller)")

    fingerprint()

    print(f"\n  total {size_before // 1024} KB -> {size_after // 1024} KB")
    print(f"  dist/ is ready: {sum(1 for _ in DIST.rglob('*') if _.is_file())} files")


if __name__ == "__main__":
    main()
