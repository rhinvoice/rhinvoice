# 0040 – Attachments of own documents

- Status: accepted
- Date: 2026-10-30

## Context
A pass-through item (ADR 0039) is proven by the third party's invoice, which the customer
needs with the invoice. Until now only invoices taken over from another program had further
files (ADR 0019); documents written here had none.

## Decision
- **Drafts take PDFs.** The existing upload (`POST /api/documents/{id}/files`) adds an
  attachment to a draft of any type; `DELETE /api/documents/{id}/attachments/{attachment_id}`
  removes one while the document is a draft. The same checks as for imported invoices: PDF
  magic bytes (`%PDF-`), at most 20 MB per file (the body limit of the path stays 21 MB), at
  most ten attachments per draft and at most 20 MB of them together (`attachments_too_large`),
  the limit of one mail (`MAX_ATTACHED_BYTES`): an issued document can always be sent. Names
  lose folders, control characters and the characters `/\:*?"<>|` as well as Unicode format
  characters (bidi overrides, zero widths) and line separators, are NFC-normalised and end in
  `.pdf` (`upload_name`). A name the document's files carry already, in any case, gets " (2)",
  " (3)" before `.pdf` (`unique_name`). Downloads revalidate (`Cache-Control: private,
  no-cache` with the hash as ETag), since a draft's file may go. The public demo refuses
  uploads and removals, as before.
- **Frozen when issued.** From issuing on the files are only ever added to imported invoices,
  never to issued documents written here, and never changed or removed (GoBD, OR 958f). The
  database trigger enforces it: it reads the document `FOR SHARE`, so an upload and issuing
  at the same moment wait for each other; it refuses removals unless the document is a draft
  and inserts into issued documents of this program. Deleting a draft deletes its files in the
  same transaction; nothing is left behind. Copies (duplicate, quote to invoice, cancellation)
  do not take the files along.
- **History.** Adding and removing note "file_added" / "file_removed" with the file name.
- **Editor.** A folded section *Anhänge* below *Weitere Angaben* on a saved draft lists the
  files (open, remove) and adds one or more PDFs. A new document attaches after its first save
  (the editor then continues on the draft's page); recurring plans have none. Issued documents
  show their files in a card *Anhänge* when they have some.
- **Mail.** Sending a document attaches its PDF, then the XRechnung if chosen, then the files
  in the order of their names, at most 20 MB of them together: mail servers often refuse more.
  The upload keeps drafts within it; the mail checks it again as a safeguard
  (`mail_attachments_too_large`). The mail dialog lists them. An imported invoice's files stay
  in the archive.
- **Export (ADR 0038).** The ZIP adds each own document's files right after its PDF, named
  after the number and the file's own name: `R20260042_Handelsregister.pdf`. The number sorts
  them next to their invoice; the name says what they are. Names are made unique like the
  PDFs' (" (2)") and shortened before `.pdf` to at most 200 characters and 255 bytes in UTF-8,
  for file systems and the folder they are unpacked into. The column *Datei* still names the
  document's PDF only. Imported invoices' further files are not exported, as before.
- **The document PDF stays as it is.** Attachments are separate files, not merged into the
  archived PDF (its hash and PDF/A-3 with the e-invoice are unchanged).

## Consequences
- The proof of a pass-through item travels with the invoice by mail and to the bookkeeper.
- Large attachments make large mails: a draft takes no more than 20 MB of them together, so
  every issued document can be sent; a scan above that has to be made smaller first.
