# rhinvoice.com

The landing page of Rhinvoice, in English (`/`) and German (`/de/`), served by GitHub Pages.

```
website/
  site/      the source: hand-written HTML, one stylesheet, one small script — edit here
  build.py   minifies site/ into dist/ and puts content hashes into asset names
  tools/     makes the images (social previews, app icons, screenshots)
  dist/      the built site (not versioned)
```

## Build and look at it

```bash
npm i -g terser                       # once
python3 website/build.py
python3 -m http.server 8765 --bind 127.0.0.1 --directory website/dist
```

Then open <http://127.0.0.1:8765/>. Pushing changes under `website/` to `main` builds and
publishes the site (`.github/workflows/pages.yml`).

## Images

The screenshots come from the public demo (`deploy/demo`) and live in `docs/screenshots`, where
the README uses them too. After changing them, or the logo, render the site's images again:

```bash
cd frontend && node ../website/tools/make-images.mjs   # needs cwebp and avifenc
```

## What the pages carry, and why

- **For search engines:** title and description per language, canonical URLs, `hreflang` between
  the two languages, Open Graph and Twitter cards with a 1200×630 preview, `sitemap.xml` with
  the language pairs, JSON-LD (`SoftwareApplication`, `SoftwareSourceCode`, `WebSite`,
  `WebPage`; publisher is the webberz organisation `https://www.webberz.ch/#firma`, the same
  node webberz.ch uses).
- **For answer engines (LLMs):** `llms.txt` with the facts and what Rhinvoice is not;
  `robots.txt` welcomes the AI crawlers by name. Everything is in the HTML, nothing is loaded
  by script.
- **Security:** a strict Content-Security-Policy as a meta tag (GitHub Pages sets no headers):
  only the site's own files, so no inline scripts or styles and no third-party requests;
  `/.well-known/security.txt` points to the private vulnerability report.
- **Speed:** self-hosted variable fonts (the app's Inter, the invoices' Source Serif 4) split
  into latin and latin-ext; screenshots as AVIF and WebP with PNG fallback and fixed sizes;
  minified files with hashed names.

Keep the facts identical in the pages, `llms.txt`, the JSON-LD and the repository README.

## GitHub Pages settings

- Settings → Pages → Source: **GitHub Actions**; custom domain **rhinvoice.com** (the `CNAME`
  file), **Enforce HTTPS** on. `www.rhinvoice.com` redirects to it.
- DNS at the registrar: `A` records for `rhinvoice.com` to 185.199.108.153, 185.199.109.153,
  185.199.110.153 and 185.199.111.153 (and the `AAAA` ones GitHub lists), `CNAME` for `www` to
  `rhinvoice.github.io`.
- Then register the domain in Google Search Console and Bing Webmaster Tools and submit
  `https://rhinvoice.com/sitemap.xml` (Bing also feeds ChatGPT search and Copilot).
