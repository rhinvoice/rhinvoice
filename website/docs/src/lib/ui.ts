/**
 * The docs' own interface words in every language (Starlight translates its own ones).
 * French and Italian were machine-translated; their pages say so (see translationIssueHref).
 */
import { languageOf } from "./paths";

interface Words {
  readonly docs: string;
  readonly docsName: string;
  readonly language: string;
  readonly breadcrumbs: string;
  readonly readingTime: (minutes: number) => string;
  readonly since: (version: string) => string;
  readonly legal: string;
  readonly noTaxAdvice: string;
  readonly legalLinks: readonly (readonly [href: string, label: string])[];
  readonly demoTitle: string;
  readonly demoText: string;
  /** Open Graph locale of the page and its image on rhinvoice.com/assets/img/. */
  readonly ogLocale: string;
  readonly ogImage: string;
}

const WORDS: Record<"de" | "en" | "fr" | "it", Words> = {
  en: {
    docs: "Docs",
    docsName: "Rhinvoice Docs",
    language: "Language",
    breadcrumbs: "Breadcrumbs",
    readingTime: (minutes) => `${minutes} min read`,
    since: (version) => `Since version ${version}`,
    legal: "Legal",
    noTaxAdvice: "No tax advice",
    legalLinks: [
      ["/legal-notice/", "Legal notice"],
      ["/privacy/", "Privacy"],
    ],
    demoTitle: "Try the demo",
    demoText: "Write invoices without installing anything:",
    ogLocale: "en_US",
    ogImage: "og.png",
  },
  de: {
    docs: "Dokumentation",
    docsName: "Rhinvoice Dokumentation",
    language: "Sprache",
    breadcrumbs: "Brotkrumen",
    readingTime: (minutes) => `Lesezeit ${minutes} ${minutes === 1 ? "Minute" : "Minuten"}`,
    since: (version) => `Ab Version ${version}`,
    legal: "Rechtliches",
    noTaxAdvice: "Keine Steuerberatung",
    legalLinks: [
      ["/de/impressum/", "Impressum"],
      ["/de/datenschutz/", "Datenschutz"],
    ],
    demoTitle: "Demo ausprobieren",
    demoText: "Rechnungen schreiben, ohne etwas zu installieren:",
    ogLocale: "de_DE",
    ogImage: "og-de.png",
  },
  fr: {
    docs: "Documentation",
    docsName: "Documentation Rhinvoice",
    language: "Langue",
    breadcrumbs: "Fil d’Ariane",
    readingTime: (minutes) => `Lecture : ${minutes} min`,
    since: (version) => `Depuis la version ${version}`,
    legal: "Informations légales",
    noTaxAdvice: "Pas de conseil fiscal",
    legalLinks: [
      ["/fr/mentions-legales/", "Mentions légales"],
      ["/fr/protection-des-donnees/", "Protection des données"],
    ],
    demoTitle: "Essayer la démo",
    demoText: "Écrire des factures sans rien installer :",
    ogLocale: "fr_CH",
    ogImage: "og-fr.png",
  },
  it: {
    docs: "Documentazione",
    docsName: "Documentazione Rhinvoice",
    language: "Lingua",
    breadcrumbs: "Percorso",
    readingTime: (minutes) => `Lettura: ${minutes} min`,
    since: (version) => `Dalla versione ${version}`,
    legal: "Note legali",
    noTaxAdvice: "Nessuna consulenza fiscale",
    legalLinks: [
      ["/it/note-legali/", "Note legali"],
      ["/it/protezione-dei-dati/", "Protezione dei dati"],
    ],
    demoTitle: "Provare la demo",
    demoText: "Scrivere fatture senza installare nulla:",
    ogLocale: "it_CH",
    ogImage: "og-it.png",
  },
};

export function words(lang: string): Words {
  return WORDS[languageOf(lang)];
}

/** The notice above every machine-translated page, with where to report a wrong translation. */
export const MACHINE_TRANSLATED: Partial<Record<string, { readonly text: string; readonly link: string; readonly mail: string; readonly language: string }>> = {
  fr: {
    text: "Cette page a été traduite automatiquement. Vos remarques sont les bienvenues :",
    link: "signaler une erreur de traduction sur GitHub",
    mail: "ou écrire à",
    language: "French",
  },
  it: {
    text: "Questa pagina è stata tradotta automaticamente. Le segnalazioni sono benvenute:",
    link: "segnalare un errore di traduzione su GitHub",
    mail: "oppure scrivere a",
    language: "Italian",
  },
};

/** A new issue with the translation form, the language and the page already filled in. */
export function translationIssueHref(language: string, pageUrl: string): string {
  const query = new URLSearchParams({ template: "translation.yml", language, page: pageUrl });
  return `https://github.com/rhinvoice/rhinvoice/issues/new?${query.toString()}`;
}
