// rhinvoice.com/docs: the user documentation, in English (/docs/), German (/docs/de/), and for the
// core pages French (/docs/fr/) and Italian (/docs/it/). A page without a French or Italian text
// is shown in English there, with Starlight's "not translated yet" notice (src/route-data.ts
// points its canonical URL to the English page).
// Built into ../dist/docs after website/build.py has built the landing page into ../dist.
import { readdirSync } from "node:fs";

import sitemap from "@astrojs/sitemap";
import starlight from "@astrojs/starlight";
import { defineConfig } from "astro/config";

// The pages written in French or Italian, as "fr/" or "fr/getting-started/installation/".
const TRANSLATED = ["fr", "it"];
const CONTENT = new URL("./src/content/docs/", import.meta.url);
const written = new Set(
  TRANSLATED.flatMap((lang) =>
    readdirSync(new URL(`${lang}/`, CONTENT), { recursive: true, encoding: "utf8" })
      .filter((file) => /\.mdx?$/.test(file))
      .map((file) => `${lang}/${file.replace(/\.mdx?$/, "/").replace(/(^|\/)index\/$/, "$1")}`),
  ),
);
/** A French or Italian address that only shows the English page (Starlight's fallback). */
const isFallback = (url) => {
  const path = new URL(url).pathname.replace(/^\/docs\//, "");
  return TRANSLATED.includes(path.split("/")[0]) && !written.has(path);
};

// Labels as [English, German, French, Italian].
const translations = ([, de, fr, it]) => ({ de, fr, it });
const group = (labels, items) => ({ label: labels[0], translations: translations(labels), items });
const page = (slug, labels, attrs = {}) => ({ slug, label: labels[0], translations: translations(labels), attrs });

export default defineConfig({
  site: "https://rhinvoice.com",
  base: "/docs",
  outDir: "../dist/docs",
  trailingSlash: "always",
  integrations: [
    // Starlight's own sitemap, without the fallback pages: they point to the English page.
    sitemap({
      i18n: { defaultLocale: "root", locales: { root: "en", de: "de", fr: "fr", it: "it" } },
      filter: (page) => !isFallback(page),
      serialize: (item) => ({ ...item, links: item.links?.filter((link) => !isFallback(link.url)) }),
    }),
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
        fr: { label: "Français", lang: "fr" },
        it: { label: "Italiano", lang: "it" },
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
      components: {
        Banner: "./src/components/Banner.astro",
        SiteTitle: "./src/components/SiteTitle.astro",
        PageTitle: "./src/components/PageTitle.astro",
        PageSidebar: "./src/components/PageSidebar.astro",
        Sidebar: "./src/components/Sidebar.astro",
        LanguageSelect: "./src/components/LanguageSelect.astro",
        SocialIcons: "./src/components/SocialIcons.astro",
        ThemeSelect: "./src/components/ThemeSelect.astro",
        Footer: "./src/components/Footer.astro",
      },
      head: [
        { tag: "meta", attrs: { name: "theme-color", content: "#f6f8fb", media: "(prefers-color-scheme: light)" } },
        { tag: "meta", attrs: { name: "theme-color", content: "#0d1520", media: "(prefers-color-scheme: dark)" } },
        { tag: "meta", attrs: { name: "robots", content: "index, follow, max-snippet:-1, max-image-preview:large" } },
        { tag: "link", attrs: { rel: "apple-touch-icon", href: "https://rhinvoice.com/assets/img/apple-touch-icon.png" } },
        { tag: "meta", attrs: { property: "og:image:width", content: "1200" } },
        { tag: "meta", attrs: { property: "og:image:height", content: "630" } },
      ],
      sidebar: [
        group(["Getting started", "Erste Schritte", "Premiers pas", "Primi passi"], [
          page("getting-started/what-is-rhinvoice", ["What is Rhinvoice?", "Was ist Rhinvoice?", "Qu’est-ce que Rhinvoice?", "Che cos’è Rhinvoice?"]),
          page("getting-started/installation", ["Installation", "Installation", "Installation", "Installazione"]),
          page("getting-started/install-desktop", ["Windows and Mac", "Windows und Mac", "Windows et Mac", "Windows e Mac"]),
          page("getting-started/first-start", ["First start", "Erster Start", "Premier démarrage", "Primo avvio"]),
          page("getting-started/first-invoice", ["Your first invoice", "Die erste Rechnung", "Votre première facture", "La prima fattura"]),
        ]),
        group(["Countries", "Länder", "Pays", "Paesi"], [
          page("countries/switzerland", ["Switzerland", "Schweiz", "Suisse", "Svizzera"], { "data-code": "CH" }),
          page("countries/liechtenstein", ["Liechtenstein", "Liechtenstein", "Liechtenstein", "Liechtenstein"], { "data-code": "FL" }),
          page("countries/germany", ["Germany", "Deutschland", "Allemagne", "Germania"], { "data-code": "DE" }),
          page("countries/austria", ["Austria", "Österreich", "Autriche", "Austria"], { "data-code": "AT" }),
        ]),
        // Its own entry, so that everyone sees Rhinvoice is open to more countries.
        page("countries/more-countries", ["More countries", "Weitere Länder", "Autres pays", "Altri paesi"]),
        group(["Invoices", "Rechnungen", "Factures", "Fatture"], [
          page("invoices/quotes", ["Quotes", "Angebote", "Offres", "Offerte"]),
          page("invoices/issue-and-cancel", ["Issuing and cancelling", "Ausstellen und Storno", "Émettre et annuler", "Emettere e stornare"]),
          page("invoices/payments-and-reminders", ["Payments and reminders", "Zahlungen und Mahnungen", "Paiements et rappels", "Pagamenti e solleciti"]),
          page("invoices/write-off", ["Writing off invoices", "Rechnungen abschreiben", "Passer des factures en perte", "Stralciare fatture"]),
          page("invoices/recurring", ["Recurring invoices", "Wiederkehrende Rechnungen", "Factures récurrentes", "Fatture ricorrenti"]),
          page("invoices/e-invoice", ["E-invoices", "E-Rechnung", "Factures électroniques", "Fatture elettroniche"]),
        ]),
        group(["Moving over", "Umzug", "Changer de programme", "Cambio di programma"], [
          page("moving/customers-and-articles", ["Customers and articles", "Kunden und Artikel", "Clients et articles", "Clienti e articoli"]),
          page("moving/old-invoices", ["Old invoices", "Alte Rechnungen übernehmen", "Anciennes factures", "Fatture precedenti"]),
        ]),
        group(["Running it", "Betrieb", "Exploitation", "Gestione"], [
          page("operations/backup", ["Backup and restore", "Backup und Wiederherstellen", "Sauvegarde et restauration", "Backup e ripristino"]),
          page("operations/backup-desktop", ["Backup in the program", "Backup im Programm", "Sauvegarde dans le programme", "Backup nel programma"]),
          page("operations/backup-google-drive", ["Backup to Google Drive", "Backup auf Google Drive", "Sauvegarde sur Google Drive", "Backup su Google Drive"]),
          page("operations/update", ["Updating", "Update", "Mise à jour", "Aggiornamento"]),
          page("operations/uninstall", ["Uninstalling", "Deinstallieren", "Désinstallation", "Disinstallazione"]),
        ]),
        group(["Help", "Hilfe", "Aide", "Aiuto"], [
          page("help/changelog", ["What's new", "Neuigkeiten", "Nouveautés", "Novità"]),
          page("help/faq", ["Frequently asked questions", "Häufige Fragen", "Questions fréquentes", "Domande frequenti"]),
          page("help/developers", ["For developers", "Für Entwickler", "Pour les développeurs", "Per sviluppatori"]),
        ]),
      ],
    }),
  ],
});
