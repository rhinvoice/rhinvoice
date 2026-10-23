import { Link, Outlet, useNavigate, useRouterState } from "@tanstack/react-router";
import {
  CircleHelpIcon,
  InfoIcon,
  LogOutIcon,
  MenuIcon,
  PanelLeftCloseIcon,
  PanelLeftOpenIcon,
  PlusIcon,
  SearchIcon,
  UserIcon,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { EditorSheetsProvider } from "@/app/editor-sheets";
import { AboutDialog } from "@/app/shell/about-dialog";
import { CommandPalette } from "@/app/shell/command-palette";
import { DemoBanner } from "@/app/shell/demo-banner";
import { ALL_NAV, PRIMARY_NAV, SECONDARY_NAV, type NavItem } from "@/app/shell/navigation";
import { ShortcutsDialog } from "@/app/shell/shortcuts-dialog";
import { ThemeToggle } from "@/app/shell/theme-toggle";
import { useGlobalShortcuts } from "@/app/shell/use-global-shortcuts";
import { usePreloadedPages } from "@/app/shell/use-preloaded-pages";
import { LanguageToggle } from "@/components/i18n/language-toggle";
import { useI18n } from "@/components/i18n/use-i18n";
import { useSingleKeyShortcuts } from "@/components/use-single-key-shortcuts";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Kbd } from "@/components/ui/kbd";
import { Tooltip } from "@/components/ui/tooltip";
import { useLogout, type User } from "@/features/auth/api";
import { companyQuery } from "@/features/company/api";
import { undoRegistry } from "@/features/shared/undo";
import { UpdateCard } from "@/features/updates/update-notice";
import { APP_VERSION, MAKER } from "@/lib/about";
import { cn } from "@/lib/cn";
import { modifierLabel } from "@/lib/shortcuts";
import { applyAccentHue } from "@/lib/theme";
import { readStorage, writeStorage } from "@/lib/storage";

const SIDEBAR_STORAGE_KEY = "rhinvoice.sidebar";

function isActive(pathname: string, item: NavItem): boolean {
  return item.to === "/" ? pathname === "/" : pathname.startsWith(item.to);
}

function NavLinks({
  items,
  collapsed,
  onNavigate,
}: {
  readonly items: readonly NavItem[];
  readonly collapsed: boolean;
  readonly onNavigate?: () => void;
}) {
  const { t } = useI18n();
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  return (
    <ul className="flex flex-col gap-0.5">
      {items.map((item) => {
        const active = isActive(pathname, item);
        const link = (
          <Link
            to={item.to}
            {...(onNavigate === undefined ? {} : { onClick: onNavigate })}
            aria-current={active ? "page" : undefined}
            aria-label={collapsed ? t(item.label) : undefined}
            className={cn(
              "flex min-h-9 items-center gap-2.5 rounded-md px-2.5 text-sm font-medium transition-colors duration-150",
              active
                ? "bg-accent text-accent-foreground"
                : "text-muted-foreground hover:bg-muted hover:text-foreground",
              collapsed && "justify-center px-0",
            )}
          >
            <item.icon className="size-4 shrink-0" aria-hidden="true" />
            {collapsed ? null : <span>{t(item.label)}</span>}
          </Link>
        );
        return (
          <li key={item.to}>
            {collapsed ? (
              <Tooltip content={t(item.label)} side="right">
                {link}
              </Tooltip>
            ) : (
              link
            )}
          </li>
        );
      })}
    </ul>
  );
}

/** The version and the maker, quiet at the foot of the navigation; opens "About". */
function AboutLine({ onOpen }: { readonly onOpen: () => void }) {
  const { t } = useI18n();
  return (
    <button
      type="button"
      onClick={onOpen}
      className="rounded-md px-2 py-1.5 text-left text-xs text-muted-foreground tabular-nums transition-colors hover:text-foreground"
    >
      <span className="sr-only">{t("about.title")}: </span>
      <span data-app-version>v{APP_VERSION}</span> · {t("about.byMaker", { maker: MAKER })}
    </button>
  );
}

function Brand({ collapsed }: { readonly collapsed: boolean }) {
  return (
    <Link
      to="/"
      className={cn("flex h-9 items-center gap-2 rounded-md px-1.5", collapsed && "justify-center")}
    >
      <img src="/favicon.svg" alt="" className="size-6" />
      {collapsed ? (
        <span className="sr-only">Rhinvoice</span>
      ) : (
        <span className="font-semibold tracking-tight">Rhinvoice</span>
      )}
    </Link>
  );
}

export function AppShell({ user }: { readonly user: User }) {
  const { t } = useI18n();
  const navigate = useNavigate();
  const logout = useLogout();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [aboutOpen, setAboutOpen] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(
    () => readStorage(SIDEBAR_STORAGE_KEY) === "collapsed",
  );
  const mod = modifierLabel(navigator.platform);
  const [singleKeys] = useSingleKeyShortcuts();
  const company = useQuery(companyQuery);
  usePreloadedPages();
  const accentHue = company.data?.accent_hue;
  useEffect(() => {
    if (accentHue !== undefined) applyAccentHue(document.documentElement, accentHue);
  }, [accentHue]);

  const newInvoice = () => void navigate({ to: "/invoices/new" });

  useGlobalShortcuts(
    {
      openPalette: () => {
        setPaletteOpen(true);
      },
      openHelp: () => {
        setHelpOpen(true);
      },
      newInvoice,
      newQuote: () => void navigate({ to: "/quotes/new" }),
      undo: () => undoRegistry.trigger(),
      focusSearch: () => {
        const search = document.querySelector<HTMLElement>("[data-page-search]");
        if (search === null) {
          setPaletteOpen(true);
        } else {
          search.focus();
        }
      },
      goTo: (key) => {
        const item = ALL_NAV.find((candidate) => candidate.goKey === key);
        if (item === undefined) return false;
        void navigate({ to: item.to });
        return true;
      },
    },
    { singleKeys },
  );

  const toggleSidebar = () => {
    setCollapsed((value) => {
      writeStorage(SIDEBAR_STORAGE_KEY, value ? "expanded" : "collapsed");
      return !value;
    });
  };

  const onLogout = () => {
    logout.mutate(undefined, {
      onSettled: () => void navigate({ to: "/login", search: { redirect: "/" } }),
    });
  };

  return (
    <div className="flex min-h-dvh">
      <a
        href="#main"
        className="fixed top-2 left-2 z-[60] -translate-y-24 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-md transition-transform duration-150 focus:translate-y-0"
      >
        {t("app.skipToContent")}
      </a>

      <aside
        className={cn(
          "sticky top-0 hidden h-dvh shrink-0 flex-col gap-4 border-r bg-background p-3 transition-[width] duration-200 md:flex",
          collapsed ? "w-16" : "w-60",
        )}
      >
        <Brand collapsed={collapsed} />
        <Button
          onClick={newInvoice}
          className={cn("w-full", collapsed && "px-0")}
          aria-label={collapsed ? t("nav.newInvoice") : undefined}
        >
          <PlusIcon aria-hidden="true" />
          {collapsed ? null : (
            <>
              <span>{t("nav.newInvoice")}</span>
              <Kbd className="ml-auto border-transparent bg-primary-foreground/15 text-primary-foreground">
                N
              </Kbd>
            </>
          )}
        </Button>
        <nav aria-label={t("nav.main")} className="flex flex-1 flex-col justify-between">
          <NavLinks items={PRIMARY_NAV} collapsed={collapsed} />
          <div className="flex flex-col gap-2">
            <NavLinks items={SECONDARY_NAV} collapsed={collapsed} />
            <Button
              variant="ghost"
              size="sm"
              onClick={toggleSidebar}
              className={cn("justify-start text-muted-foreground", collapsed && "justify-center")}
              aria-label={collapsed ? t("nav.expand") : t("nav.collapse")}
              aria-expanded={!collapsed}
            >
              {collapsed ? (
                <PanelLeftOpenIcon aria-hidden="true" />
              ) : (
                <PanelLeftCloseIcon aria-hidden="true" />
              )}
              {collapsed ? null : <span>{t("nav.collapse")}</span>}
            </Button>
            {collapsed ? null : (
              <>
                <UpdateCard />
                <AboutLine
                  onOpen={() => {
                    setAboutOpen(true);
                  }}
                />
              </>
            )}
          </div>
        </nav>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <DemoBanner />
        <header className="sticky top-0 z-40 flex h-14 items-center gap-2 border-b bg-background/90 px-4 backdrop-blur md:px-6">
          <Button
            variant="ghost"
            size="icon-sm"
            className="md:hidden"
            onClick={() => {
              setMobileNavOpen(true);
            }}
            aria-label={t("nav.openMenu")}
          >
            <MenuIcon aria-hidden="true" />
          </Button>
          <button
            type="button"
            onClick={() => {
              setPaletteOpen(true);
            }}
            className="flex h-10 w-full max-w-sm items-center gap-2 rounded-md bg-field px-3 text-sm text-muted-foreground transition-colors hover:bg-field-hover"
          >
            <SearchIcon className="size-4" aria-hidden="true" />
            <span className="flex-1 text-left">{t("topbar.search")}</span>
            <span className="hidden gap-1 sm:flex" aria-hidden="true">
              <Kbd>{mod}</Kbd>
              <Kbd>K</Kbd>
            </span>
          </button>
          <div className="ml-auto flex items-center gap-1">
            <LanguageToggle />
            <ThemeToggle />
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => {
                setHelpOpen(true);
              }}
              aria-label={t("topbar.help")}
            >
              <CircleHelpIcon aria-hidden="true" />
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon-sm" aria-label={t("topbar.account")}>
                  <UserIcon aria-hidden="true" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="min-w-56">
                <DropdownMenuLabel className="flex flex-col gap-0.5 text-foreground">
                  <span className="text-sm font-medium">{user.display_name}</span>
                  <span className="text-xs font-normal text-muted-foreground">{user.email}</span>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem asChild>
                  <Link to="/settings">{t("nav.settings")}</Link>
                </DropdownMenuItem>
                <DropdownMenuItem
                  onSelect={() => {
                    setAboutOpen(true);
                  }}
                >
                  <InfoIcon aria-hidden="true" />
                  {t("about.title")}
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={onLogout}>
                  <LogOutIcon aria-hidden="true" />
                  {t("topbar.logout")}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </header>

        <main
          id="main"
          tabIndex={-1}
          className="flex-1 px-4 py-6 pb-24 outline-none md:px-8 md:pb-8"
        >
          <div className="mx-auto flex w-full max-w-[1440px] flex-col gap-6">
            <EditorSheetsProvider>
              <Outlet />
            </EditorSheetsProvider>
          </div>
        </main>

        <nav
          aria-label={t("nav.main")}
          className="fixed inset-x-0 bottom-0 z-40 flex h-16 items-stretch border-t bg-background/95 backdrop-blur md:hidden"
        >
          {PRIMARY_NAV.slice(0, 4).map((item) => (
            <MobileTab key={item.to} item={item} />
          ))}
        </nav>
      </div>

      <Dialog open={mobileNavOpen} onOpenChange={setMobileNavOpen}>
        <DialogContent side="left" closeLabel={t("common.close")}>
          <DialogTitle className="sr-only">{t("nav.main")}</DialogTitle>
          <Brand collapsed={false} />
          <nav aria-label={t("nav.main")} className="flex flex-col gap-4">
            <NavLinks
              items={[...PRIMARY_NAV, ...SECONDARY_NAV]}
              collapsed={false}
              onNavigate={() => {
                setMobileNavOpen(false);
              }}
            />
          </nav>
          <div className="mt-auto flex flex-col">
            <UpdateCard />
            <AboutLine
              onOpen={() => {
                setMobileNavOpen(false);
                setAboutOpen(true);
              }}
            />
          </div>
        </DialogContent>
      </Dialog>

      <CommandPalette
        open={paletteOpen}
        onOpenChange={setPaletteOpen}
        onShowShortcuts={() => {
          setHelpOpen(true);
        }}
      />
      <ShortcutsDialog open={helpOpen} onOpenChange={setHelpOpen} />
      <AboutDialog open={aboutOpen} onOpenChange={setAboutOpen} />
    </div>
  );
}

function MobileTab({ item }: { readonly item: NavItem }) {
  const { t } = useI18n();
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const active = isActive(pathname, item);
  return (
    <Link
      to={item.to}
      aria-current={active ? "page" : undefined}
      className={cn(
        "flex flex-1 flex-col items-center justify-center gap-1 text-xs font-medium",
        active ? "text-primary" : "text-muted-foreground",
      )}
    >
      <item.icon className="size-5" aria-hidden="true" />
      {t(item.label)}
    </Link>
  );
}
