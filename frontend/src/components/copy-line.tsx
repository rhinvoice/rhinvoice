import { CheckIcon, CopyIcon } from "lucide-react";
import { useState } from "react";

import { useI18n } from "@/components/i18n/use-i18n";
import { Button } from "@/components/ui/button";

/** A command or setting to paste elsewhere, with a copy button. */
export function CopyLine({ text }: { readonly text: string }) {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);
  return (
    <div className="flex items-start gap-1">
      <code className="min-w-0 flex-1 rounded-md border bg-background px-2 py-1 font-mono text-xs break-words">
        {text}
      </code>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="size-7 shrink-0"
        aria-label={copied ? t("common.copied") : t("common.copy")}
        onClick={() => {
          navigator.clipboard.writeText(text).then(
            () => {
              setCopied(true);
              window.setTimeout(() => {
                setCopied(false);
              }, 2_000);
            },
            () => {
              // Refused (e.g. plain http on another computer): the text can still be selected.
            },
          );
        }}
      >
        {copied ? <CheckIcon aria-hidden="true" /> : <CopyIcon aria-hidden="true" />}
      </Button>
    </div>
  );
}
