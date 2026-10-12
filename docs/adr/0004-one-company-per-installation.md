# 0004 – One company per installation, multi-tenancy prepared

- Status: accepted
- Date: 2026-10-10

## Context
Rhinvoice targets sole proprietors and small companies. CLAUDE.md requires "one company per installation,
multi-tenancy prepared".

## Decision
- The `company` table allows exactly one row (check constraint on a singleton column with a unique index).
  Logo and number sequences are installation-wide as well.
- All entities have UUIDs as primary keys. Later multi-tenancy adds a `tenant_id` column
  via migration and a filter in the repositories. Data from several installations can be merged without
  key conflicts.
- Addresses are structured (street, house number, address addition, postal code, town, country) with the field lengths of the Swiss QR-Bill
  (Implementation Guidelines v2.3, only structured addresses from November 2025). This way they can be printed on the
  payment part without conversion.
- Names are sorted with the ICU collation `und-x-icu` (Ä with A, ü with u), independent of the
  database's default collation. Search is accent- and case-insensitive (`unaccent` + `ILIKE`).

## Consequences
- No tenant switching in the UI. Anyone running several companies operates several installations for now.
- The address addition (c/o, P.O. box, department) has no field of its own in the QR-Bill's structured address format.
  It appears in the document's address block, but not in the QR payment part.
