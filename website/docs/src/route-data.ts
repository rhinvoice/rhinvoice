/**
 * What every docs page tells search engines and answer engines beyond Starlight's own head:
 * a preview image in the page's language, and structured data (JSON-LD) naming the page as
 * an article about Rhinvoice, its place in the docs, and its questions and answers.
 */
import { defineRouteMiddleware, type StarlightRouteData } from "@astrojs/starlight/route-data";

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
  const docsName = lang === "de" ? "Rhinvoice Dokumentation" : "Rhinvoice Docs";
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
      inLanguage: lang,
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
      inLanguage: lang,
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
  const german = route.lang === "de";
  const image = `${SITE}/assets/img/${german ? "og-de" : "og"}.png`;
  // Open Graph wants language and territory, as on the landing page.
  for (const tag of route.head) {
    if (tag.tag === "meta" && tag.attrs?.property === "og:locale") {
      tag.attrs.content = german ? "de_DE" : "en_US";
    }
  }
  route.head.push(
    { tag: "meta", attrs: { property: "og:locale:alternate", content: german ? "en_US" : "de_DE" } },
    { tag: "meta", attrs: { property: "og:image", content: image } },
    { tag: "meta", attrs: { name: "twitter:image", content: image } },
    {
      tag: "script",
      attrs: { type: "application/ld+json" },
      // "<" never reaches the HTML parser as a tag start inside the script.
      content: JSON.stringify(structuredData(route, url)).replaceAll("<", "\\u003c"),
    },
  );
});
