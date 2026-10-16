/**
 * What every docs page tells search engines and answer engines beyond Starlight's own head:
 * a preview image in the page's language, and structured data (JSON-LD) naming the page as
 * an article about Rhinvoice, its place in the docs, and its questions and answers.
 */
import { defineRouteMiddleware, type StarlightRouteData } from "@astrojs/starlight/route-data";

import { LANGUAGES, docsBase, languageOf, type Language } from "./lib/paths";
import { words } from "./lib/ui";

const SITE = "https://rhinvoice.com";
const SOFTWARE = {
  "@type": "SoftwareApplication",
  "@id": `${SITE}/#software`,
  name: "Rhinvoice",
  url: `${SITE}/`,
  applicationCategory: "BusinessApplication",
  applicationSubCategory: "Invoicing",
  operatingSystem: "Docker (Linux, macOS, Windows)",
  license: "https://www.gnu.org/licenses/agpl-3.0.html",
  offers: { "@type": "Offer", price: "0", priceCurrency: "CHF" },
};
/** Every written page as "<lang>/<slug>" ("en/" for the English start page), read at build time. */
const WRITTEN = new Set(
  Object.keys(import.meta.glob("./content/docs/**/*.{md,mdx}")).map((file) => {
    const id = file.replace(/^\.\/content\/docs\//, "").replace(/\.mdx?$/, "").replace(/(^|\/)index$/, "");
    const [first = "", ...rest] = id.split("/");
    return (LANGUAGES as readonly string[]).includes(first) && first !== "en" ? `${first}/${rest.join("/")}` : `en/${id}`;
  }),
);

/** The page's path below its language's docs root, e.g. "getting-started/installation". */
function slugOf(pathname: string, lang: Language): string {
  return pathname.slice(docsBase(lang).length).replace(/\/$/, "");
}

function written(lang: Language, slug: string): boolean {
  return WRITTEN.has(`${lang}/${slug}`);
}

const PUBLISHER = {
  "@type": "Organization",
  // The same entity as on rhinvoice.com and webberz.ch.
  "@id": "https://www.webberz.ch/#firma",
  name: "webberz",
  url: "https://www.webberz.ch/",
};

type Link = { type: "link"; label: string; href: string; isCurrent: boolean };
type Group = { type: "group"; label: string; entries: Entry[] };
type Entry = Link | Group;

/** The sidebar group that holds the current page, for the breadcrumb. */
function currentGroup(entries: Entry[]): Group | undefined {
  for (const entry of entries) {
    if (entry.type !== "group") continue;
    if (entry.entries.some((child) => child.type === "link" && child.isCurrent)) return entry;
    const nested = currentGroup(entry.entries);
    if (nested !== undefined) return nested;
  }
  return undefined;
}

function structuredData(route: StarlightRouteData, url: string): object[] {
  const { entry, lang, siteTitleHref, lastUpdated } = route;
  const docsHome = new URL(siteTitleHref, SITE).href;
  const { docsName } = words(lang);
  const group = currentGroup(route.sidebar as Entry[]);
  // A group has no page of its own: its crumb leads to its first page.
  const first = group?.entries.find((child): child is Link => child.type === "link");
  const crumbs = [
    { name: docsName, item: docsHome },
    ...(group === undefined || first === undefined
      ? []
      : [{ name: group.label, item: new URL(first.href, SITE).href }]),
    { name: entry.data.title, item: url },
  ];
  const data: object[] = [
    {
      "@context": "https://schema.org",
      "@type": "TechArticle",
      headline: entry.data.title,
      description: entry.data.description,
      // A page without translation yet shows the English text.
      inLanguage: route.entryMeta.lang,
      url,
      ...(lastUpdated === undefined ? {} : { dateModified: lastUpdated.toISOString() }),
      author: PUBLISHER,
      publisher: PUBLISHER,
      about: SOFTWARE,
      isPartOf: { "@type": "WebSite", name: docsName, url: docsHome },
    },
    {
      "@context": "https://schema.org",
      "@type": "BreadcrumbList",
      itemListElement: crumbs.map((crumb, index) => ({
        "@type": "ListItem",
        position: index + 1,
        ...crumb,
      })),
    },
  ];
  const faq = entry.data.faq;
  if (faq !== undefined && faq.length > 0) {
    data.push({
      "@context": "https://schema.org",
      "@type": "FAQPage",
      inLanguage: route.entryMeta.lang,
      mainEntity: faq.map(({ q, a }) => ({
        "@type": "Question",
        name: q,
        acceptedAnswer: { "@type": "Answer", text: a },
      })),
    });
  }
  return data;
}

export const onRequest = defineRouteMiddleware((context) => {
  const route = context.locals.starlightRoute;
  const url = new URL(context.url.pathname, SITE).href;
  const lang = languageOf(route.lang);
  const slug = slugOf(context.url.pathname, lang);
  const { ogLocale, ogImage } = words(lang);
  const image = `${SITE}/assets/img/${ogImage}`;
  // A page shown in English because it has no translation yet points search engines to the
  // English page and names no language versions of its own.
  const english = new URL(`${docsBase("en")}${slug === "" ? "" : `${slug}/`}`, SITE).href;
  const kept = route.head.filter((tag) => {
    const { rel, hreflang } = tag.attrs ?? {};
    if (tag.tag !== "link" || rel !== "alternate" || typeof hreflang !== "string") return true;
    if (route.isFallback) return false;
    return hreflang === "x-default" || written(languageOf(hreflang), slug);
  });
  route.head.splice(0, route.head.length, ...kept);
  const alternates = route.isFallback ? [] : LANGUAGES.filter((other) => other !== lang && written(other, slug));
  for (const tag of route.head) {
    if (tag.tag === "meta" && tag.attrs?.property === "og:locale") {
      // Open Graph wants language and territory, as on the landing page.
      tag.attrs.content = ogLocale;
    }
    if (route.isFallback && tag.tag === "link" && tag.attrs?.rel === "canonical") tag.attrs.href = english;
    if (route.isFallback && tag.tag === "meta" && tag.attrs?.property === "og:url") tag.attrs.content = english;
  }
  route.head.push(
    ...alternates.map((other) => ({
      tag: "meta" as const,
      attrs: { property: "og:locale:alternate", content: words(other).ogLocale },
    })),
    { tag: "meta", attrs: { property: "og:image", content: image } },
    { tag: "meta", attrs: { name: "twitter:image", content: image } },
    {
      tag: "script",
      attrs: { type: "application/ld+json" },
      // "<" never reaches the HTML parser as a tag start inside the script.
      content: JSON.stringify(structuredData(route, route.isFallback ? english : url)).replaceAll("<", "\\u003c"),
    },
  );
});
