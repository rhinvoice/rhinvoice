import { useI18n } from "@/components/i18n/use-i18n";
import { Button } from "@/components/ui/button";
import { modifierLabel } from "@/lib/shortcuts";
import { useUnsavedChanges } from "@/features/shared/use-unsaved-changes";

interface FormFooterProps {
  readonly saving: boolean;
  readonly dirty: boolean;
  readonly label?: string;
}

/**
 * Save bar. Sticky on desktop; on phones it sits at the end of the form so that
 * it never covers fields together with the bottom tab bar (WCAG 2.4.11, 2.5.8).
 */
export function FormFooter({ saving, dirty, label }: FormFooterProps) {
  const { t } = useI18n();
  // Closing the program for an update asks about these changes first (ADR 0031).
  useUnsavedChanges(dirty);
  return (
    <div className="z-10 -mx-4 flex items-center justify-end gap-3 border-t bg-background/95 px-4 py-3 backdrop-blur md:sticky md:bottom-0 md:-mx-8 md:px-8">
      <p className="text-sm text-muted-foreground" aria-live="polite">
        {saving ? t("common.saving") : dirty ? t("common.unsavedChanges") : ""}
      </p>
      <Button type="submit" disabled={saving}>
        {label ?? t("common.save")}
        <span className="sr-only">{` (${modifierLabel(navigator.platform)} Enter)`}</span>
      </Button>
    </div>
  );
}
