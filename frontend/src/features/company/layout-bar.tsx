import { EllipsisIcon, FileDownIcon, PencilIcon, PlusIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { useI18n } from "@/components/i18n/use-i18n";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Field } from "@/components/ui/field";
import { NativeSelect } from "@/components/ui/native-select";
import {
  fetchSamplePdf,
  useCreatePrintLayout,
  useDeletePrintLayout,
  useMakeDefaultPrintLayout,
  useSavePrintLayout,
} from "@/features/company/api";
import { LayoutNameDialog } from "@/features/company/layout-name-dialog";
import type { NamedLayout, PrintLayout } from "@/features/shared/company-api";
import { saveFile } from "@/features/shared/file-download";
import { useErrorMessage } from "@/features/shared/use-error-message";

interface LayoutBarProps {
  readonly named: NamedLayout;
  readonly layouts: readonly NamedLayout[];
  /** The settings as edited, for the sample PDF. */
  readonly layout: PrintLayout;
  /** Unsaved changes: another layout is chosen after saving or resetting. */
  readonly dirty: boolean;
  readonly onSelect: (id: string) => void;
}

/** Choose, add, rename and delete print layouts, one of them the default (#48, variant 4A). */
export function LayoutBar({ named, layouts, layout, dirty, onSelect }: LayoutBarProps) {
  const { t } = useI18n();
  const errorMessage = useErrorMessage();
  const create = useCreatePrintLayout();
  const save = useSavePrintLayout();
  const makeDefault = useMakeDefaultPrintLayout();
  const remove = useDeletePrintLayout();
  const [dialog, setDialog] = useState<"new" | "rename" | "delete" | null>(null);
  const defaultLayout = layouts.find((other) => other.is_default);

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-start gap-x-3 gap-y-2">
        <Field
          className="w-full max-w-md min-w-56 flex-1 sm:w-auto"
          label={t("printLayout.choose")}
          description={
            dirty
              ? t("printLayout.switchFirst")
              : named.is_default
                ? t("printLayout.defaultHint")
                : t("printLayout.otherHint")
          }
        >
          <NativeSelect
            id="print-layout-choice"
            value={named.id}
            disabled={dirty}
            onChange={(event) => {
              onSelect(event.target.value);
            }}
          >
            {layouts.map((other) => (
              <option key={other.id} value={other.id}>
                {other.is_default ? t("printLayout.nameDefault", { name: other.name }) : other.name}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <div className="flex flex-wrap items-center gap-2 sm:pt-7">
          {named.is_default ? <Badge>{t("printLayout.isDefault")}</Badge> : null}
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={dirty}
            onClick={() => {
              setDialog("new");
            }}
          >
            <PlusIcon aria-hidden="true" />
            {t("printLayout.new")}
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => {
              setDialog("rename");
            }}
          >
            <PencilIcon aria-hidden="true" />
            {t("printLayout.rename")}
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() =>
              fetchSamplePdf(layout, t("printLayout.sampleName", { name: named.name })).then(
                saveFile,
                (caught: unknown) => {
                  toast.error(errorMessage(caught));
                },
              )
            }
          >
            <FileDownIcon aria-hidden="true" />
            {t("printLayout.sample")}
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                type="button"
                variant="outline"
                size="icon-sm"
                aria-label={t("printLayout.more")}
                disabled={named.is_default}
              >
                <EllipsisIcon aria-hidden="true" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem
                disabled={dirty}
                onSelect={() => {
                  makeDefault.mutate(named.id, {
                    onSuccess: () =>
                      toast.success(t("printLayout.madeDefault", { name: named.name })),
                    onError: (caught) => toast.error(errorMessage(caught)),
                  });
                }}
              >
                {t("printLayout.makeDefault")}
              </DropdownMenuItem>
              <DropdownMenuItem
                className="text-destructive"
                onSelect={() => {
                  setDialog("delete");
                }}
              >
                {t("printLayout.delete")}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      {dialog === "new" ? (
        <LayoutNameDialog
          title={t("printLayout.newTitle")}
          description={t("printLayout.newHint", { name: named.name })}
          initial=""
          submitLabel={t("printLayout.create")}
          onSubmit={async (name) => {
            const created = await create.mutateAsync({ name, copy_of: named.id });
            toast.success(t("printLayout.created"));
            onSelect(created.id);
          }}
          onClose={() => {
            setDialog(null);
          }}
        />
      ) : null}
      {dialog === "rename" ? (
        <LayoutNameDialog
          title={t("printLayout.renameTitle")}
          initial={named.name}
          submitLabel={t("common.save")}
          onSubmit={async (name) => {
            // The name only: settings being edited stay unsaved.
            await save.mutateAsync({ id: named.id, name, layout: named.layout });
            toast.success(t("printLayout.renamed"));
          }}
          onClose={() => {
            setDialog(null);
          }}
        />
      ) : null}
      <AlertDialog
        open={dialog === "delete"}
        onOpenChange={(open) => {
          if (!open) setDialog(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t("printLayout.deleteTitle", { name: named.name })}
            </AlertDialogTitle>
            <AlertDialogDescription>{t("printLayout.deleteDescription")}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              destructive
              onClick={() =>
                remove.mutateAsync(named.id).then(
                  () => {
                    toast.success(t("printLayout.deleted"));
                    if (defaultLayout !== undefined) onSelect(defaultLayout.id);
                  },
                  (caught: unknown) => {
                    toast.error(errorMessage(caught));
                  },
                )
              }
            >
              {t("common.delete")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
