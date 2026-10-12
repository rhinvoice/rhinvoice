import { ChevronLeftIcon, ChevronRightIcon } from "lucide-react";

import { useI18n } from "@/components/i18n/use-i18n";
import { Button } from "@/components/ui/button";

interface PaginationProps {
  readonly offset: number;
  readonly limit: number;
  readonly total: number;
  readonly onChange: (offset: number) => void;
}

export function Pagination({ offset, limit, total, onChange }: PaginationProps) {
  const { t } = useI18n();
  if (total <= limit) {
    return null;
  }
  const from = offset + 1;
  const to = Math.min(offset + limit, total);
  return (
    <nav
      aria-label={t("common.pageInfo", { from, to, total })}
      className="flex items-center justify-end gap-2"
    >
      <span className="text-sm text-muted-foreground tabular-nums" aria-live="polite">
        {t("common.pageInfo", { from, to, total })}
      </span>
      <Button
        variant="outline"
        size="icon-sm"
        disabled={offset === 0}
        onClick={() => {
          onChange(Math.max(0, offset - limit));
        }}
        aria-label={t("common.previous")}
      >
        <ChevronLeftIcon aria-hidden="true" />
      </Button>
      <Button
        variant="outline"
        size="icon-sm"
        disabled={to >= total}
        onClick={() => {
          onChange(offset + limit);
        }}
        aria-label={t("common.next")}
      >
        <ChevronRightIcon aria-hidden="true" />
      </Button>
    </nav>
  );
}
