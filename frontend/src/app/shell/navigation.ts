import {
  FileTextIcon,
  LayoutDashboardIcon,
  PackageIcon,
  ReceiptIcon,
  SettingsIcon,
  UsersIcon,
  type LucideIcon,
} from "lucide-react";

import type { MessageKey } from "@/lib/i18n";

export interface NavItem {
  readonly to: "/" | "/invoices" | "/quotes" | "/customers" | "/articles" | "/settings";
  readonly label: MessageKey;
  readonly icon: LucideIcon;
  /** Second key of the "G then X" navigation shortcut. */
  readonly goKey: string;
  /** Earlier second keys that keep working, unlisted. */
  readonly goAliases?: readonly string[];
}

export const PRIMARY_NAV: readonly NavItem[] = [
  { to: "/", label: "nav.dashboard", icon: LayoutDashboardIcon, goKey: "d" },
  { to: "/invoices", label: "nav.invoices", icon: ReceiptIcon, goKey: "i" },
  { to: "/quotes", label: "nav.quotes", icon: FileTextIcon, goKey: "q", goAliases: ["o"] },
  { to: "/customers", label: "nav.customers", icon: UsersIcon, goKey: "c" },
  { to: "/articles", label: "nav.articles", icon: PackageIcon, goKey: "a" },
];

export const SECONDARY_NAV: readonly NavItem[] = [
  { to: "/settings", label: "nav.settings", icon: SettingsIcon, goKey: "s" },
];

export const ALL_NAV: readonly NavItem[] = [...PRIMARY_NAV, ...SECONDARY_NAV];
