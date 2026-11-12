import { useState } from "react";

import { useI18n } from "@/components/i18n/use-i18n";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { useSubmitOnce } from "@/components/use-run-once";
import { FormAlert } from "@/features/shared/form-alert";
import { useErrorMessage } from "@/features/shared/use-error-message";
import { ApiError } from "@/lib/api-error";

const MAX_LAYOUT_NAME = 60;

interface LayoutNameDialogProps {
  readonly title: string;
  readonly description?: string;
  readonly initial: string;
  readonly submitLabel: string;
  /** Saves the name; a refused one (taken) keeps the dialog open with the reason. */
  readonly onSubmit: (name: string) => Promise<void>;
  readonly onClose: () => void;
}

/** Name a new print layout or rename one (#48). */
export function LayoutNameDialog({
  title,
  description,
  initial,
  submitLabel,
  onSubmit,
  onClose,
}: LayoutNameDialogProps) {
  const { t } = useI18n();
  const errorMessage = useErrorMessage();
  const [name, setName] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const once = useSubmitOnce(async () => {
    if (name.trim() === "") {
      setError(t("validation.required"));
      return;
    }
    try {
      await onSubmit(name.trim());
      // Closing unmounts the dialog, so the lock needs no release.
      onClose();
    } catch (caught) {
      const field = caught instanceof ApiError ? caught.details["name"] : undefined;
      if (field === undefined) setFailure(errorMessage(caught));
      else setError(errorMessage(caught));
    }
  });

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent closeLabel={t("common.close")}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description === undefined ? null : <DialogDescription>{description}</DialogDescription>}
        </DialogHeader>
        <form className="flex flex-col gap-4" onSubmit={once.submit} noValidate>
          <FormAlert message={failure} />
          <Field label={t("printLayout.name")} error={error ?? undefined}>
            <Input
              id="print-layout-name"
              value={name}
              maxLength={MAX_LAYOUT_NAME}
              autoComplete="off"
              onChange={(event) => {
                setName(event.target.value);
                setError(null);
              }}
            />
          </Field>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" busy={once.busy}>
              {submitLabel}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
