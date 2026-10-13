// rhinvoice.com/docs: the user documentation, in English (/docs/) and German (/docs/de/).
// Built into ../dist/docs after website/build.py has built the landing page into ../dist.
import starlight from "@astrojs/starlight";
import { defineConfig } from "astro/config";

const group = (label, de, items) => ({ label, translations: { de }, items });
const page = (slug, label, de) => ({ slug, label, translations: { de } });

export default defineConfig({
  site: "https://rhinvoice.com",
  base: "/docs",
  outDir: "../dist/docs",
  trailingSlash: "always",
  integrations: [
    starlight({
      // Page titles read "Old invoices | Rhinvoice"; the header adds "Docs" itself.
      title: "Rhinvoice",
      description:
        "Documentation of Rhinvoice, the free open-source invoicing program for Switzerland, Liechtenstein, Germany and Austria.",
      logo: { src: "./src/assets/logo.svg", alt: "Rhinvoice" },
      favicon: "/favicon.svg",
      defaultLocale: "root",
      locales: {
        root: { label: "English", lang: "en" },
        de: { label: "Deutsch", lang: "de" },
      },
      social: [
        { icon: "github", label: "GitHub", href: "https://github.com/rhinvoice/rhinvoice" },
      ],
      // GitHub Pages serves the landing page's 404.html for every missing page, /docs/ included.
      disable404Route: true,
      editLink: { baseUrl: "https://github.com/rhinvoice/rhinvoice/edit/main/website/docs/" },
      lastUpdated: true,
      customCss: ["./src/styles/rhinvoice.css"],
      routeMiddleware: "./src/route-data.ts",
      components: { SiteTitle: "./src/components/SiteTitle.astro" },
      head: [
        { tag: "meta", attrs: { name: "theme-color", content: "#f6f8fb", media: "(prefers-color-scheme: light)" } },
        { tag: "meta", attrs: { name: "theme-color", content: "#0d1520", media: "(prefers-color-scheme: dark)" } },
        { tag: "meta", attrs: { name: "robots", content: "index, follow, max-snippet:-1, max-image-preview:large" } },
        { tag: "link", attrs: { rel: "apple-touch-icon", href: "https://rhinvoice.com/assets/img/apple-touch-icon.png" } },
        { tag: "meta", attrs: { property: "og:image:width", content: "1200" } },
        { tag: "meta", attrs: { property: "og:image:height", content: "630" } },
      ],
      sidebar: [
        group("Getting started", "Erste Schritte", [
          page("getting-started/what-is-rhinvoice", "What is Rhinvoice?", "Was ist Rhinvoice?"),
          page("getting-started/installation", "Installation", "Installation"),
          page("getting-started/first-start", "First start", "Erster Start"),
          page("getting-started/first-invoice", "Your first invoice", "Die erste Rechnung"),
        ]),
        group("Countries", "Länder", [
          page("countries/switzerland", "Switzerland", "Schweiz"),
          page("countries/liechtenstein", "Liechtenstein", "Liechtenstein"),
          page("countries/germany", "Germany", "Deutschland"),
          page("countries/austria", "Austria", "Österreich"),
        ]),
        // Its own entry, so that everyone sees Rhinvoice is open to more countries.
        page("countries/more-countries", "More countries", "Weitere Länder"),
        group("Invoices", "Rechnungen", [
          page("invoices/quotes", "Quotes", "Angebote"),
          page("invoices/issue-and-cancel", "Issuing and cancelling", "Ausstellen und Storno"),
          page("invoices/payments-and-reminders", "Payments and reminders", "Zahlungen und Mahnungen"),
          page("invoices/recurring", "Recurring invoices", "Wiederkehrende Rechnungen"),
          page("invoices/e-invoice", "E-invoices", "E-Rechnung"),
        ]),
        group("Moving over", "Umzug", [
          page("moving/customers-and-articles", "Customers and articles", "Kunden und Artikel"),
          page("moving/old-invoices", "Old invoices", "Alte Rechnungen übernehmen"),
        ]),
        group("Running it", "Betrieb", [
          page("operations/backup", "Backup and restore", "Backup und Wiederherstellen"),
          page("operations/update", "Updating", "Update"),
          page("operations/uninstall", "Uninstalling", "Deinstallieren"),
        ]),
        group("Help", "Hilfe", [
          page("help/faq", "Frequently asked questions", "Häufige Fragen"),
          page("help/developers", "For developers", "Für Entwickler"),
        ]),
      ],
    }),
  ],
});
