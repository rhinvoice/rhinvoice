# 0046 – Own units

- Status: accepted
- Date: 2026-11-14

## Context
Lines, articles and recurring plans took one of 21 fixed units (UN/ECE Recommendation 20
codes with labels in four languages). A farmer sells grain by the Doppelzentner of 100 kg
(#95), others need hectares, cartons or pallets; each such wish needed a release. The
e-invoice must stay valid whatever a user sets up: EN 16931 accepts only the codes of its
unit code list (BR-CL-23), UN/ECE Recommendation 20 with the Recommendation 21 codes
prefixed by X.

## Decision
- **Units belong to the company**, like the tax rates (ADR 0044): a label printed on
  documents, optional labels of its own per document language (an empty one prints the main
  label), a description for the user only, and the code for the
  e-invoice. Several units may share a code ("Std." and "Stunde" are both HUR); labels are
  unique whatever the case. At most 100 units.
- **The code list is data**: `domain/catalog/unit_codes.json` holds the 2162 codes the CEN
  validation artefacts 1.3.16 accept (rule BR-CL-23, as in the KoSIT XRechnung configuration
  3.0.2 of 2026-08-31) with their official English names from the KoSIT code lists
  `rec20_3` (Rec 20 revision 17) and `rec21_3` (Rec 21 revision 12); XSX, missing in the
  KoSIT list, is named after the OpenPEPPOL list. The domain refuses any other code.
- **A catalogue** brings the 21 units of before (labels unchanged) and common ones for
  small businesses, each with labels and names in four languages and a group: quarter,
  Doppelzentner (DTN), millimetre, centimetre, hectare, millilitre, hectolitre, megawatt
  hour, carton, box, pallet, bag, sack and bottle. *From catalogue …* lists what the company
  does not have yet and its hidden units, searchable and grouped; several are taken at once
  and go to the end of the list.
- **Hectare is H18** (square hectometre, exactly one hectare): HAR, which issue #95 and the
  first plan named, is deprecated since Rec 20 revision 17 and refused by the validators.
- **The order is the user's**: the settings list the units offered, sorted by drag and drop
  or keyboard; the selects of lines, articles and plans follow it. A new article without a
  unit takes the first one.
- **Removing** deletes a unit nothing uses (a line or an article saved meanwhile makes the
  database refuse the delete: the unit is hidden then); a unit that a line, an article or a recurring
  plan uses is hidden instead, one action for the user (the answer says which). Hidden units
  are not listed in the settings and not offered for new lines; a line, article or plan
  that has one keeps it and shows it marked. They come back through the catalogue. The last
  unit offered cannot be removed.
- **Issuing freezes the unit** on each line: its code and its label in the document's
  language (`unit_code`, `unit_label`), as the percentage of the rate. Renaming or removing a
  unit never changes an issued document; drafts show the current unit.
- **Migration 0029** gives every installation the 21 units of before, also one without a
  company (articles may be saved before it), like the default print layout of 0026. The
  first plan wanted the seeding on the first company save; the migration does it for every
  installation instead, so there is no second way to the same start. Every stored code
  points to its unit; a code that was none of the 21 (never written by Rhinvoice) gets a
  unit of its own labelled with the code. Issued lines keep their code and get the label
  they printed with. A downgrade stops once something uses a unit with another code.
- **CSV import** finds a unit offered by its label in any language, then by its code, then by
  the common words it knew before ("Stunden", "pauschal"); saved mappings keep working.

## Consequences
- `/api/reference/units` is gone; `/api/units` lists, changes, sorts and removes units,
  `/api/units/codes` lists the code list and `/api/units/presets` the catalogue. Lines,
  articles and plans send `unit_id`; lines answer with the unit's code and label. The API
  makes no compatibility promise before 1.0.
- The seeded units take the label of the company's document language as their main one;
  the other languages, German included, keep theirs as labels of their own where they
  differ, so every document prints what it did before. Migration 0029 does so for an
  existing company; an installation without a company gets German labels, which the first
  save of the company rewords (units the user changed stay as they are).
