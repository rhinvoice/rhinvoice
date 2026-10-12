import { useNavigate } from "@tanstack/react-router";
import {
  BellRingIcon,
  FilePlusIcon,
  KeyboardIcon,
  MoonIcon,
  PackagePlusIcon,
  PlusIcon,
  RepeatIcon,
  UploadIcon,
  UserPlusIcon,
} from "lucide-react";

import { ALL_NAV } from "@/app/shell/navigation";
import { useI18n } from "@/components/i18n/use-i18n";
import { useTheme } from "@/components/theme/use-theme";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandShortcut,
} from "@/components/ui/command";
import { Kbd } from "@/components/ui/kbd";

interface CommandPaletteProps {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  readonly onShowShortcuts: () => void;
}

export function CommandPalette({ open, onOpenChange, onShowShortcuts }: CommandPaletteProps) {
  const { t } = useI18n();
  const navigate = useNavigate();
  const { theme, setPreference } = useTheme();

  const run = (action: () => void) => {
    onOpenChange(false);
    action();
  };

  return (
    <CommandDialog
      open={open}
      onOpenChange={onOpenChange}
      title={t("palette.title")}
      description={t("palette.placeholder")}
      label={t("palette.title")}
    >
      <CommandInput placeholder={t("palette.placeholder")} />
      <CommandList>
        <CommandEmpty>{t("palette.empty")}</CommandEmpty>
        <CommandGroup heading={t("palette.actions")}>
          <CommandItem
            onSelect={() => {
              run(() => void navigate({ to: "/invoices/new" }));
            }}
          >
            <PlusIcon aria-hidden="true" />
            {t("nav.newInvoice")}
            <CommandShortcut>
              <Kbd>N</Kbd>
            </CommandShortcut>
          </CommandItem>
          <CommandItem
            onSelect={() => {
              run(() => void navigate({ to: "/quotes/new" }));
            }}
          >
            <FilePlusIcon aria-hidden="true" />
            {t("documents.newQuote")}
            <CommandShortcut>
              <Kbd>Q</Kbd>
            </CommandShortcut>
          </CommandItem>
          <CommandItem
            onSelect={() => {
              run(() => void navigate({ to: "/customers/new" }));
            }}
          >
            <UserPlusIcon aria-hidden="true" />
            {t("customers.new")}
          </CommandItem>
          <CommandItem
            onSelect={() => {
              run(() => void navigate({ to: "/articles/new" }));
            }}
          >
            <PackagePlusIcon aria-hidden="true" />
            {t("articles.new")}
          </CommandItem>
          <CommandItem
            onSelect={() => {
              run(() => void navigate({ to: "/dunning" }));
            }}
          >
            <BellRingIcon aria-hidden="true" />
            {t("dunning.title")}
          </CommandItem>
          <CommandItem
            onSelect={() => {
              run(() => void navigate({ to: "/recurring" }));
            }}
          >
            <RepeatIcon aria-hidden="true" />
            {t("recurring.title")}
          </CommandItem>
          <CommandItem
            onSelect={() => {
              run(() => void navigate({ to: "/customers/import" }));
            }}
          >
            <UploadIcon aria-hidden="true" />
            {t("import.title.customers")}
          </CommandItem>
          <CommandItem
            onSelect={() => {
              run(() => void navigate({ to: "/articles/import" }));
            }}
          >
            <UploadIcon aria-hidden="true" />
            {t("import.title.articles")}
          </CommandItem>
          <CommandItem
            onSelect={() => {
              run(() => {
                setPreference(theme === "dark" ? "light" : "dark");
              });
            }}
          >
            <MoonIcon aria-hidden="true" />
            {t("palette.toggleTheme")}
          </CommandItem>
          <CommandItem
            onSelect={() => {
              run(onShowShortcuts);
            }}
          >
            <KeyboardIcon aria-hidden="true" />
            {t("palette.shortcuts")}
            <CommandShortcut>
              <Kbd>?</Kbd>
            </CommandShortcut>
          </CommandItem>
        </CommandGroup>
        <CommandGroup heading={t("palette.navigation")}>
          {ALL_NAV.map((item) => (
            <CommandItem
              key={item.to}
              onSelect={() => {
                run(() => void navigate({ to: item.to }));
              }}
            >
              <item.icon aria-hidden="true" />
              {t(item.label)}
              <CommandShortcut>
                <Kbd>G</Kbd>
                <Kbd>{item.goKey.toUpperCase()}</Kbd>
              </CommandShortcut>
            </CommandItem>
          ))}
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
