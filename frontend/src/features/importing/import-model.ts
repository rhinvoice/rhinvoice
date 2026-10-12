import type { components } from "@/api/client";

export type ImportRun = components["schemas"]["ImportRunResponse"];
export type ImportRow = components["schemas"]["ImportRowResponse"];
export type ImportTemplate = components["schemas"]["TemplateResponse"];
export type ImportTarget = ImportRun["target"];
export type RowStatus = ImportRow["status"];
/** Field key -> column index (0-based). */
export type Mapping = Readonly<Record<string, number>>;

const UMLAUTS: readonly (readonly [string, string])[] = [
  ["ä", "ae"],
  ["ö", "oe"],
  ["ü", "ue"],
  ["ß", "ss"],
];

/** Compare column names like the server does (application/importing/parsing.py). */
export function normalizeName(text: string): string {
  let lowered = text.trim().toLowerCase();
  for (const [from, to] of UMLAUTS) {
    lowered = lowered.replaceAll(from, to);
  }
  return lowered.normalize("NFKD").replace(/[^a-z0-9]/g, "");
}

/** The columns of a file that a saved template names. */
export function mappingFromTemplate(
  template: Pick<ImportTemplate, "columns">,
  headers: readonly string[],
): Mapping {
  const names = headers.map(normalizeName);
  const mapping: Record<string, number> = {};
  for (const [field, column] of Object.entries(template.columns)) {
    const index = names.indexOf(normalizeName(column));
    if (index >= 0) {
      mapping[field] = index;
    }
  }
  return mapping;
}

/** A mapping as column names, to be saved as a template. */
export function templateColumns(
  mapping: Mapping,
  headers: readonly string[],
): Record<string, string> {
  const columns: Record<string, string> = {};
  for (const [field, index] of Object.entries(mapping)) {
    const header = headers[index];
    if (header !== undefined) {
      columns[field] = header;
    }
  }
  return columns;
}

export function fieldOfColumn(mapping: Mapping, column: number): string | null {
  return Object.entries(mapping).find(([, index]) => index === column)?.[0] ?? null;
}

/** Give a column a field (or none); a field belongs to one column at most. */
export function withColumn(mapping: Mapping, column: number, field: string | null): Mapping {
  const next: Record<string, number> = {};
  for (const [key, index] of Object.entries(mapping)) {
    if (index !== column && key !== field) {
      next[key] = index;
    }
  }
  if (field !== null) {
    next[field] = column;
  }
  return next;
}

export type RowFilter = "all" | RowStatus;

export function filterRows(rows: readonly ImportRow[], filter: RowFilter): readonly ImportRow[] {
  return filter === "all" ? rows : rows.filter((row) => row.status === filter);
}

/** Rows the import will save. */
export function importableCount(run: Pick<ImportRun, "counts">): number {
  return run.counts.new + run.counts.updated;
}

function csvCell(text: string): string {
  // Cells from the imported file must not become formulas in Excel (OWASP CSV injection).
  const value = /^[=+\-@\t\r]/.test(text) ? `'${text}` : text;
  return /[;"\n\r]/.test(value) ? `"${value.replaceAll('"', '""')}"` : value;
}

/** The report as CSV with semicolons (opens directly in Excel in the DACH region). */
export function reportCsv(
  rows: readonly ImportRow[],
  headers: readonly string[],
  describe: (row: ImportRow) => readonly string[],
): string {
  const lines = [headers, ...rows.map(describe)].map((cells) => cells.map(csvCell).join(";"));
  // A byte order mark makes Excel read the file as UTF-8.
  return `\uFEFF${lines.join("\r\n")}\r\n`;
}

const FIELD_KEYS = [
  "number",
  "company_name",
  "salutation",
  "first_name",
  "last_name",
  "contact_person",
  "street",
  "house_number",
  "supplement",
  "postal_code",
  "city",
  "postal_city",
  "country",
  "email",
  "phone",
  "vat_number",
  "group",
  "default_currency",
  "default_language",
  "default_discount",
  "payment_terms_days",
  "tax_exempt",
  "note",
  "customer_since",
  "name",
  "description",
  "unit",
  "price",
  "price_chf",
  "price_eur",
  "tax_category",
  "supply",
  "issue_date",
  "due_date",
  "customer_number",
  "customer_name",
  "currency",
  "net_amount",
  "tax_amount",
  "total_amount",
  "open_amount",
  "subject",
] as const;
type FieldKey = (typeof FIELD_KEYS)[number];

/** Fields named by the domain differently from the import columns. */
const FIELD_ALIASES: Readonly<Record<string, FieldKey>> = {
  "prices.CHF": "price_chf",
  "prices.EUR": "price_eur",
  total: "total_amount",
  net: "net_amount",
};

function isFieldKey(field: string): field is FieldKey {
  return (FIELD_KEYS as readonly string[]).includes(field);
}

/** Message key of a field's label, or null for fields the import does not know. */
export function fieldLabelKey(field: string): `import.field.${FieldKey}` | null {
  const key = FIELD_ALIASES[field] ?? field;
  return isFieldKey(key) ? `import.field.${key}` : null;
}

const PROBLEM_CODES = [
  "required",
  "invalid",
  "invalid_amount",
  "invalid_number",
  "invalid_flag",
  "invalid_date",
  "unknown_unit",
  "unknown_tax_rate",
  "unknown_supply",
  "unknown_language",
  "unknown_currency",
  "unknown_country_prefix",
  "non_positive_total",
  "net_above_total",
  "open_above_total",
] as const;
type ProblemCode = (typeof PROBLEM_CODES)[number];

/** Message key of the reason a row was refused, or null to show the server's text. */
export function problemKey(code: string): `import.problem.${ProblemCode}` | null {
  return (PROBLEM_CODES as readonly string[]).includes(code)
    ? (`import.problem.${code}` as `import.problem.${ProblemCode}`)
    : null;
}

/** Browsers send at most this many files in one request to the server (Starlette's limit). */
export const MAX_UPLOAD_FILES = 1000;
/** All PDF files of one import together (the server's limit). */
export const MAX_UPLOAD_BYTES = 200 * 1024 * 1024;

/** The name a file is sent with: its folders too, when a folder was chosen. */
export function uploadName(file: Pick<File, "name" | "webkitRelativePath">): string {
  return file.webkitRelativePath || file.name;
}

/** PDF and ZIP files of a choice; a folder's other files (pictures, .DS_Store) stay out. */
export function invoiceFiles<T extends Pick<File, "name" | "webkitRelativePath">>(
  files: Iterable<T>,
): T[] {
  return [...files].filter((file) => {
    const parts = uploadName(file).split("/");
    const hidden = parts.some((part) => part.startsWith(".") || part === "__MACOSX");
    return !hidden && /\.(pdf|zip)$/i.test(file.name);
  });
}

/** Why the chosen files cannot be sent, or null. */
export function uploadProblem(files: readonly Pick<File, "size">[]): "tooMany" | "tooLarge" | null {
  if (files.length > MAX_UPLOAD_FILES) return "tooMany";
  const bytes = files.reduce((sum, file) => sum + file.size, 0);
  return bytes > MAX_UPLOAD_BYTES ? "tooLarge" : null;
}

/** Size for people: "8.8 MB", "512 KB". */
export function sizeText(bytes: number, locale: string): string {
  const units = ["byte", "kilobyte", "megabyte"] as const;
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return new Intl.NumberFormat(locale, {
    style: "unit",
    unit: units[unit],
    unitDisplay: "short",
    maximumFractionDigits: unit === 2 ? 1 : 0,
  }).format(value);
}
