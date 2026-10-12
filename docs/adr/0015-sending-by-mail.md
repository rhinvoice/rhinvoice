# 0015 – Sending documents by mail

- Status: accepted
- Date: 2026-10-12

## Context
Invoices, quotes and reminders went to customers as downloaded PDFs attached by hand. Sending them
from Rhinvoice saves the step, attaches the right (archived) file every time and records the mail in
the document's history.

## Decision
- **SMTP of the company's own provider**, set up once in the settings (server, port, STARTTLS / TLS
  / none, login, sender, reply-to, optional blind copy to the sender). No mail service of our own,
  no extra container. The standard library's `smtplib` sends, certificates are checked against the
  system's trust store.
- **The password lives in the database**, like all other data of the installation (backups are
  encrypted with restic). It never leaves the server again: the API only says whether one is set,
  an empty field keeps it. Encrypting it with a key from the environment would protect nothing the
  database alone does not already reveal, and installations would need a new secret to update.
- **Sending is immediate**, in the request, with a 30-second timeout: the person sees right away
  whether the server took the mail and, if not, what it answered (wrong password, refused sender,
  TLS mismatch …). No queue that could fail silently. A mail refused for some recipients counts as
  failed for those and says so.
- **Only issued documents are sent**, with their archived PDF (the e-invoice inside); invoices may
  attach the XRechnung when it is complete. Reminders carry their letter. Each mail is an event in
  the history of the document (the invoice for reminders) with the recipients.
- **Templates per kind and language** (invoice, quote, credit note, three reminder levels; German and
  English), built in and replaceable in the settings, with the placeholders of the document texts plus
  `{firma}`. The greeting follows the company's country (Swiss German writes "Grüsse").
- The person checks recipients, subject and text before each mail; the customer's address is
  prefilled, up to five recipients.

## Consequences
- No sending of mails in the background yet (recurring invoices send in their own run, ADR 0016).
- No tracking of opened mails and no bounces: the history says that the server took the mail.
- Installations behind firewalls need outgoing SMTP allowed.
