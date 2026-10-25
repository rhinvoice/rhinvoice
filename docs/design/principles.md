# Rhinvoice – Design principles and design system

As of: 2026-10-09. Basis for all frontend work (React, Tailwind CSS v4, shadcn/ui, Radix, Motion, Lucide).
Binding for reviews: a UI review checks against this document.

---

## 1. Research – findings per source

### 1.1 Linear
- Redesign 2025/26 along two principles: *"Don't compete for attention you haven't earned"* (navigation and chrome step back, content dominates) and *"Structure should be felt, not seen"* (softer borders, fewer dividers, fewer icons).
- Sidebar dimmed, inactive entries in a muted text color, compact tabs; color system in LCH with controls for hue/chroma/lightness, warmer greys instead of cold blue.
- Keyboard first: ⌘K palette, mnemonic single-key shortcuts (e.g. `S` status), shortcut hints in tooltips, context menus and palette results, so users learn them along the way.
- Sources: [Behind the latest design refresh](https://linear.app/now/behind-the-latest-design-refresh), [How we redesigned the Linear UI](https://linear.app/blog/how-we-redesigned-the-linear-ui)

### 1.2 Stripe Dashboard
- Compact tables that can be sorted and filtered. Filters as chips above the table (one chip per attribute, e.g. status); status comes first and is visually dominant (badge with color **and** text).
- Amounts right-aligned with currency; detail view as its own page with a timeline (event history).
- Stripe limits custom styling on purpose, to guarantee contrast and consistency – for us: a few checked tokens instead of free colors.
- Sources: [Stripe Apps Design](https://docs.stripe.com/stripe-apps/design), [UI components](https://docs.stripe.com/stripe-apps/components), [Filter controls](https://docs.stripe.com/stripe-apps/patterns/filter-controls)

### 1.3 Vercel (Geist)
- High-contrast color system with scaled greys, its own typeface (Geist Sans/Mono), "Materials" as presets for radius, fill, stroke and shadow, fixed grid.
- For us: adopt the materials idea (surface = color + border + radius + shadow as a fixed combination: `surface`, `popover`, `dialog`).
- Source: [Geist Introduction](https://vercel.com/geist/introduction)

### 1.4 Attio
- Data-dense table views (grid/list/kanban) with saved views, column selection, filtering, sorting and inline editing; multi-select with Shift-click, copy/paste of cells.
- For us: saved views ("Überfällig" (overdue), "Entwürfe" (drafts)) and inline editing of invoice positions.
- Sources: [Create and manage table views](https://attio.com/help/reference/managing-your-data/views/create-and-manage-table-views)

### 1.5 shadcn/ui and Radix
- shadcn/ui (Tailwind v4): semantic token pairs as CSS variables in **OKLCH** (`--background`/`--foreground`, `--card`, `--popover`, `--primary`, `--secondary`, `--muted`, `--accent`, `--destructive`, `--border`, `--input`, `--ring`, `--chart-1…5`, `--sidebar-*`), available in Tailwind via `@theme inline` as `bg-background`, `text-foreground` etc.; dark mode via the `.dark` class.
- Note: in shadcn, `--accent` is a **subtle hover surface**, not the brand color. Our configurable brand color is therefore called `--accent-hue` and feeds `--primary`.
- The shadcn defaults (`--border`/`--input` ≈ `oklch(0.922 0 0)`) do **not** reach 3:1 for input field borders (WCAG 1.4.11). We set `--input` darker (see tokens).
- Components: `Command` (cmdk) for ⌘K, `Sonner` for toasts (`toast(msg, { action: { label, onClick } })`, `toast.promise`), `Dialog`/`AlertDialog`, `Table` + TanStack Table, `Sidebar`, `Form` with label/description/message.
- Radix: components follow the WAI-ARIA Authoring Practices and provide keyboard navigation and focus management (focus trap in dialogs, focus return, `AlertDialog` focuses "Abbrechen" (cancel)). **Labels remain our responsibility.**
- Sources: [shadcn Theming](https://ui.shadcn.com/docs/theming), [shadcn Tailwind v4](https://ui.shadcn.com/docs/tailwind-v4), [Sonner](https://ui.shadcn.com/docs/components/sonner), [Sonner API](https://sonner.emilkowal.ski/toast), [Radix Accessibility](https://www.radix-ui.com/primitives/docs/overview/accessibility)

### 1.6 WCAG 2.2 AA
New in 2.2 (relevant for AA): 2.4.11 Focus Not Obscured (Minimum), 2.5.7 Dragging Movements, 2.5.8 Target Size (Minimum, 24×24 CSS px or enough spacing), 3.2.6 Consistent Help (A), 3.3.7 Redundant Entry (A), 3.3.8 Accessible Authentication (Minimum). 4.1.1 Parsing is dropped.
- 2.4.11: a typical failure is a sticky header/footer/toast that hides the focused element; the fix is `scroll-padding`.
- 2.5.8: exceptions for inline links in running text, an equivalent larger alternative, and controls styled by the browser.
- Sources: [What's new in WCAG 2.2](https://www.w3.org/WAI/standards-guidelines/wcag/new-in-22/), [Understanding 2.5.8](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html), [Understanding 2.4.11](https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum.html)

### 1.7 European Accessibility Act (EAA)
- Directive (EU) 2019/882, applicable since **28 June 2025** (DE: BFSG, AT: BaFG). The technical basis is the harmonised standard **EN 301 549** (currently refers to WCAG 2.1 AA; the next edition moves to WCAG 2.2). Mandatory mainly for B2C e-commerce and consumer services, including an accessibility statement; micro-enterprises (< 10 employees, ≤ EUR 2 million) are exempt for services.
- Rhinvoice is self-hosted B2B software and hardly falls under it directly. We still meet **WCAG 2.2 AA** (a superset of 2.1 AA), so that users and public contracting authorities (AT/DE) can use Rhinvoice without reservation.
- Sources: [e-include: EAA – who it applies to](https://e-include.eu/web-accessibility/european-accessibility-act/), [Clym: EAA / EN 301 549](https://regulations.clym.io/european-accessibility-act-eea-en-301549), [EAA/BFSG overview](https://koksal.av.tr/en/legislation/eu-accessibility-act-eaa-germanys-bfsg/)

### 1.8 Material Design 3 and Apple HIG
- M3 text fields: label always visible (no placeholder as label), help text below the field, the error message **replaces** the help text until corrected and explains how to fix the error; mark required fields.
- M3/M2 data tables: numbers right-aligned, text left-aligned, header row with sort arrow, row heights in density levels, selection by checkbox in the first column.
- Apple HIG lists & tables: prefer tables for scannable text, group rows, clear select/delete/sort interactions; on mobile lists instead of wide tables; touch targets 44×44 pt.
- Sources: [M3 Text fields](https://m3.material.io/components/text-fields/guidelines), [Material Web Text field](https://material-web.dev/components/text-field), [M2 Data tables](https://m2.material.io/components/data-tables), [Apple HIG Lists and tables](https://developer.apple.com/design/human-interface-guidelines/lists-and-tables), [Apple HIG Layout](https://developer.apple.com/design/human-interface-guidelines/layout)

### 1.9 Number and date formats (DACH)
Checked with Node 22 (ICU 77.1, CLDR 47):

| Locale | Number `1234.5` | Amount | Long date | Percent |
|---|---|---|---|---|
| de-CH / de-LI | `1’234.5` | `CHF 1’234’567.50` | `5. Januar 2026` | `8.1%` |
| de-DE | `1.234,5` | `1.234.567,50 €` | `5. Januar 2026` | `8,1 %` |
| de-AT | `1 234,5` (NBSP!) | `€ 1.234.567,50` | `5. Jänner 2026` | `8,1 %` |
| en | `1,234.5` | `€1,234.50` | `5 January 2026` (en-CH) | `8.1%` |

- de-CH groups with **U+2019** (’), not with the ASCII apostrophe. Tests must expect the real Intl output (or normalise it), never a hard-coded `'`.
- According to CLDR, de-AT groups plain numbers with a no-break space and currency amounts with a dot. So amounts are **always** formatted with `style: "currency"`, never by gluing a number and a currency sign together.
- Sources: [CLDR de_CH (ICU)](https://opensource.apple.com/source/ICU/ICU-491.11.1/icuSources/data/locales/de_CH.txt.auto.html), [JDK-8211262 (de-CH Separator)](https://bugs.openjdk.org/browse/JDK-8211262), [MDN Intl.NumberFormat](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Intl/NumberFormat)

---

## 2. Guiding principles for Rhinvoice

1. **Calm and dense:** content (amounts, status, customers) dominates, chrome steps back. No element claims more attention than it deserves.
2. **Status first:** in every list, the document status is the first visual information (badge with icon + text + color).
3. **Keyboard first, mouse and touch equal:** every core action has a shortcut and a visible button.
4. **Trust:** money is serious. Amounts always with tabular figures, right-aligned, with currency; the immutability of issued documents is visible (lock icon, "Ausgestellt am …" (issued on …)).
5. **Forgive rather than confirm:** run reversible actions at once (optimistically) and offer an undo toast; confirm only irreversible actions (issue, cancel, delete) with an `AlertDialog`.
6. **Few checked tokens:** no ad-hoc colors in code. All colors come from the tokens below, whose contrasts are calculated.

---

## 3. Design tokens

### 3.1 Colors (OKLCH)

A single variable `--accent-hue` (default `250`, a calm steel blue) sets the primary color, the focus ring and the slight tint of the neutrals. It can be changed per installation in the settings (company color → hue). Lightness and chroma stay fixed, so the contrasts hold for **every** hue (see 3.2, hue sweep). Status and semantic colors have fixed hues and do not depend on `--accent-hue`.

```css
:root {
  --accent-hue: 250;            /* configurable per installation, 0–360 */
  --neutral-hue: var(--accent-hue);

  --background: oklch(0.990 0.003 var(--neutral-hue));
  --foreground: oklch(0.205 0.015 var(--neutral-hue));
  --card: oklch(1 0 0);
  --card-foreground: var(--foreground);
  --popover: oklch(1 0 0);
  --popover-foreground: var(--foreground);
  --muted: oklch(0.960 0.006 var(--neutral-hue));
  --muted-foreground: oklch(0.500 0.018 var(--neutral-hue));
  --secondary: var(--muted);
  --secondary-foreground: var(--foreground);
  --accent: oklch(0.955 0.020 var(--accent-hue));          /* shadcn: subtle hover/selected surface */
  --accent-foreground: oklch(0.400 0.110 var(--accent-hue));
  --border: oklch(0.905 0.008 var(--neutral-hue));          /* decorative dividers only */
  --input: oklch(0.640 0.015 var(--neutral-hue));           /* form control outlines, >= 3:1 */
  --ring: oklch(0.560 0.130 var(--accent-hue));
  --primary: oklch(0.500 0.120 var(--accent-hue));
  --primary-foreground: oklch(0.985 0.003 var(--accent-hue));
  --destructive: oklch(0.530 0.190 27);
  --destructive-foreground: oklch(0.985 0 0);
  --success: oklch(0.500 0.120 150);
  --success-foreground: oklch(0.985 0 0);
  --warning: oklch(0.555 0.125 60);
  --warning-foreground: oklch(1 0 0);
  --info: oklch(0.520 0.110 235);
  --info-foreground: oklch(0.985 0 0);

  /* Document status: text (fg) on tinted badge background (bg) */
  --status-draft-fg: oklch(0.45 0.015 var(--neutral-hue));  --status-draft-bg: oklch(0.955 0.005 var(--neutral-hue));
  --status-sent-fg: oklch(0.45 0.090 235);                  --status-sent-bg: oklch(0.955 0.020 235);
  --status-issued-fg: oklch(0.45 0.120 250);                --status-issued-bg: oklch(0.955 0.020 250);
  --status-partially-paid-fg: oklch(0.47 0.095 70);         --status-partially-paid-bg: oklch(0.960 0.028 70);
  --status-paid-fg: oklch(0.45 0.120 150);                  --status-paid-bg: oklch(0.960 0.035 150);
  --status-accepted-fg: oklch(0.45 0.090 165);              --status-accepted-bg: oklch(0.960 0.030 165);
  --status-overdue-fg: oklch(0.48 0.170 27);                --status-overdue-bg: oklch(0.955 0.020 27);
  --status-declined-fg: oklch(0.47 0.150 10);               --status-declined-bg: oklch(0.955 0.020 10);
  --status-expired-fg: oklch(0.47 0.100 55);                --status-expired-bg: oklch(0.960 0.022 55);
  --status-cancelled-fg: oklch(0.45 0.015 var(--neutral-hue)); --status-cancelled-bg: oklch(0.955 0.005 var(--neutral-hue));
}

.dark {
  --background: oklch(0.170 0.008 var(--neutral-hue));
  --foreground: oklch(0.955 0.004 var(--neutral-hue));
  --card: oklch(0.205 0.010 var(--neutral-hue));
  --popover: oklch(0.225 0.010 var(--neutral-hue));
  --muted: oklch(0.250 0.010 var(--neutral-hue));
  --muted-foreground: oklch(0.720 0.015 var(--neutral-hue));
  --accent: oklch(0.270 0.040 var(--accent-hue));
  --accent-foreground: oklch(0.850 0.070 var(--accent-hue));
  --border: oklch(0.300 0.010 var(--neutral-hue));
  --input: oklch(0.520 0.015 var(--neutral-hue));
  --ring: oklch(0.680 0.120 var(--accent-hue));
  --primary: oklch(0.720 0.110 var(--accent-hue));
  --primary-foreground: oklch(0.170 0.020 var(--accent-hue));
  --destructive: oklch(0.650 0.190 25);
  --destructive-foreground: oklch(0.170 0.008 var(--neutral-hue));
  --success: oklch(0.720 0.140 150);
  --success-foreground: oklch(0.170 0.008 var(--neutral-hue));
  --warning: oklch(0.800 0.140 80);
  --warning-foreground: oklch(0.220 0.040 60);
  --info: oklch(0.720 0.110 235);
  --info-foreground: oklch(0.170 0.008 var(--neutral-hue));

  --status-draft-fg: oklch(0.80 0.012 var(--neutral-hue)); --status-draft-bg: oklch(0.26 0.010 var(--neutral-hue));
  --status-sent-fg: oklch(0.82 0.090 235);                 --status-sent-bg: oklch(0.28 0.050 235);
  --status-issued-fg: oklch(0.82 0.090 250);               --status-issued-bg: oklch(0.28 0.050 250);
  --status-partially-paid-fg: oklch(0.84 0.110 70);        --status-partially-paid-bg: oklch(0.29 0.050 70);
  --status-paid-fg: oklch(0.82 0.130 150);                 --status-paid-bg: oklch(0.28 0.050 150);
  --status-accepted-fg: oklch(0.82 0.110 165);             --status-accepted-bg: oklch(0.28 0.045 165);
  --status-overdue-fg: oklch(0.80 0.110 27);               --status-overdue-bg: oklch(0.29 0.070 27);
  --status-declined-fg: oklch(0.80 0.100 10);              --status-declined-bg: oklch(0.28 0.060 10);
  --status-expired-fg: oklch(0.82 0.090 55);               --status-expired-bg: oklch(0.28 0.045 55);
  --status-cancelled-fg: oklch(0.78 0.012 var(--neutral-hue)); --status-cancelled-bg: oklch(0.26 0.010 var(--neutral-hue));
}
```

Theme switching: three states `light | dark | system`, stored in `localStorage`; with `system`, the `.dark` class follows `prefers-color-scheme` (listener on `matchMedia`). An inline script in `<head>` sets the class before the first paint (no flicker). Set `color-scheme: light dark` on `:root`, so native controls and scrollbars match.

### 3.2 Contrast proof (calculated)

Calculated with OKLCH → linear sRGB → WCAG 2 luminance, all values inside the sRGB gamut (script reproducible, see section 8). Requirement: text ≥ 4.5:1 (1.4.3), UI components and focus ≥ 3:1 (1.4.11).

| Pair | Light | Dark | Target |
|---|---|---|---|
| foreground / background | 17.40 | 16.77 | 4.5 |
| foreground / card | 17.90 | 15.71 | 4.5 |
| foreground / popover | 17.90 | 15.00 | 4.5 |
| foreground / muted | 15.94 | 14.03 | 4.5 |
| muted-foreground / background | 5.82 | 7.72 | 4.5 |
| muted-foreground / card | 5.99 | 7.23 | 4.5 |
| muted-foreground / muted | 5.33 | 6.45 | 4.5 |
| primary-foreground / primary | 5.74 | 7.75 | 4.5 |
| primary (as text/link) / background | 5.82 | 7.75 | 4.5 |
| primary / card | 5.99 | 7.26 | 4.5 |
| ring / background | 4.51 | 6.67 | 3.0 |
| ring / card | 4.64 | 6.25 | 3.0 |
| input (field border) / background | 3.26 | 3.48 | 3.0 |
| input / card | 3.36 | 3.26 | 3.0 |
| destructive-foreground / destructive | 5.57 | 5.40 | 4.5 |
| destructive (text) / background | 5.66 | 5.40 | 4.5 |
| success (text) / background | 5.52 | 8.15 | 4.5 |
| info (text) / background | 5.25 | 7.86 | 4.5 |
| warning-foreground / warning | 4.94 | 9.20 | 4.5 |
| warning (text) / background | 4.80 | 10.09 | 4.5 |
| accent-foreground / accent | 8.10 | 9.56 | 4.5 |
| border / background (decorative) | 1.29 | 1.40 | – |

Status badges (text on badge surface / text on page / text on card):

| Status | Light | Dark |
|---|---|---|
| draft | 6.52 / 7.22 / 7.43 | 8.32 / 10.24 / 9.59 |
| sent | 6.44 / 7.11 / 7.31 | 8.43 / 11.12 / 10.42 |
| issued | 6.54 / 7.23 / 7.44 | 8.39 / 11.01 / 10.31 |
| partially_paid | 6.19 / 6.78 / 6.97 | 8.57 / 11.51 / 10.78 |
| paid | 6.34 / 6.84 / 7.04 | 8.61 / 11.49 / 10.76 |
| accepted | 6.39 / 6.89 / 7.09 | 8.59 / 11.46 / 10.73 |
| overdue | 6.22 / 6.94 / 7.14 | 7.44 / 9.81 / 9.18 |
| declined | 6.46 / 7.21 / 7.42 | 7.67 / 9.80 / 9.18 |
| expired | 6.26 / 6.87 / 7.06 | 8.27 / 10.71 / 10.03 |
| cancelled | 6.52 / 7.22 / 7.43 | 7.77 / 9.56 / 8.96 |

**Hue sweep for `--accent-hue`** (0–350 in steps of 10, with gamut clipping): worst values in light mode primary-foreground/primary **5.15**, primary/background **5.22**, ring/background **4.04**; in dark mode primary-foreground/primary **7.34**. So every hue is allowed; the settings dialog needs no contrast warning.

Rule: `--border` is decorative only (table rows, card edge). Every control that is recognisable only by its outline (checkbox, radio, switch) uses `--input`. Text fields are filled (`--field`) and carry a bottom line in `--input`, see 4.4.

> **As of v0.4 (style "Weich", chosen 2026-10-11):** the actual values are in `frontend/src/styles/index.css`; the Vitest test `src/lib/contrast.test.ts` checks all pairs (incl. `field`) for every accent hue. The table above documents v0.3.

### 3.3 Spacing (4px grid)

Tailwind v4 uses `--spacing: 0.25rem` (4 px) as its base; `p-1` = 4 px, `p-2` = 8 px etc. Allowed steps: `0.5 (2px, fine-tuning only) · 1 · 1.5 · 2 · 3 · 4 · 5 · 6 · 8 · 10 · 12 · 16 · 24` (4–96 px).

| Use | Value |
|---|---|
| Icon ↔ text | 6–8 px (`gap-1.5`/`gap-2`) |
| Horizontal padding of inputs/buttons | 12 px (`px-3`) |
| Label → field | 6 px (`gap-1.5`) |
| Between fields | 16 px (`gap-4`) |
| Between form sections | 32 px (`gap-8`) |
| Card padding | 16 px mobile / 24 px desktop |
| Page margin | 16 px mobile / 24 px tablet / 32 px desktop |

### 3.4 Radius

```css
:root {
  --radius: 0.75rem;                      /* 12px base (style "Weich") */
  --radius-sm: calc(var(--radius) - 4px); /* 8px: kbd, small controls */
  --radius-md: calc(var(--radius) - 2px); /* 10px: inputs, buttons */
  --radius-lg: var(--radius);             /* 12px: popovers */
  --radius-xl: calc(var(--radius) + 4px); /* 16px: cards, fieldsets, tables, dialogs */
  --radius-full: 9999px;                  /* avatars, pill badges (optional) */
}
```

### 3.5 Typography

- Typeface: **Inter Variable** (self-hosted via `@fontsource-variable/inter`, no external requests – privacy), fallback `ui-sans-serif, system-ui, sans-serif`. Mono: `ui-monospace, "SF Mono", Menlo, monospace` for IBANs/references.
- `font-feature-settings: "cv11", "ss01"` optional (clearer figures); `"tnum"` via `tabular-nums`.
- **All amounts, quantities, dates and document numbers in tables and totals:** `font-variant-numeric: tabular-nums` (Tailwind `tabular-nums`), right-aligned.

| Token | Size / line height | Weight | Use |
|---|---|---|---|
| `text-xs` | 12 / 16 px | 500 | Badges, kbd, meta |
| `text-sm` | 14 / 20 px | 400/500 | **Default UI text**, tables, inputs (desktop) |
| `text-base` | 16 / 24 px | 400 | Running text, inputs on mobile (prevents iOS zoom) |
| `text-lg` | 18 / 28 px | 600 | Card titles, dialog titles |
| `text-xl` | 20 / 28 px | 600 | Page titles |
| `text-2xl` | 24 / 32 px | 600 | KPI figures on the dashboard |
| `text-3xl` | 30 / 36 px | 600 | Grand total in the editor |

Weights: 400 regular, 500 medium (labels, buttons, table headers), 600 semibold (titles). No 700+. Headings `tracking-tight` from `text-xl` up.

### 3.6 Shadows (materials)

```css
:root {
  --shadow-xs: 0 1px 2px 0 oklch(0 0 0 / 0.05);                                       /* inputs, buttons */
  --shadow-sm: 0 1px 3px 0 oklch(0 0 0 / 0.08), 0 1px 2px -1px oklch(0 0 0 / 0.08);  /* cards */
  --shadow-md: 0 4px 12px -2px oklch(0 0 0 / 0.10), 0 2px 4px -2px oklch(0 0 0 / 0.06); /* popover, menu, toast */
  --shadow-lg: 0 16px 40px -8px oklch(0 0 0 / 0.18), 0 4px 12px -4px oklch(0 0 0 / 0.08); /* dialog, ⌘K */
}
.dark { /* shadows barely visible on dark; elevation = lighter surface + 1px border */
  --shadow-sm: 0 1px 2px 0 oklch(0 0 0 / 0.4);
  --shadow-md: 0 4px 12px -2px oklch(0 0 0 / 0.5);
  --shadow-lg: 0 16px 40px -8px oklch(0 0 0 / 0.6);
}
```
In dark mode, depth comes from lighter surfaces (`background` < `card` < `popover`) plus `--border`.

### 3.7 Motion

```css
:root {
  --duration-fast: 150ms;   /* hover, focus, color changes, tooltip */
  --duration-base: 200ms;   /* popover, dropdown, toast in, accordion */
  --duration-slow: 250ms;   /* dialog, sheet, route transitions */
  --ease-out: cubic-bezier(0.16, 1, 0.3, 1);     /* entering */
  --ease-in: cubic-bezier(0.7, 0, 0.84, 0);      /* leaving (use ~80% of entering duration) */
  --ease-in-out: cubic-bezier(0.65, 0, 0.35, 1); /* moving/reordering */
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```
Motion (Framer): `<MotionConfig reducedMotion="user">` at the app root. Animate only `opacity` and `transform`. No animation longer than 250 ms, no movement as the only carrier of information.

---

## 4. Layout and components

### 4.1 App shell
- **Sidebar on the left** (shadcn `Sidebar`, 240 px, collapsible to a 56 px icon bar, state remembered): logo/company name, primary action "Neue Rechnung" (new invoice) (`N`), navigation: Dashboard, Documents (invoices, quotes, cancellations), Customers, Articles, Import; at the bottom Settings, Help, User. Sidebar surface = `--background`; a `--card` panel for the content is **not** needed; active entry `bg-accent text-accent-foreground`, inactive `text-muted-foreground`.
- **Top bar** (48–56 px, sticky): breadcrumb/page title on the left; centre/right a search trigger styled as an input, "Suchen … ⌘K" (search …) (opens the command palette), theme toggle (light/dark/system, `DropdownMenu`), help icon (`?`). **Help always in the same place** (WCAG 3.2.6).
- **Mobile (< 768 px):** sidebar as a `Sheet` (hamburger top left), bottom bar with at most 4 destinations (Dashboard, Documents, Customers, More) + floating "Neu" (new) button. Compensate for the bottom bar and top bar with `scroll-padding-top/bottom` (WCAG 2.4.11).
- Skip link "Zum Inhalt springen" (skip to content) as the first focusable element.

### 4.2 Content widths
| Content | Max. width |
|---|---|
| Forms (settings, customer) | 672 px (`max-w-2xl`), single column; two columns only for short fields that belong together (postcode/town) |
| Detail pages | 1024 px (`max-w-5xl`) |
| Tables/lists, dashboard | full width, max. 1440 px |
| Editor | full width, split view 50/50 (form ≥ 560 px, preview panel resizable), below 1280 px the preview as a tab/sheet |

### 4.3 Tables
- TanStack Table + virtual scrolling (`@tanstack/react-virtual`) from ~100 rows; sticky header row.
- **Density:** compact 36 px, standard 44 px (default), comfortable 52 px row height; selectable in the view options and saved.
- Column order for invoices: status · number · customer · subject · date · due · amount (right, tabular-nums, with currency) · actions (`…` menu).
- Text left, numbers/amounts right, header aligned like the content. Sorting via a button in the `<th>` with `aria-sort`.
- Filters as chips above the table (status, customer, period, currency); **saved views** as tabs/segments: Alle, Entwürfe, Offen, Überfällig, Bezahlt (all, drafts, open, overdue, paid). Column selection via a `DropdownMenu` with checkboxes.
- Whole row clickable (a link on the first cell element, not `onClick` on `<tr>`), row actions also reachable via a menu. Totals row per currency in the footer.
- On mobile the table becomes a list (one card per document: status badge, number, customer, amount, due date).

### 4.4 Forms
- **Style "Weich"** (decided 2026-10-11 after a design preview): text fields, selects and search fields are **filled** (`bg-field`, hover `bg-field-hover`) without a full border, 40 px high, radius 10 px. The field boundary is a **bottom line in `--input`** (≥ 3:1 against the fill and the card, WCAG 1.4.11; pattern as in Fluent 2 / M3 "filled"). Focus: the fill becomes `card`, 2 px ring in `--ring`. Shared classes in `components/ui/field-styles.ts`.
- Form sections (`Fieldset`) are cards (`rounded-xl`, soft shadow `--shadow-sm`); badges are pills; secondary buttons are filled (`bg-muted`) instead of outlined.
- **Label always above the field**, visible, `<label for>` (shadcn `FormLabel`). No placeholder as label; placeholder only as an example ("CHE-123.456.789").
- Mark optional fields as "(optional)" instead of cluttering required fields with `*` – most fields are required; where `*` is used, a legend at the top.
- Help text below the field (`FormDescription`, `aria-describedby`); the error message replaces the help text, sits below the field, starts with an icon and says **what to do** ("IBAN hat 21 Zeichen, erwartet 21 für CH – bitte prüfen" (IBAN has 21 characters, 21 expected for CH – please check)), `aria-invalid="true"`.
- **Inline validation when leaving the field** (on blur), after that check again on input; never turn red during the first entry.
- **Error summary** on submit (and on "Ausstellen" (issue) with the mandatory-fields check): a box at the top of the form with `role="alert"`, heading "2 Angaben fehlen" (2 details missing), a list with links to the fields; focus jumps to the box.
- Fitting `type`, `inputmode` (`decimal` for amounts/quantities), `autocomplete` (`organization`, `street-address`, `postal-code`, `email`, `tel`; `iban` does not exist → `off`).
- Parse amounts and quantities tolerant of the locale (de-CH `1’234.50` and `1234.50`, de-DE `1.234,50`), bring them into display format on blur.
- No redundant entry (WCAG 3.3.7): the customer address is prefilled from the master record, delivery address "wie Rechnungsadresse" (same as billing address) as a checkbox, onboarding data is reused in the settings.
- Saving: `⌘↵`/`Ctrl+↵`; drafts autosave (debounced 800 ms) with the status "Gespeichert vor 2 s" (saved 2 s ago) (`aria-live="polite"`, announce only state changes).

### 4.5 Empty states
- Structure: Lucide icon (32 px, `text-muted-foreground`) · title (1 sentence) · explanation (1–2 sentences) · **one** primary action (+ optional secondary action "Kunden importieren" (import customers)).
- Examples: "Noch keine Rechnungen – Erstelle deine erste Rechnung. [Neue Rechnung (N)]" (no invoices yet – create your first invoice); filtered list without results: "Keine Rechnungen für diesen Filter – [Filter zurücksetzen]" (no invoices for this filter – reset filter) (worded differently from a real empty state).
- Loading states as skeletons in the shape of the layout (no spinners for lists), `aria-busy` on the container.

### 4.6 Status badges
Every badge = **icon + text + color**, never color alone (WCAG 1.4.1). `text-xs font-medium`, `px-2 py-0.5`, `rounded-sm`, background `--status-*-bg`, text and icon `--status-*-fg`, 14 px icon with `aria-hidden`.

| Status | Text (de) | Lucide icon | Token |
|---|---|---|---|
| draft | Entwurf | `PencilLine` | status-draft |
| sent (quote) | Gesendet | `Send` | status-sent |
| issued | Ausgestellt | `FileCheck` | status-issued |
| partially_paid | Teilweise bezahlt | `CircleDashed` / `CircleDollarSign` | status-partially-paid |
| paid | Bezahlt | `CircleCheck` | status-paid |
| overdue (derived) | Überfällig | `CircleAlert` | status-overdue |
| cancelled | Storniert | `Ban` | status-cancelled (+ `line-through` on the amount in lists) |
| accepted | Angenommen | `ThumbsUp` | status-accepted |
| declined | Abgelehnt | `ThumbsDown` | status-declined |
| expired | Abgelaufen | `Clock` | status-expired |

In the display, "Überfällig" replaces "Ausgestellt"/"Teilweise bezahlt" and adds the days ("Überfällig · 12 Tage" (overdue · 12 days)).

### 4.7 Toasts and optimistic UI
- Sonner, positioned bottom right (desktop) or bottom centre above the bottom bar (mobile), at most 3 visible.
- Reversible actions (mark as paid, archive, delete draft): applied optimistically in the cache at once (TanStack Query `onMutate` + rollback in `onError`), toast "Als bezahlt markiert · **Rückgängig**" (marked as paid · undo) (`action: { label: "Rückgängig", onClick }`), duration **10 s** (instead of the default 4 s, WCAG 2.2.1 Timing), paused on hover/focus. `Ctrl/⌘+Z` triggers the last undo while the toast is visible.
- Errors: toast with a clear cause + "Erneut versuchen" (try again); error toasts do not close automatically.
- Toasts are live regions (Sonner: `aria-live`); they must not steal focus and must not hide a focused element.
- Irreversible (issue, cancel; deleting issued data is forbidden anyway): `AlertDialog` with the concrete consequence ("Nach dem Ausstellen ist die Rechnung unveränderlich. Korrekturen nur per Storno." (after issuing, the invoice cannot be changed; corrections only by cancellation)) and a verb button ("Ausstellen"), not "OK".

### 4.8 Command palette (⌘K / Ctrl+K)
- shadcn `CommandDialog` (cmdk). Groups: **Actions** (new invoice, new quote, new customer, switch theme), **Navigation**, **Documents** (server search, debounced 200 ms, number/customer/subject), **Customers**, **Articles**.
- Every entry shows its shortcut on the right (`<kbd>`). Recently used entries at the top. Search terms tolerant of umlauts ("Mueller" finds "Müller").

### 4.9 Keyboard shortcuts
Single-key shortcuts are active only when no input field has focus, and can be turned off in the settings (WCAG 2.1.4). Overview with `?` as a dialog, grouped. Each thing has one letter, taken from its English name so it is the same in every language: alone it creates one, after `G` it opens the list (`G O` stays for the quotes).

| Shortcut | Action |
|---|---|
| `⌘K` / `Ctrl+K` | Command palette |
| `/` | Focus the search in the current list |
| `I` (also `N`) | New invoice |
| `Q` | New quote |
| `C` | New customer |
| `A` | New article |
| `⌘↵` / `Ctrl+↵` | Save / submit form |
| `⌘Z` / `Ctrl+Z` | Undo the last action (while the undo toast is visible) |
| `?` | Shortcut overview |
| `Esc` | Close dialog/palette/sheet |
| `G` then `D` / `I` / `Q` / `C` / `A` / `S` | Go to dashboard / invoices / quotes / customers / articles / settings |
| `J` / `K` or `↓` / `↑` | Next / previous row in lists |
| `↵` | Open the selected row |
| `P` (in a document) | Open PDF |
| `Shift+P` (in a document) | Record payment / mark as paid |

Platform-dependent display: `⌘` on macOS/iOS, otherwise `Ctrl`.

### 4.10 Invoice editor (short rules)
- Positions as a table with inline inputs; Tab/Shift+Tab between cells, `↵` in the last cell adds a new row. Article autocomplete as a combobox (`role="combobox"`).
- Drag & drop for sorting (dnd-kit) **plus** an alternative without dragging: menu "Nach oben/unten" (move up/down) and `Alt+↑/↓` (WCAG 2.5.7), drag handle ≥ 24×24 px.
- Live PDF preview debounced (~600 ms), subtle loading state, preview panel with `aria-label="PDF-Vorschau"`; the preview is supplementary, all values (totals per tax rate, total) are also shown in the form.

### 4.11 Mobile minimum requirements
- Document list with status badges, filters "Überfällig"/"Offen" (overdue/open) reachable with one tap.
- Document detail: status, amount, due date at the top; actions "Bezahlt markieren" (mark as paid) (sheet with date = today and amount = remaining amount prefilled, partial payment possible), "PDF ansehen" (view PDF) (opens the PDF in the native viewer), "Teilen" (share) (Web Share API `navigator.share({ files })`, fallback: download/copy link).
- Touch targets ≥ 44×44 px on mobile (Apple HIG), ≥ 24×24 px everywhere (WCAG 2.5.8). Inputs `text-base` (16 px).
- No horizontal scrollbar at 320 px width (WCAG 1.4.10), except in the editor's position table (scrollable on purpose, with a visible hint).

---

## 5. Accessibility checklist (WCAG 2.2 AA, testable)

| # | Criterion | Check | How tested |
|---|---|---|---|
| 1 | 1.1.1 Non-text Content | Icon buttons have `aria-label`; decorative icons `aria-hidden`; logo has alt text | axe, review |
| 2 | 1.3.1 Info and Relationships | Real `<table>`/`<th scope>`; forms with `<label>`; error texts via `aria-describedby`; landmarks `nav`/`main`/`header` | axe |
| 3 | 1.3.5 Identify Input Purpose | `autocomplete` for name, company, address, email, phone | Review |
| 4 | 1.4.1 Use of Color | Status never by color alone (icon + text); links in text underlined | Visual review, greyscale screenshot |
| 5 | 1.4.3 Contrast (Text) | ≥ 4.5:1 – tokens as in 3.2; no text opacity below the token | axe `color-contrast` (light + dark) |
| 6 | 1.4.4 / 1.4.10 Resize, Reflow | 200 % zoom without loss; 320 px width without horizontal scrolling | Playwright viewport 320 |
| 7 | 1.4.11 Non-text Contrast | Field borders, checkboxes, focus ring ≥ 3:1 (`--input`, `--ring`) | Token test (Vitest) |
| 8 | 1.4.12 Text Spacing | No clipping with increased line/word spacing (no fixed heights for text) | Playwright with text-spacing CSS |
| 9 | 1.4.13 Content on Hover or Focus | Tooltips dismissable with `Esc`, hoverable, stay visible (Radix Tooltip) | Review |
| 10 | 2.1.1 / 2.1.2 Keyboard, No Keyboard Trap | All actions by keyboard; dialogs close with `Esc`, focus returns | Playwright keyboard E2E |
| 11 | 2.1.4 Character Key Shortcuts | Single-key shortcuts can be turned off, active only without focus in input fields | Unit test of the hook |
| 12 | 2.2.1 Timing Adjustable | Undo toast ≥ 10 s, paused on hover/focus; session expiry with warning + extend | E2E |
| 13 | 2.4.1 Bypass Blocks | Skip link as the first element | E2E |
| 14 | 2.4.2 / 2.4.6 Page Titled, Headings | `document.title` per route ("Rechnung R20260012 · Rhinvoice"); one `h1` per page | E2E |
| 15 | 2.4.3 Focus Order | DOM order = visual order; no positive `tabindex` | Lint (`jsx-a11y/tabindex-no-positive`) |
| 16 | 2.4.7 Focus Visible | `focus-visible:ring-2 ring-ring ring-offset-2 ring-offset-background` on all interactive elements; never `outline: none` without a replacement | Screenshot test |
| 17 | **2.4.11** Focus Not Obscured | `scroll-padding-top` = top bar height, `scroll-padding-bottom` = bottom bar/toast area; toasts do not cover focus | E2E: tab through a long list, `boundingBox` in the viewport |
| 18 | 2.5.3 Label in Name | Visible button text is contained in the accessible name | axe |
| 19 | **2.5.7** Dragging Movements | Positions sortable via menu/`Alt+↑/↓`; column width by keyboard/menu; preview splitter with buttons | E2E without drag |
| 20 | **2.5.8** Target Size | All targets ≥ 24×24 CSS px (icon buttons `size-8` = 32 px; badges not clickable); mobile ≥ 44 px | Playwright measurement of all `button, a, [role=button]` |
| 21 | 3.1.1 / 3.1.2 Language | `<html lang>` matches the UI language; document parts in another language with `lang` | E2E |
| 22 | 3.2.1 / 3.2.2 No Change of Context | Selecting in a select does not trigger navigation | Review |
| 23 | **3.2.6** Consistent Help | Help link in the top bar at a fixed position on all pages | E2E |
| 24 | 3.3.1 / 3.3.3 Error Identification, Suggestion | Error message at the field + summary, with a hint how to fix it | E2E mandatory-fields check |
| 25 | 3.3.4 Error Prevention (financial data) | Issue/cancel with a confirmation dialog and summary | E2E |
| 26 | **3.3.7** Redundant Entry | Prefilled from master data, "wie Rechnungsadresse", onboarding data reused | Review |
| 27 | **3.3.8** Accessible Authentication | Login: password manager/paste allowed (`autocomplete="username"`, `"current-password"`), no CAPTCHA; TOTP field `autocomplete="one-time-code"`, paste allowed | E2E: paste into the password field |
| 28 | 4.1.2 Name, Role, Value | Radix primitives; own widgets with the correct role; toggle with `aria-pressed` | axe |
| 29 | 4.1.3 Status Messages | Autosave status, toasts, search result count as `aria-live="polite"` | E2E/review |
| 30 | Motion | `prefers-reduced-motion` respected (CSS + `MotionConfig`) | Playwright `reducedMotion: "reduce"` |

Every Playwright test runs `@axe-core/playwright` with the tags `wcag2a, wcag2aa, wcag21a, wcag21aa, wcag22aa` – in light and in dark mode.

---

## 6. Localisation

- Supported UI locales: `de-CH`, `de-DE`, `de-AT`, `en`. Default = the installation's locale (derived from the company country, can be overridden); documents use the language/locale of the document or customer.
- **All numbers, amounts and dates via `Intl`**, centrally in `frontend/src/lib/format/` (pure functions, 100 % tested). Cache formatter instances.
  - Amounts: `new Intl.NumberFormat(locale, { style: "currency", currency, currencyDisplay: "code" | "symbol" })`. CHF always as the code `CHF`.
  - Quantities: `maximumFractionDigits` according to the unit (pieces 0–3, hours 2).
  - Percent: `style: "percent"`, `maximumFractionDigits: 1` (8.1 % / 8,1 %).
  - Date: `dateStyle: "medium"` in tables (`05.01.2026`), `"long"` on the PDF/detail page (`5. Januar 2026`, de-AT `5. Jänner 2026`).
  - Relative time: `Intl.RelativeTimeFormat` ("vor 2 Sekunden" (2 seconds ago)) for autosave/activity.
- No string concatenation of number + currency; no home-made thousands separators. Tests compare against the Intl output or normalise U+2019/U+00A0/U+202F.
- **Spelling:** de-CH without "ß" ("Strasse", "gemäss", "Massnahme") – the i18n catalogue `de-CH` derives from `de` and overrides; terms: CH/FL "MWST", DE/AT "USt"; AT "Jänner" (comes from Intl), "Rechnungsbetrag" (invoice amount) throughout.
- Tax and legal terms come from the country profile (backend), not from the UI catalogue, so the PDF and the UI are identical.
- Input parsing locale-aware and tolerant: ignore group separators `’ ' . ␣`, decimal separator from the locale; when ambiguous (`1.234` in de-CH) the locale wins.
- Week starts on Monday, 24-hour time, date input via date picker + text input `TT.MM.JJJJ`.
- UI texts: informal "Du" vs. formal "Sie" → **"Sie"** in de (business context, conservative), short verbs on buttons ("Ausstellen" (issue), "Speichern" (save)).
- `<html lang>` dynamic (`de-CH` etc.), translations via ICU MessageFormat (plural: "1 Rechnung" / "3 Rechnungen").

---

## 7. Implementation notes (Tailwind v4)

```css
@import "tailwindcss";
@custom-variant dark (&:is(.dark *));
@theme inline {
  --color-background: var(--background);
  --color-foreground: var(--foreground);
  /* … all tokens from 3.1, incl. --color-success, --color-warning, --color-info,
     --color-status-paid-fg / --color-status-paid-bg etc. */
  --font-sans: "Inter Variable", ui-sans-serif, system-ui, sans-serif;
  --radius-lg: var(--radius);
}
html { scroll-padding-top: 4rem; scroll-padding-bottom: 5rem; color-scheme: light dark; }
```
- Accent color at runtime: `document.documentElement.style.setProperty("--accent-hue", String(hue))` from the installation settings.
- A Vitest test calculates the contrasts of all token pairs from section 3.2 (OKLCH → sRGB → WCAG) and fails when a pair falls below the target – incl. the hue sweep 0–350.

## 8. Contrast calculation (reference)

OKLCH → OKLab (`a = C·cos h`, `b = C·sin h`) → LMS (cube) → linear sRGB (matrices by Björn Ottosson) → relative luminance `0.2126 R + 0.7152 G + 0.0722 B` → contrast `(L1 + 0.05) / (L2 + 0.05)`. Values outside the gamut are clipped; all tokens in 3.1 lie inside the sRGB gamut.
