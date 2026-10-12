# 0007 – Print template, PDF via Gotenberg and archiving

- Status: accepted
- Date: 2026-10-11

## Context
CLAUDE.md §9 requires a Jinja2 template, PDFs via Gotenberg and immutable PDFs of issued
documents (SHA-256). The editor should show the document live as paper (choice of editor variant A);
issued documents open as a document.

## Decision
- **One template for everything**: `infrastructure/rendering/templates/document.html.j2` + `document.css` (A4,
  address field according to DIN 5008 form B, also fits C5 window envelopes with the window on the left in Switzerland). The live preview
  in the editor, the document view and the PDF use the same HTML page. All decisions (texts,
  number formats 1’234.50 / 1.234,50, notices, placeholders) are made in Python; the template only arranges.
  A theme folder (`RHINVOICE_THEME_DIR`) can replace the files.
- **Preview in the browser**: the frontend loads the page as text and shows it in an `iframe srcdoc`
  without scripts (`sandbox="allow-same-origin"`), scaled to the available width. A click on a
  line row (`data-index`) opens it in the editor. `frame-ancestors 'none'` remains in place for real pages.
- **Font**: Inter in static weights (400/500/600/700, latin + latin-ext) as data URI. Chromium embeds the variable
  font as a Type 3 font, which does not survive a PDF/A conversion.
- **PDF**: Gotenberg 8 (Chromium), tagged PDF (`generateTaggedPdf`) with metadata (title, company).
  Gotenberg runs hardened: no port exposed to the outside, JavaScript off, all network access except the
  file passed in blocked, read-only.
- **PDF/A-3b** is implemented together with the e-invoice (phase 7, ZUGFeRD/Factur-X). Gotenberg's PDF/A conversion
  runs via LibreOffice and replaces the font in the process (tested with 8.37.0); the result would
  no longer match the preview.
- **Archiving**: right after issuing or cancelling, the PDF is generated and stored
  (`document_pdfs`); its SHA-256 is stored on the document (`pdf_sha256`). If Gotenberg is unreachable at that point,
  issuing is still possible and the PDF is archived on first retrieval. Database triggers prevent
  modification, deletion and TRUNCATE and check that the content matches the hash. Later retrievals return exactly this
  file; only verified PDFs (`application/pdf`, `%PDF-`) are archived. Drafts are generated anew every time.
  The HTML view of issued documents is rendered with the current logo/theme; the PDF is authoritative.
- **Multiple pages**: page margins via `@page`, the table header repeats, the footer is printed on every page via the
  margin boxes `@bottom-left/center/right` (fixed elements shift from page to page in Chromium).
- **Printing** in the browser prints the HTML page (identical to the PDF) via an invisible window.

## Consequences
- Without Gotenberg (`RHINVOICE_GOTENBERG_URL` empty) everything works except PDF (response 503 `unavailable`).
- A changed template or a new logo does not change PDFs that are already archived.
