// rhinvoice.com/docs: the user documentation, in English (/docs/), German (/docs/de/), French
// (/docs/fr/) and Italian (/docs/it/). Every page exists in all four (scripts/check.py).
// Built into ../dist/docs after website/build.py has built the landing page into ../dist.
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import starlight from "@astrojs/starlight";
import { defineConfig } from "astro/config";

// Astro hashes the inline scripts it knows of for the Content-Security-Policy; the one in
// Starlight's search button (the shortcut label) it misses, so its hash is taken from the
// component itself. `scripts/check.py csp` fails if any inline script of a page lacks one.
const searchComponent = readFileSync(
  new URL("./node_modules/@astrojs/starlight/dist/components/Search.astro", import.meta.url),
  "utf8",
);
const inlineScriptHashes = [...searchComponent.matchAll(/<script is:inline>([\s\S]*?)<\/script>/g)].map(
  ([, script]) => `sha256-${createHash("sha256").update(script).digest("base64")}`,
);

// Labels as [English, German, French, Italian].
const translations = ([, de, fr, it]) => ({ de, fr, it });
const group = (labels, items) => ({ label: labels[0], translations: translations(labels), items });
const page = (slug, labels, attrs = {}) => ({ slug, label: labels[0], translations: translations(labels), attrs });

export default defineConfig({
  site: "https://rhinvoice.com",
  base: "/docs",
  outDir: "../dist/docs",
  trailingSlash: "always",
  // A Content-Security-Policy <meta> on every page, like the landing page's (ADR 0033). Astro
  // adds the hashes of its inline scripts; the search (Pagefind) runs WebAssembly. Styles allow
  // 'unsafe-inline': the code blocks colour their tokens with style attributes. frame-ancestors
  // cannot be set in a <meta>.
  security: {
    csp: {
      directives: [
        "default-src 'self'",
        "img-src 'self' data:",
        "font-src 'self'",
        "connect-src 'self'",
        "form-action 'self'",
        "base-uri 'self'",
        "object-src 'none'",
        "manifest-src 'self'",
        "upgrade-insecure-requests",
      ],
      scriptDirective: { resources: ["'self'", "'wasm-unsafe-eval'"], hashes: inlineScriptHashes },
      styleDirective: { resources: ["'self'", "'unsafe-inline'"] },
    },
  },
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
