import type { CreateRequest, DocumentDetail } from "@/features/documents/api";
import { documentToForm, formToDraft } from "@/features/documents/document-form-model";
import type { Locale } from "@/lib/locale";

type QuoteLine = Pick<DocumentDetail["lines"][number], "id" | "kind" | "in_total">;

/** Whether a quote has items outside its total: then converting asks which ones were taken. */
export function hasOptions(lines: readonly QuoteLine[]): boolean {
  return lines.some((line) => line.in_total !== "yes");
}

/** The items ticked when the conversion dialog opens: those in the total. */
export function initialChoice(lines: readonly QuoteLine[]): string[] {
  return lines
    .filter((line) => line.kind === "item" && line.in_total === "yes")
    .map((line) => line.id);
}

/**
 * The invoice a quote becomes with the ``chosen`` items, as the preview calculates it: dated
 * ``today``, the chosen items as ordinary ones and every text line (ADR 0045).
 */
export function conversionRequest(
  quote: DocumentDetail,
  chosen: ReadonlySet<string>,
  locale: Locale,
  today: string,
): CreateRequest {
  const form = documentToForm(quote, locale);
  const lines = form.lines
    .filter((line) => line.kind === "text" || chosen.has(line.key))
    .map((line) => ({ ...line, in_total: "yes" as const, alternative_to: null }));
  return {
    type: "invoice",
    ...formToDraft({ ...form, issue_date: today, due_date: "", lines }, locale),
  };
}
