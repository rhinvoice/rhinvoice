# 0043 – Several print templates

- Status: accepted
- Date: 2026-11-11

## Context
An installation had one print layout for all documents. A customer or a bookkeeper who wants
another look, or other details top right (ADR 0042), changed every invoice (#48). Kadir's rule:
no update and no wish of one customer changes how the other invoices look.

## Decision
- **Named layouts** (`NamedLayout`: id, name, layout, is_default) replace the single one, at
  most 20, names unique regardless of case. Exactly one is the default: a partial unique index
  allows one at most, and the default cannot be deleted. Migration 0026 turns the layout saved
  so far into the default named "Standard"; without one, the program's defaults, so documents
  look as before.
- **Which layout a document takes** (`layout_for`): the one chosen for the document, else its
  customer's, else the default. A choice whose layout was deleted falls through to the next one;
  the foreign keys of customers and documents are set to null on deletion. Recurring plans keep
  their choice in their template and fall back the same way when they run. A choice that names
  no layout is refused when it is saved (`unknown print layout`).
- **Issuing freezes the layout** in the snapshot, as before; issued documents never change.
- **Where it is chosen** (variants chosen by Kadir, 4A and 5B):
  - Settings: a choice of the layout at the top of the print layout page with *New template*
    (a copy of the one shown), *Rename*, *Sample PDF* and a menu to make it the default or
    delete it. While the shown layout has unsaved changes, another one cannot be chosen.
  - Customer: *Print template* among the defaults, next to language and currency.
  - Editor: in the page header, next to the title; the card *Dates* shows the fields of the
    layout the document takes, values entered for others stay with the document.
  - All three appear only with more than one layout.
- **Sample PDF**: the latest invoice (or the sample one) with a layout as it is on screen,
  marked "Sample" on every page like the "Draft" mark, without an e-invoice.
- **One logo** for the company; each layout sets its place and size. A logo per layout would
  wait for a real need.

## Consequences
- A bookkeeper's or an authority's wish gets its own layout without touching the others.
- `/api/print-layout` became `/api/print-layouts` with ids; the web client is its only user.
- Tests and the demo start with the default layout, as every installation does after 0026.
