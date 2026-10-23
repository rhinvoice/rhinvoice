import { Fragment } from "react";

import { useI18n } from "@/components/i18n/use-i18n";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Kbd } from "@/components/ui/kbd";
import type { MessageKey } from "@/lib/i18n";
import { modifierLabel } from "@/lib/shortcuts";

interface ShortcutRow {
  readonly keys: readonly string[];
  readonly label: MessageKey;
  readonly sequence?: boolean;
  /** A second key that does the same. */
  readonly alternative?: string;
}

export function ShortcutsDialog({
  open,
  onOpenChange,
}: {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
}) {
  const { t } = useI18n();
  const mod = modifierLabel(navigator.platform);
  const groups: readonly [MessageKey, readonly ShortcutRow[]][] = [
    [
      "shortcuts.groupGeneral",
      [
        { keys: [mod, "K"], label: "shortcuts.palette" },
        { keys: ["/"], label: "shortcuts.search" },
        { keys: ["I"], label: "shortcuts.newInvoice", alternative: "N" },
        { keys: ["Q"], label: "shortcuts.newQuote" },
        { keys: ["C"], label: "shortcuts.newCustomer" },
        { keys: ["A"], label: "shortcuts.newArticle" },
        { keys: [mod, "↵"], label: "shortcuts.save" },
        { keys: [mod, "Z"], label: "shortcuts.undo" },
        { keys: ["P"], label: "shortcuts.payment" },
        { keys: ["Alt", "↑"], label: "shortcuts.moveLineUp" },
        { keys: ["Alt", "↓"], label: "shortcuts.moveLineDown" },
        { keys: ["?"], label: "shortcuts.help" },
        { keys: ["Esc"], label: "shortcuts.close" },
      ],
    ],
    [
      "shortcuts.groupNavigation",
      [
        { keys: ["G", "D"], label: "shortcuts.goDashboard", sequence: true },
        { keys: ["G", "I"], label: "shortcuts.goInvoices", sequence: true },
        { keys: ["G", "Q"], label: "shortcuts.goQuotes", sequence: true },
        { keys: ["G", "C"], label: "shortcuts.goCustomers", sequence: true },
        { keys: ["G", "A"], label: "shortcuts.goArticles", sequence: true },
        { keys: ["G", "S"], label: "shortcuts.goSettings", sequence: true },
      ],
    ],
  ];
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent closeLabel={t("common.close")}>
        <DialogHeader>
          <DialogTitle>{t("shortcuts.title")}</DialogTitle>
          <DialogDescription>{t("shortcuts.description")}</DialogDescription>
        </DialogHeader>
        {groups.map(([group, rows]) => (
          <section key={group} className="flex flex-col gap-2">
            <h3 className="text-xs font-medium text-muted-foreground">{t(group)}</h3>
            <dl className="flex flex-col gap-1">
              {rows.map((row) => (
                <div key={row.label} className="flex min-h-8 items-center justify-between gap-4">
                  <dt className="text-sm">{t(row.label)}</dt>
                  <dd className="flex items-center gap-1">
                    {row.keys.map((key, index) => (
                      <Fragment key={key}>
                        {index > 0 && row.sequence === true ? (
                          <span className="text-xs text-muted-foreground">
                            {t("shortcuts.then")}
                          </span>
                        ) : null}
                        <Kbd>{key}</Kbd>
                      </Fragment>
                    ))}
                    {row.alternative === undefined ? null : (
                      <>
                        <span className="text-xs text-muted-foreground">{t("shortcuts.or")}</span>
                        <Kbd>{row.alternative}</Kbd>
                      </>
                    )}
                  </dd>
                </div>
              ))}
            </dl>
          </section>
        ))}
      </DialogContent>
    </Dialog>
  );
}
