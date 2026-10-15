# Changelog

All notable changes are listed here. The project follows [Semantic Versioning](https://semver.org/);
before 1.0, minor versions may contain breaking changes.

## [Unreleased]

### Added
- The programs for Windows and Mac open their window where it was closed, as large as it was
  (or maximized).

### Fixed
- Opening a page for the first time no longer blanks the whole window for a moment; the
  navigation stays. The programs for Windows and Mac load all pages shortly after the start.
- On Windows the start card and the program window open in the middle of the main screen,
  no longer near its top left.

## [0.7.3] – 2026-10-15

### Added
- *About Rhinvoice* has a button **Check for updates** that asks for a new version right away.
- The programs for Windows and Mac show a start card with the logo and the current step right
  after the double-click, until their window opens.

### Changed
- Starting the program for Windows and Mac a second time brings its open window to the front
  instead of opening another one.

### Fixed
- The notice about a new version appears within a minute of starting Rhinvoice. The page
  asked before the first check had run and then waited an hour.

## [0.7.2] – 2026-10-15

### Fixed
- Reminders, recurring invoices and the imports lead back to their list above the title, as
  the documents do.

## [0.7.1] – 2026-10-15

### Changed
- The setups for Windows and Mac are smaller: the Mac disk image is packed with LZMA, and the
  bundled Python leaves out what Rhinvoice never uses (its tests, Tk, IDLE, pip, debug symbols).
  Compiled Python files are no longer shipped; the program writes them into its cache on the
  first start, which therefore takes a few seconds longer once.
- The Windows setup always installs into `%LOCALAPPDATA%\Programs\Rhinvoice`, and uninstalling
  removes only the parts it installed there. An installation in another folder keeps it.

### Fixed
- Articles show and ask for the price in the company's currency first: euros for a company in
  Germany or Austria, also on a phone, where only that column fits.

## [0.7.0] – 2026-10-15

### Added
- **Rhinvoice without Docker (beta):** a setup for Windows 10/11 and a Mac app (macOS 12 or later,
  Apple silicon) with their own window and icon. They bring the database and everything else
  with them; PDFs are printed with Edge on Windows and with a bundled Chromium on the Mac. The
  data lies in the user's own folder and stays when the program is removed (ADR 0021). The
  setups are not signed yet: Windows and macOS ask once before they open them.
- Updates in the program: a quiet card at the foot of the sidebar and the *About* dialog say when
  a newer version exists. Without Docker one click installs it and restarts the program; a new
  version that does not start is taken back with the database from before it (ADR 0022). With
  Docker the card shows the commands. The check asks GitHub once a day for a signed `release.json`
  and can be switched off with `RHINVOICE_UPDATE_CHECK=false`.
- Backups without Docker: *Settings → Backup* chooses a folder (OneDrive, Dropbox, iCloud Drive,
  Google Drive, a network drive or a USB disk) and shows the recovery key once. The program then
  backs up as the backup container does: daily, after issuing or cancelling documents and on
  request, encrypted with restic, 7 daily, 4 weekly, 12 monthly and every yearly backup kept.
  `--restore` brings a backup back, also on a new computer (ADR 0023).
- A way back from a forgotten password: *Forgot password?* on the login page. On a server it
  names the new commands `rhinvoice user list` and `rhinvoice user reset-password`; in the
  installation without Docker it puts a one-time code into the data folder and opens the file.
  A new password also ends the account's other sessions and a lock after failed logins (ADR 0024).

### Fixed
- The overview shows the company's currency first. A company in Germany or Austria saw Swiss
  francs as soon as one document was in CHF, and before its first invoice.

## [0.6.2] – 2026-10-13

### Changed
- The original PDF of an invoice taken over from another program is fitted to the width, without
  the thumbnails of the browser's viewer (in Chromium browsers).

## [0.6.1] – 2026-10-13

### Fixed
- The backup container backs up at once after it created a new repository. Before, a repository
  made after earlier successful backups (another target, another access to the same one) stayed
  empty until the next daily backup, while the dashboard still showed the last successful one.
- A backup asked for while the repository is being created no longer fails with "config file
  already exists".

## [0.6.0] – 2026-10-13

### Added
- Writing off invoices that will not be paid: *More actions → Write off …* on an open invoice, with
  date, reason and note. The invoice stays as issued and nothing goes to the customer; it is no longer
  open, overdue or reminded, and it does not count as paid. A payment that comes in later is recorded
  as usual, and a write-off made by mistake can be taken back. Invoices taken over from another
  program can be written off too.
- The invoice list has the view *Written off* with the bad debts per year and currency: written off,
  paid later, loss, net and the tax contained. Each country names them and its tax rule in its own
  words (CH/LI Art. 41 MWSTG, DE § 17 UStG, AT § 16 UStG).

### Changed
- Backups to Google Drive are documented with an OAuth client ID of your own, because rclone retires
  its shared one during 2026: the steps in the Google Cloud console, moving an existing backup over,
  and a restore test in a second installation with every command.

## [0.5.6] – 2026-10-13

### Added
- Legal notice and privacy notice on rhinvoice.com, linked from the website, the docs and the
  login page of the public demo. Installations of your own do not show them.

## [0.5.5] – 2026-10-13

### Added
- The logo on the login page leads to rhinvoice.com, and the strip on every page of the public demo
  links it too.

## [0.5.4] – 2026-10-13

### Added
- The user documentation at [rhinvoice.com/docs](https://rhinvoice.com/docs/), in English and German:
  getting started, the rules of each country, invoices, moving over from another program, running
  it, questions, and these release notes. Features newer than the first public release are marked
  "Since version …".
- How more company countries come in: one country profile per country, with the Netherlands as the
  example (docs and landing page).

### Changed
- The interface links its guides (backup, installation, imports) to the docs in its own language
  instead of Markdown files on GitHub.

## [0.5.3] – 2026-10-13

### Fixed
- PDF footer: a long commercial register entry ran past the page edge. It now takes one line per
  comma-separated part ("Amtsgericht Kempten, HRB 12345"), and the label "Commercial register" is
  left out when the entry already names it ("Handelsregister des Kantons Zürich, …").

## [0.5.2] – 2026-10-13

### Fixed
- A session that ends while the app is open (expired, logged out elsewhere, or the hourly reset
  of the demo) now leads straight to the login, which says why. Before, pages showed "E-mail
  address or password is incorrect". The API answers such requests with the codes
  `session_expired` and `not_logged_in` instead of `authentication_failed`, which is now kept
  for wrong credentials.

## [0.5.1] – 2026-10-13

### Changed
- The public demo takes no uploads any more: importing customers, articles and invoices is
  switched off there, and the import page says how to try it on an own installation. Request
  bodies in the demo may have at most 2 MB.

## [0.5.0] – 2026-10-13

### Added
- Old invoices come over from the program used before, with their original PDFs: a list (CSV or
  Excel) and the folder of PDF files, single files or ZIP files. Each becomes a locked invoice with
  its number, date, customer and amounts, and its PDF as the invoice; reminders, corrections and
  copies of the same number are kept as attachments. Customers are found by number or name, unknown
  ones are created and archived. Imported invoices appear in lists (marked "Taken over"), search,
  the customer's history and the revenue, and open ones can be paid. The invoice sequence continues
  behind the imported numbers. See docs/import.md and ADR 0019.
- An imported invoice without PDF takes its PDF later on its page; further files become attachments.
- Uninstalling: how to remove the containers, data and images (docs/install.md), and the
  installation's name in `.env` (`COMPOSE_PROJECT_NAME`).

## [0.4.3] – 2026-10-12

### Added
- Customers keep the date they became customers: the import reads it from a column such as
  "Kunde seit", "Angelegt am" or "Created" (14.03.2019, 2019-03-14, also with a time), also when
  updating customers already imported. The customer page shows it next to the number.
- The Swiss VAT rates of 2011 to 2017 (8 / 2.5 / 3.8 %): article lists of older programs with
  "8" as their rate import, so do documents with a supply in those years.
- Article units such as "monatlich", "pro Monat", "jährlich" or "wöchentlich".

## [0.4.2] – 2026-10-12

### Changed
- A new logo: an invoice page with the Rhine and its four countries. It is the favicon and the
  home-screen icon on phones, and appears in the app, on rhinvoice.com and in the previews.

## [0.4.1] – 2026-10-12

### Changed
- The public demo takes imports of at most 200 KB and 200 rows, so it cannot be filled with junk;
  the import page says so. Installations of your own keep their limits (5 MB, 10'000 rows).

## [0.4.0] – 2026-10-12

### Added
- PDF output through Gotenberg with a live paper preview in the editor; issued documents keep
  their first PDF (SHA-256).
- Swiss QR-bill (QR reference or creditor reference) for Switzerland and Liechtenstein, EPC QR code
  (GiroCode) for Germany and Austria and for euro invoices from Switzerland and Liechtenstein to
  customers in the EEA; mandatory invoice details checked before issuing.
- Print templates (classic, modern, plain) with logo position and size, font, sender line,
  contact details, position numbers and all bank accounts in the footer; issued documents keep
  the layout of the day they were issued.
- Payment reminders and dunning letters in three levels with new deadlines, optional fees and
  texts per language; the PDF asks for the open amount plus the fee.
- Import of customers and articles from CSV, XLSX and XLS with column mapping, test run,
  duplicate handling and saved templates.
- Backups with restic in their own container: daily and after issuing, to S3, SFTP, a local
  folder or Dropbox, Google Drive and others through rclone; state on the dashboard and in the
  settings, restore with `make restore`.
- First-start wizard (country, company) and a setup checklist on the dashboard.
- A hint in the editor when an EU business customer lacks the VAT number for reverse charge.
- E-invoices: every issued invoice and cancellation embeds a ZUGFeRD / Factur-X invoice
  (EN 16931) in its PDF, for all countries and switchable in the print template; XRechnung 3.0
  download for German authorities; the invoice tells what is missing for either. Validated in CI
  with the KoSIT validator and Mustang.

- Demo data for a test installation: `rhinvoice demo` (or `make demo`) adds customers, articles and
  about 21 months of invoices, payments and quotes.

- The app refuses to start (and to migrate) on a database set up by a newer version, with a
  message that says what to do, instead of failing later on single actions.
- Recurring invoices: plans that write an invoice every month, quarter, half-year or year, as a
  draft, issued, or issued and sent by e-mail, with the covered period as service period. The web
  server writes them by itself (each period once, missed periods caught up); `rhinvoice recurring`
  does it at once. An issued invoice can be made recurring.
- Sending by e-mail: invoices, quotes, credit notes and reminders go out from Rhinvoice with their
  PDF (and the XRechnung on request) through the company's own mail server (SMTP), set up with a
  test mail under Settings → E-mail. Templates per kind and language with placeholders (new:
  `{firma}`); every mail is noted in the document's history. A refused mail shows the server's
  answer.
- Goods and services: articles and positions say what they supply. Goods to EU businesses with a
  VAT number are tax-free intra-Community supplies (e-invoice category K with the place of
  delivery), goods leaving the VAT area are tax-free export deliveries, also to private customers;
  each with its own notice, also on mixed invoices. The editor reminds of the proof of export or
  arrival.

- A language menu at the top right (also on the login page): Deutsch (Schweiz, Deutschland,
  Österreich) or English, kept per browser. Version, licence and links under "About Rhinvoice"
  in the account menu and at the foot of the sidebar.

- Country profiles: everything that differs between Switzerland, Liechtenstein, Germany and Austria
  (VAT law, rates, notices, mandatory details, payment codes, terms) lives in one profile per
  country, which the interface reads from the API. Adding a country is described in
  `docs/adding-a-country.md`.

- Demo mode (`RHINVOICE_DEMO`) for a public demo: the data is reset every hour, the login page
  logs in with one click, what would lock visitors out or send mail is refused, and logins and
  changes are rate-limited. `deploy/demo/` runs Switzerland, Germany and Austria side by side
  behind Caddy, isolated from the internet.
- At most two password checks (argon2, 64 MiB each) run at the same time; a burst of logins waits
  instead of exhausting the memory.

### Fixed
- The overview kept an empty gap at the top once the setup checklist was hidden.
- The import read a rate of 13 % as Austria's 10 % rate; rates are now read from the company's
  country (13 % is Austria's own rate, 16 % and 5 % German ones of 2020). A rate the country never
  had (e.g. 19 % for a Swiss company) is reported instead of being taken as the standard rate.
- German documents print "Ihre USt-IdNr." instead of "Ihre UID"; the tax name is "USt." everywhere.
- The first-start wizard shows the VAT rates of the day instead of fixed text.
- The 5-centime rounding and the QR-IBAN are only offered where they apply (Switzerland,
  Liechtenstein).
- Paying or cancelling invoices issued by an earlier version failed with a conflict.
- Cancellations without VAT wrote a tax total of "-0.00" into their e-invoice, which Mustang
  rejects (BR-CO-14).
- The article list's button said "Neuer Kunde".

### Changed
- Rhinvoice is licensed under the GNU Affero General Public License v3.0 or later; contributions
  come under a contributor licence agreement. The project lives at `github.com/rhinvoice/rhinvoice`
  and its images at `ghcr.io/rhinvoice/rhinvoice`.
- The overview is a cockpit: revenue this year against last year with a trend line, open and
  overdue amounts, open quotes with the acceptance rate, open invoices by age, the longest overdue
  ones, the best customers, the payments to expect per week and the latest activity, per currency.
- The architecture decision records are written in English.
- All PDFs are PDF/A-3b, made from Chromium's output without changing pages, fonts or tags.

## [0.3.0] – 2026-10-11

First preview release.

### Added
- Quotes, invoices and cancellation invoices: create, edit, issue, mark as paid (also partially),
  remove payments, cancel, duplicate, turn a quote into an invoice.
- Calculation with line and document discounts, net or gross prices, VAT per rate and Swiss
  5-cent rounding; dated VAT rates for Switzerland, Liechtenstein, Germany and Austria; automatic
  tax treatment (domestic, reverse charge, export, small business, exempt) with a logged manual
  override.
- Numbers are assigned when issuing, without gaps; issued documents are immutable (also enforced
  by the database), corrections only by cancellation.
- Invoice and quote lists with views (open, overdue, paid …) and full-text search; dashboard with
  open, overdue and paid amounts, monthly revenue and recent activity.
- Customers and articles with search, archive and document history; company, logo, bank accounts
  (IBAN/QR-IBAN) and number sequences in the settings.
- Login with optional two-factor authentication, keyboard shortcuts, command palette, light and
  dark mode, German (CH/DE/AT) and English.

### Not yet included
- PDF output, Swiss QR-bill and EPC-QR, e-invoices, import, backup, onboarding assistant.
