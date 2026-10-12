import { useQuery, type QueryClient } from "@tanstack/react-query";
import {
  createRootRouteWithContext,
  createRoute,
  createRouter,
  lazyRouteComponent,
  Outlet,
  redirect,
  stripSearchParams,
  type ParsedLocation,
} from "@tanstack/react-router";

import { ErrorPage } from "@/app/pages/error-page";
import { AppShell } from "@/app/shell/app-shell";
import { meQuery, setupStatusQuery } from "@/features/auth/api";
import { ApiError } from "@/lib/api-error";
import { safeRedirect } from "@/lib/redirect";
import { deferSetup, isSetupDeferred } from "@/lib/setup-deferral";
import { SETTINGS_TABS, type SettingsTab } from "@/app/pages/settings-tabs";
import { companyQuery } from "@/features/company/api";
import { parseListSearch, type ListSearch } from "@/features/shared/list-search";
import {
  DOCUMENT_LIST_DEFAULTS,
  parseDocumentListSearch,
  type DocumentListSearch,
  type ListKind,
} from "@/features/documents/document-list-search";

const CUSTOMER_SORTS = ["number", "name", "city", "created_at"] as const;
const LIST_DEFAULTS = { q: "", archived: false, sort: "number", dir: "asc", page: 1 } as const;
const ARTICLE_SORTS = ["number", "name", "group", "created_at"] as const;

// Pages are loaded on demand to keep the initial bundle small.
const LoginPage = lazyRouteComponent(() => import("@/features/auth/login-page"), "LoginPage");
const SetupPage = lazyRouteComponent(() => import("@/features/auth/setup-page"), "SetupPage");
const CompanyWizard = lazyRouteComponent(
  () => import("@/features/company/company-wizard"),
  "CompanyWizard",
);
const OverviewPage = lazyRouteComponent(() => import("@/app/pages/overview-page"), "OverviewPage");
const DunningPage = lazyRouteComponent(
  () => import("@/features/dunning/dunning-page"),
  "DunningPage",
);
const RecurringListPage = lazyRouteComponent(
  () => import("@/features/documents/recurring-pages"),
  "RecurringListPage",
);
const NewPlanPage = lazyRouteComponent(
  () => import("@/features/documents/recurring-pages"),
  "NewPlanPage",
);
const PlanPage = lazyRouteComponent(
  () => import("@/features/documents/recurring-pages"),
  "PlanPage",
);
const ImportPage = lazyRouteComponent(
  () => import("@/features/importing/import-page"),
  "ImportPage",
);
const SettingsPage = lazyRouteComponent(() => import("@/app/pages/settings-page"), "SettingsPage");
const CustomerListPage = lazyRouteComponent(
  () => import("@/features/customers/customer-list-page"),
  "CustomerListPage",
);
const NewCustomerPage = lazyRouteComponent(
  () => import("@/features/customers/customer-pages"),
  "NewCustomerPage",
);
const CustomerPage = lazyRouteComponent(
  () => import("@/features/customers/customer-pages"),
  "CustomerPage",
);
const ArticleListPage = lazyRouteComponent(
  () => import("@/features/articles/article-list-page"),
  "ArticleListPage",
);
const NewArticlePage = lazyRouteComponent(
  () => import("@/features/articles/article-pages"),
  "NewArticlePage",
);
const ArticlePage = lazyRouteComponent(
  () => import("@/features/articles/article-pages"),
  "ArticlePage",
);
const DocumentListPage = lazyRouteComponent(
  () => import("@/features/documents/document-list-page"),
  "DocumentListPage",
);
const NewDocumentPage = lazyRouteComponent(
  () => import("@/features/documents/document-pages"),
  "NewDocumentPage",
);
const DocumentPage = lazyRouteComponent(
  () => import("@/features/documents/document-pages"),
  "DocumentPage",
);
const CustomerDocuments = lazyRouteComponent(
  () => import("@/features/documents/customer-documents"),
  "CustomerDocuments",
);

export interface RouterContext {
  readonly queryClient: QueryClient;
}

const rootRoute = createRootRouteWithContext<RouterContext>()({
  component: Outlet,
});

const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/login",
  validateSearch: (search: Record<string, unknown>) => ({
    redirect: safeRedirect(search["redirect"]),
  }),
  beforeLoad: async ({ context }) => {
    const status = await context.queryClient.query(setupStatusQuery);
    if (status.needs_setup) {
      throw redirect({ to: "/setup" });
    }
  },
  component: function LoginRoute() {
    const { redirect: target } = loginRoute.useSearch();
    return <LoginPage redirectTo={target} />;
  },
});

const setupRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/setup",
  beforeLoad: async ({ context }) => {
    const status = await context.queryClient.query(setupStatusQuery);
    if (!status.needs_setup) {
      throw redirect({ to: "/login", search: { redirect: "/" } });
    }
  },
  component: SetupPage,
});

/** The logged-in user, or a redirect to the login page. */
async function requireUser(queryClient: QueryClient, location: ParsedLocation) {
  try {
    return await queryClient.query(meQuery);
  } catch (error) {
    if (error instanceof ApiError && error.isUnauthorized) {
      throw redirect({ to: "/login", search: { redirect: location.href } });
    }
    throw error;
  }
}

const appRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: "app",
  beforeLoad: async ({ context, location }) => ({
    user: await requireUser(context.queryClient, location),
  }),
  component: function AppRoute() {
    const { user } = appRoute.useRouteContext();
    return <AppShell user={user} />;
  },
});

// First start: country and company, outside the app shell (there is nothing to navigate yet).
const welcomeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/welcome",
  beforeLoad: async ({ context, location }) => {
    await requireUser(context.queryClient, location);
    if ((await context.queryClient.query(companyQuery)) !== null) {
      throw redirect({ to: "/" });
    }
  },
  component: function WelcomeRoute() {
    const navigate = welcomeRoute.useNavigate();
    return (
      <CompanyWizard
        onDone={() => void navigate({ to: "/" })}
        onLater={() => {
          deferSetup();
          void navigate({ to: "/" });
        }}
      />
    );
  },
});

const dashboardRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/",
  beforeLoad: async ({ context }) => {
    if (!isSetupDeferred() && (await context.queryClient.query(companyQuery)) === null) {
      throw redirect({ to: "/welcome" });
    }
  },
  component: function DashboardRoute() {
    const { user } = dashboardRoute.useRouteContext();
    return <OverviewPage userName={user.display_name} />;
  },
});

function documentListRoute(kind: ListKind, path: "/invoices" | "/quotes") {
  const route = createRoute({
    getParentRoute: () => appRoute,
    path,
    // Optional in links; defaults are applied when reading.
    validateSearch: (search: Record<string, unknown>): Partial<DocumentListSearch> =>
      parseDocumentListSearch(search, kind),
    // Keep URLs short: default values are not written into the address bar.
    search: { middlewares: [stripSearchParams(DOCUMENT_LIST_DEFAULTS)] },
    component: function DocumentListRoute() {
      const search = parseDocumentListSearch(route.useSearch(), kind);
      const navigate = route.useNavigate();
      return (
        <DocumentListPage
          kind={kind}
          search={search}
          onSearchChange={(update: Partial<DocumentListSearch>) =>
            void navigate({ search: (previous) => ({ ...previous, ...update }), replace: true })
          }
        />
      );
    },
  });
  return route;
}

const invoicesRoute = documentListRoute("invoice", "/invoices");
const quotesRoute = documentListRoute("quote", "/quotes");

function newDocumentRoute(kind: ListKind, path: "/invoices/new" | "/quotes/new") {
  const route = createRoute({
    getParentRoute: () => appRoute,
    path,
    validateSearch: (search: Record<string, unknown>): { customer?: string } =>
      typeof search["customer"] === "string" ? { customer: search["customer"] } : {},
    component: function NewDocumentRoute() {
      const { customer } = route.useSearch();
      return <NewDocumentPage key={customer} type={kind} customerId={customer} />;
    },
  });
  return route;
}

const newInvoiceRoute = newDocumentRoute("invoice", "/invoices/new");
const newQuoteRoute = newDocumentRoute("quote", "/quotes/new");

const documentRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/documents/$documentId",
  component: function DocumentRoute() {
    const { documentId } = documentRoute.useParams();
    return <DocumentPage key={documentId} documentId={documentId} />;
  },
});

const customersRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/customers",
  // Optional in links; defaults are applied when reading.
  validateSearch: (
    search: Record<string, unknown>,
  ): Partial<ListSearch<(typeof CUSTOMER_SORTS)[number]>> =>
    parseListSearch(search, CUSTOMER_SORTS, "number"),
  // Keep URLs short: default values are not written into the address bar.
  search: { middlewares: [stripSearchParams(LIST_DEFAULTS)] },
  component: function CustomersRoute() {
    const search = parseListSearch(customersRoute.useSearch(), CUSTOMER_SORTS, "number");
    const navigate = customersRoute.useNavigate();
    return (
      <CustomerListPage
        search={search}
        onSearchChange={(update: Partial<ListSearch<(typeof CUSTOMER_SORTS)[number]>>) =>
          void navigate({ search: (previous) => ({ ...previous, ...update }), replace: true })
        }
      />
    );
  },
});

const dunningRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/dunning",
  component: DunningPage,
});

const recurringRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/recurring",
  component: RecurringListPage,
});

const newPlanRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/recurring/new",
  // ?from=<invoice id>: repeat that invoice.
  validateSearch: (search: Record<string, unknown>): { from?: string } =>
    typeof search["from"] === "string" ? { from: search["from"] } : {},
  component: function NewPlanRoute() {
    const { from } = newPlanRoute.useSearch();
    return <NewPlanPage key={from} fromDocument={from} />;
  },
});

const planRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/recurring/$planId",
  component: function PlanRoute() {
    const { planId } = planRoute.useParams();
    return <PlanPage key={planId} planId={planId} />;
  },
});

const customerImportRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/customers/import",
  component: function CustomerImportRoute() {
    return <ImportPage target="customers" />;
  },
});

const articleImportRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/articles/import",
  component: function ArticleImportRoute() {
    return <ImportPage target="articles" />;
  },
});

const newCustomerRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/customers/new",
  component: function NewCustomerRoute() {
    const company = useQuery(companyQuery);
    return <NewCustomerPage defaultCountry={company.data?.country ?? "CH"} />;
  },
});

const customerRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/customers/$customerId",
  component: function CustomerRoute() {
    const { customerId } = customerRoute.useParams();
    return (
      <CustomerPage
        customerId={customerId}
        documents={<CustomerDocuments customerId={customerId} />}
      />
    );
  },
});

const articlesRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/articles",
  // Optional in links; defaults are applied when reading.
  validateSearch: (
    search: Record<string, unknown>,
  ): Partial<ListSearch<(typeof ARTICLE_SORTS)[number]>> =>
    parseListSearch(search, ARTICLE_SORTS, "number"),
  // Keep URLs short: default values are not written into the address bar.
  search: { middlewares: [stripSearchParams(LIST_DEFAULTS)] },
  component: function ArticlesRoute() {
    const search = parseListSearch(articlesRoute.useSearch(), ARTICLE_SORTS, "number");
    const navigate = articlesRoute.useNavigate();
    return (
      <ArticleListPage
        search={search}
        onSearchChange={(update: Partial<ListSearch<(typeof ARTICLE_SORTS)[number]>>) =>
          void navigate({ search: (previous) => ({ ...previous, ...update }), replace: true })
        }
      />
    );
  },
});

const newArticleRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/articles/new",
  component: NewArticlePage,
});

const articleRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/articles/$articleId",
  component: function ArticleRoute() {
    const { articleId } = articleRoute.useParams();
    return <ArticlePage articleId={articleId} />;
  },
});

const settingsRoute = createRoute({
  getParentRoute: () => appRoute,
  path: "/settings",
  validateSearch: (search: Record<string, unknown>): { tab?: SettingsTab } => ({
    tab: SETTINGS_TABS.find((tab) => tab === search["tab"]) ?? "company",
  }),
  search: { middlewares: [stripSearchParams({ tab: "company" })] },
  component: function SettingsRoute() {
    const { user } = settingsRoute.useRouteContext();
    const { tab = "company" } = settingsRoute.useSearch();
    const navigate = settingsRoute.useNavigate();
    return (
      <SettingsPage
        user={user}
        tab={tab}
        onTabChange={(next) => void navigate({ search: { tab: next }, replace: true })}
      />
    );
  },
});

const routeTree = rootRoute.addChildren([
  loginRoute,
  setupRoute,
  welcomeRoute,
  appRoute.addChildren([
    dashboardRoute,
    invoicesRoute,
    newInvoiceRoute,
    quotesRoute,
    newQuoteRoute,
    documentRoute,
    dunningRoute,
    recurringRoute,
    newPlanRoute,
    planRoute,
    customersRoute,
    customerImportRoute,
    newCustomerRoute,
    customerRoute,
    articlesRoute,
    articleImportRoute,
    newArticleRoute,
    articleRoute,
    settingsRoute,
  ]),
]);

export function createAppRouter(queryClient: QueryClient) {
  return createRouter({
    routeTree,
    context: { queryClient },
    defaultPreload: "intent",
    defaultErrorComponent: ErrorPage,
    scrollRestoration: true,
  });
}

declare module "@tanstack/react-router" {
  interface Register {
    router: ReturnType<typeof createAppRouter>;
  }
}
