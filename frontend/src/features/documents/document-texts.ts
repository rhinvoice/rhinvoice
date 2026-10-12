import type { TextKind, TextTemplate } from "@/features/shared/texts-api";

type EditableType = "invoice" | "quote";
type Language = TextTemplate["language"];

export interface DocumentTexts {
  readonly intro_text: string;
  readonly payment_text: string;
  readonly closing_text: string;
}

/** Templates of one kind for a document type and language, in their order. */
export function templatesFor(
  templates: readonly TextTemplate[],
  kind: TextKind,
  type: EditableType,
  language: Language,
): TextTemplate[] {
  return templates
    .filter(
      (template) =>
        template.kind === kind && template.document_type === type && template.language === language,
    )
    .sort((a, b) => a.position - b.position);
}

/** The texts a new document starts with: its default templates, joined by line breaks. */
export function defaultTexts(
  templates: readonly TextTemplate[],
  type: EditableType,
  language: Language,
): DocumentTexts {
  const joined = (kind: TextKind) =>
    templatesFor(templates, kind, type, language)
      .filter((template) => template.is_default)
      .map((template) => template.text)
      .join("\n");
  return {
    intro_text: joined("intro"),
    payment_text: joined("payment"),
    closing_text: joined("closing"),
  };
}

function lines(text: string): string[] {
  return text === "" ? [] : text.split("\n");
}

/** Index where ``block`` starts as whole lines inside ``text``, or -1. */
function findBlock(text: readonly string[], block: readonly string[]): number {
  if (block.length === 0) return -1;
  for (let start = 0; start + block.length <= text.length; start += 1) {
    if (block.every((line, offset) => text[start + offset] === line)) return start;
  }
  return -1;
}

/** Whether the template's text appears in ``text`` as whole lines. */
export function containsTemplate(text: string, template: TextTemplate): boolean {
  return findBlock(lines(text), lines(template.text)) !== -1;
}

/**
 * Switch a template on or off in a text made of templates (the payment terms).
 * The templates keep their order; text the user wrote stays at the end.
 */
export function toggleTemplate(
  text: string,
  template: TextTemplate,
  siblings: readonly TextTemplate[],
): string {
  let rest = lines(text);
  const present: TextTemplate[] = [];
  for (const candidate of siblings) {
    const block = lines(candidate.text);
    const start = findBlock(rest, block);
    if (start !== -1) {
      present.push(candidate);
      rest = [...rest.slice(0, start), ...rest.slice(start + block.length)];
    }
  }
  const active = present.some((candidate) => candidate.id === template.id);
  const chosen = active
    ? present.filter((candidate) => candidate.id !== template.id)
    : [...present, template];
  const ordered = siblings.filter((candidate) => chosen.some((item) => item.id === candidate.id));
  return [...ordered.map((candidate) => candidate.text), ...rest].join("\n").trim();
}

/**
 * When the language changes, texts that are still the defaults of the old
 * language become the defaults of the new one; changed texts stay.
 */
export function switchLanguage(
  current: DocumentTexts,
  templates: readonly TextTemplate[],
  type: EditableType,
  from: Language,
  to: Language,
): DocumentTexts {
  const before = defaultTexts(templates, type, from);
  const after = defaultTexts(templates, type, to);
  const pick = (key: keyof DocumentTexts) =>
    current[key] === before[key] ? after[key] : current[key];
  return {
    intro_text: pick("intro_text"),
    payment_text: pick("payment_text"),
    closing_text: pick("closing_text"),
  };
}
