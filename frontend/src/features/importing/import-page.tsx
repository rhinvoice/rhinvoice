import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import {
  DownloadIcon,
  FileSpreadsheetIcon,
  FilesIcon,
  FolderOpenIcon,
  MonitorDownIcon,
  UploadIcon,
  XIcon,
} from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { toast } from "sonner";

import { ExternalLink } from "@/components/external-link";
import { useI18n } from "@/components/i18n/use-i18n";
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
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
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
import { NativeSelect } from "@/components/ui/native-select";
import { PageHeader } from "@/components/ui/page-header";
import { RadioCard } from "@/components/ui/radio-cards";
import { StatusBadge, type DocumentStatusTone } from "@/components/ui/status-badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useDocumentTitle } from "@/components/use-document-title";
import {
  runImport,
  templatesQuery,
  useDeleteTemplate,
  useSaveTemplate,
  type DuplicateStrategy,
} from "@/features/importing/api";
import {
  MAX_UPLOAD_FILES,
  fieldLabelKey,
  fieldOfColumn,
  filterRows,
  importableCount,
  invoiceFiles,
  uploadProblem,
  mappingFromTemplate,
  problemKey,
  reportCsv,
  templateColumns,
  withColumn,
  type ImportRow,
  type ImportRun,
  type ImportTarget,
  type Mapping,
  type RowFilter,
  type RowStatus,
} from "@/features/importing/import-model";
import { demoQuery } from "@/features/shared/demo-api";
import { FormAlert } from "@/features/shared/form-alert";
import { useErrorMessage } from "@/features/shared/use-error-message";
import { IMPORT_GUIDE_URL, INSTALL_URL } from "@/lib/about";
import { cn } from "@/lib/cn";
import { formatBytes, formatMoney, formatNumber } from "@/lib/format";
import type { Locale } from "@/lib/locale";

/** More rows would slow the page down; the CSV report holds all of them. */
const SHOWN_ROWS = 500;
const ACCEPT =
  ".csv,.txt,.xlsx,.xls,text/csv,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

const TONES: Readonly<Record<RowStatus, DocumentStatusTone>> = {
  new: "paid",
  updated: "sent",
  skipped: "draft",
  error: "overdue",
};

interface ChosenFile {
  readonly file: File;
  /** Changes with every choice, also when the same file is chosen again. */
  readonly key: number;
}

interface ChosenPdfs {
  readonly files: readonly File[];
  readonly key: number;
}

const LIST_PATHS = {
  customers: "/customers",
  articles: "/articles",
  invoices: "/invoices",
} as const;

export function ImportPage({ target }: { readonly target: ImportTarget }) {
  const { t } = useI18n();
  useDocumentTitle(t("app.pageTitle", { title: t(`import.title.${target}`) }));
  // The public demo takes no files: everything it stored, every visitor could open.
  const demo = useQuery(demoQuery).data?.enabled === true;
  return demo ? <ImportInDemo target={target} /> : <ImportForm target={target} />;
}

function ImportInDemo({ target }: { readonly target: ImportTarget }) {
  const { t } = useI18n();
  return (
    <>
      <PageHeader title={t(`import.title.${target}`)} />
      <Card className="max-w-2xl">
        <div className="flex items-start gap-4">
          <MonitorDownIcon className="size-8 shrink-0 text-muted-foreground" aria-hidden="true" />
          <div className="flex flex-col gap-2">
            <h2 className="text-sm font-medium">{t("import.demo.title")}</h2>
            <p className="text-sm text-muted-foreground">{t("import.demo.text")}</p>
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
              <ExternalLink href={INSTALL_URL} className="min-h-6 text-primary">
                {t("import.demo.install")}
              </ExternalLink>
              <ExternalLink href={IMPORT_GUIDE_URL} className="min-h-6 text-primary">
                {t("import.demo.guide")}
              </ExternalLink>
            </div>
          </div>
        </div>
      </Card>
    </>
  );
}

function ImportForm({ target }: { readonly target: ImportTarget }) {
  const { t } = useI18n();
  const errorMessage = useErrorMessage();
  const client = useQueryClient();
  const [chosen, setChosen] = useState<ChosenFile | null>(null);
  const [duplicates, setDuplicates] = useState<DuplicateStrategy>("skip");
  const [mapping, setMapping] = useState<Mapping | null>(null);
  const [templateId, setTemplateId] = useState("");
  const [done, setDone] = useState<ImportRun | null>(null);
  const [pdfs, setPdfs] = useState<ChosenPdfs | null>(null);
  const files = pdfs?.files ?? [];
  const tooMuch = uploadProblem(files);

  const preview = useQuery({
    queryKey: ["import-preview", target, chosen?.key, duplicates, mapping, pdfs?.key],
    queryFn: ({ signal }) => {
      if (chosen === null) throw new Error("no file chosen");
      return runImport(target, { file: chosen.file, duplicates, mapping, files }, false, signal);
    },
    enabled: chosen !== null && done === null && tooMuch === null,
    retry: false,
    gcTime: 0,
    // While a new mapping is checked the last result stays; a new file starts empty.
    placeholderData: (previous, previousQuery) =>
      previousQuery?.queryKey[2] === chosen?.key ? previous : undefined,
  });
  const importing = useMutation({
    mutationFn: () => {
      if (chosen === null) throw new Error("no file chosen");
      return runImport(target, { file: chosen.file, duplicates, mapping, files }, true);
    },
    onSuccess: (run) => {
      setDone(run);
      toast.success(t(`import.done.${target}`, { count: importableCount(run) }));
      void client.invalidateQueries({ queryKey: [target] });
      if (target === "invoices") {
        // New invoices, customers and a moved number sequence.
        void client.invalidateQueries({ queryKey: ["documents"] });
        void client.invalidateQueries({ queryKey: ["customers"] });
        void client.invalidateQueries({ queryKey: ["dashboard"] });
        void client.invalidateQueries({ queryKey: ["numbering"] });
      }
    },
    onError: (caught) => toast.error(errorMessage(caught) ?? t("error.generic")),
  });

  const choose = (file: File | undefined) => {
    setChosen(file === undefined ? null : { file, key: Date.now() });
    setMapping(null);
    setTemplateId("");
    setDone(null);
    if (file === undefined) setPdfs(null);
  };
  const choosePdfs = (chosenFiles: readonly File[] | null) => {
    setPdfs(chosenFiles === null ? null : { files: chosenFiles, key: Date.now() });
    // The files may tell another column of the numbers.
    setMapping(null);
    setTemplateId("");
  };
  const run = chosen === null ? undefined : preview.data;
  const count = run === undefined ? 0 : importableCount(run);
  const summaryOf = (result: ImportRun) =>
    result.missing.length > 0
      ? t("import.missingColumns", { columns: missingText(result.missing) })
      : t("import.summary", { ...result.counts });
  const missingText = (missing: ImportRun["missing"]) =>
    missing
      .map((group) =>
        group
          .map((field) => {
            const key = fieldLabelKey(field);
            return key === null ? field : t(key);
          })
          .join(t("import.or")),
      )
      .join(", ");
  // One live region, always there: screen readers announce each new result.
  const announcement = done === null ? (run === undefined ? "" : summaryOf(run)) : summaryOf(done);

  return (
    <>
      <PageHeader
        title={t(`import.title.${target}`)}
        description={
          target === "invoices" ? t("import.descriptionInvoices") : t("import.description")
        }
        actions={
          run === undefined || done !== null ? undefined : (
            <Button
              disabled={
                count === 0 || preview.isFetching || importing.isPending || tooMuch !== null
              }
              onClick={() => {
                importing.mutate();
              }}
            >
              <UploadIcon aria-hidden="true" />
              {t(`import.run.${target}`, { count })}
            </Button>
          )
        }
      />
      <p className="sr-only" role="status">
        {announcement}
      </p>
      <div className="flex flex-col gap-6">
        {done !== null ? (
          <ImportDone
            run={done}
            target={target}
            onAgain={() => {
              choose(undefined);
            }}
          />
        ) : (
          <>
            <FilePicker target={target} chosen={chosen} run={run} onChoose={choose} />
            {target === "invoices" ? (
              <PdfPicker files={files} disabled={importing.isPending} onChoose={choosePdfs} />
            ) : null}
            <FormAlert
              message={
                tooMuch === null
                  ? null
                  : tooMuch === "tooMany"
                    ? t("import.pdfs.tooMany", { max: MAX_UPLOAD_FILES })
                    : t("import.pdfs.tooLarge")
              }
            />
            <FormAlert message={preview.isError ? errorMessage(preview.error) : null} />
            {run === undefined || run.missing.length === 0 ? null : (
              <FormAlert message={summaryOf(run)} />
            )}
            {run === undefined || chosen === null ? null : (
              // While importing nothing may change what is imported.
              <fieldset disabled={importing.isPending} className="contents">
                <ImportSettings
                  target={target}
                  run={run}
                  mapping={mapping ?? run.mapping}
                  duplicates={duplicates}
                  templateId={templateId}
                  onDuplicates={setDuplicates}
                  onTemplate={(id, templateMapping) => {
                    setTemplateId(id);
                    setMapping(templateMapping);
                  }}
                  onMapping={(next) => {
                    setTemplateId("");
                    setMapping(next);
                  }}
                />
                {run.missing.length > 0 ? null : (
                  <ImportResult
                    // A new file, mapping or choice starts with the fitting row filter.
                    key={`${String(chosen.key)}-${JSON.stringify(mapping)}-${duplicates}-${String(pdfs?.key)}`}
                    run={run}
                    target={target}
                    busy={preview.isFetching}
                    summary={summaryOf(run)}
                  />
                )}
              </fieldset>
            )}
          </>
        )}
      </div>
    </>
  );
}

function FilePicker({
  target,
  chosen,
  run,
  onChoose,
}: {
  readonly target: ImportTarget;
  readonly chosen: ChosenFile | null;
  readonly run: ImportRun | undefined;
  readonly onChoose: (file: File | undefined) => void;
}) {
  const { t, locale } = useI18n();
  const inputId = useId();
  const details =
    run === undefined
      ? null
      : [
          t("import.rows", { count: run.rows.length }),
          run.file_type === "csv"
            ? [
                run.encoding,
                run.delimiter === null
                  ? null
                  : `«${run.delimiter === "\t" ? "Tab" : run.delimiter}»`,
              ]
                .filter((part) => part !== null)
                .join(" · ")
            : run.file_type.toUpperCase(),
        ].join(" · ");
  return (
    <Card>
      <div className="flex flex-wrap items-center gap-4">
        <FileSpreadsheetIcon className="size-8 text-muted-foreground" aria-hidden="true" />
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <p className="text-sm font-medium break-all">
            {chosen === null ? t(`import.choose.${target}`) : chosen.file.name}
          </p>
          <p id={`${inputId}-details`} className="text-sm text-muted-foreground">
            {details ?? t("import.formats", { rows: formatNumber("10000", locale, 0) })}
          </p>
        </div>
        {/* The browser's own file button cannot be translated or styled; the label is the button. */}
        <label
          className={cn(
            buttonVariants({ variant: chosen === null ? "default" : "outline" }),
            "cursor-pointer has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring has-[:focus-visible]:ring-offset-2 has-[:focus-visible]:ring-offset-background",
          )}
        >
          <UploadIcon aria-hidden="true" />
          {chosen === null ? t("import.chooseFile") : t("import.otherFile")}
          <input
            id={inputId}
            type="file"
            accept={ACCEPT}
            className="sr-only"
            aria-describedby={`${inputId}-details`}
            onChange={(event) => {
              onChoose(event.target.files?.[0]);
              // Choosing the same file again must count as a new choice.
              event.target.value = "";
            }}
          />
        </label>
      </div>
    </Card>
  );
}

interface ImportSettingsProps {
  readonly target: ImportTarget;
  readonly run: ImportRun;
  readonly mapping: Mapping;
  readonly duplicates: DuplicateStrategy;
  readonly templateId: string;
  readonly onDuplicates: (value: DuplicateStrategy) => void;
  readonly onTemplate: (id: string, mapping: Mapping | null) => void;
  readonly onMapping: (mapping: Mapping) => void;
}

function ImportSettings({
  target,
  run,
  mapping,
  duplicates,
  templateId,
  onDuplicates,
  onTemplate,
  onMapping,
}: ImportSettingsProps) {
  const { t } = useI18n();
  const templates = useQuery(templatesQuery(target)).data ?? [];
  const removeTemplate = useDeleteTemplate(target);
  const [saving, setSaving] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const selected = templates.find((template) => template.id === templateId);
  const mapped = Object.keys(mapping).length;
  // Opened when columns are missing, and kept open while the person maps them: closing
  // as soon as the last required column is chosen would hide the next select.
  const [mappingOpen, setMappingOpen] = useState(run.missing.length > 0);
  if (run.missing.length > 0 && !mappingOpen) setMappingOpen(true);
  return (
    <Card aria-labelledby="import-settings-title">
      <CardHeader>
        <CardTitle id="import-settings-title">{t("import.settings")}</CardTitle>
      </CardHeader>
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="flex flex-col gap-2">
          <Field label={t("import.template")} description={t("import.templateHint")}>
            <NativeSelect
              value={templateId}
              onChange={(event) => {
                const template = templates.find((item) => item.id === event.target.value);
                onTemplate(
                  event.target.value,
                  template === undefined ? null : mappingFromTemplate(template, run.headers),
                );
              }}
            >
              <option value="">{t("import.templateAuto")}</option>
              {templates.map((template) => (
                <option key={template.id} value={template.id}>
                  {template.name}
                </option>
              ))}
            </NativeSelect>
          </Field>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setSaving(true);
              }}
            >
              {t("import.saveTemplate")}
            </Button>
            {selected === undefined ? null : (
              <Button
                variant="ghost"
                size="sm"
                disabled={removeTemplate.isPending}
                onClick={() => {
                  setConfirming(true);
                }}
              >
                {t("import.deleteTemplate", { name: selected.name })}
              </Button>
            )}
            <AlertDialog open={confirming && selected !== undefined} onOpenChange={setConfirming}>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>{t("import.deleteTemplateTitle")}</AlertDialogTitle>
                  <AlertDialogDescription>
                    {t("import.deleteTemplateDescription", { name: selected?.name ?? "" })}
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
                  <AlertDialogAction
                    onClick={() => {
                      if (selected === undefined) return;
                      removeTemplate.mutate(selected, {
                        onSuccess: () => {
                          onTemplate("", null);
                          toast.success(t("import.templateDeleted"));
                        },
                      });
                    }}
                  >
                    {t("common.delete")}
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        </div>
        {target === "invoices" ? (
          <p className="text-sm text-muted-foreground">{t("import.skippedInvoices")}</p>
        ) : (
          <fieldset className="flex flex-col gap-1.5">
            <legend className="mb-1.5 text-sm font-medium">{t("import.duplicates")}</legend>
            <div className="grid gap-2 sm:grid-cols-3">
              {(["skip", "update", "create"] as const).map((value) => (
                <RadioCard
                  key={value}
                  id={`duplicates-${value}`}
                  name="duplicates"
                  value={value}
                  checked={duplicates === value}
                  label={t(`import.duplicates.${value}`)}
                  onChange={() => {
                    onDuplicates(value);
                  }}
                />
              ))}
            </div>
            <p className="text-sm text-muted-foreground">{t(`import.duplicatesHint.${target}`)}</p>
          </fieldset>
        )}
      </div>
      <details
        className="group rounded-lg border border-border/70"
        open={mappingOpen}
        onToggle={(event) => {
          setMappingOpen(event.currentTarget.open);
        }}
      >
        <summary className="flex min-h-11 cursor-pointer items-center px-4 text-sm font-medium">
          {t("import.mapping", { mapped, total: run.headers.length })}
        </summary>
        <div className="flex flex-col gap-3 border-t border-border/70 p-4">
          <p className="text-sm text-muted-foreground">{t(`import.required.${target}`)}</p>
          <Table scrollLabel={t("import.mappingCaption")}>
            <caption className="sr-only">{t("import.mappingCaption")}</caption>
            <TableHeader>
              <TableRow>
                <TableHead>{t("import.column")}</TableHead>
                <TableHead>{t("import.example")}</TableHead>
                <TableHead>{t("import.becomes")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {run.headers.map((header, column) => (
                <TableRow key={`${String(column)}-${header}`}>
                  <TableCell className="font-medium">
                    {header || t("import.unnamedColumn", { number: column + 1 })}
                  </TableCell>
                  <TableCell className="max-w-64 truncate text-muted-foreground">
                    {run.sample[0]?.[column] ?? ""}
                  </TableCell>
                  <TableCell className="min-w-56">
                    <NativeSelect
                      aria-label={t("import.fieldFor", {
                        column: header || t("import.unnamedColumn", { number: column + 1 }),
                      })}
                      value={fieldOfColumn(mapping, column) ?? ""}
                      onChange={(event) => {
                        onMapping(withColumn(mapping, column, event.target.value || null));
                      }}
                    >
                      <option value="">{t("import.skipColumn")}</option>
                      {run.fields.map((field) => {
                        const key = fieldLabelKey(field.key);
                        return (
                          <option key={field.key} value={field.key}>
                            {key === null ? field.key : t(key)}
                          </option>
                        );
                      })}
                    </NativeSelect>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </details>
      <SaveTemplateDialog
        target={target}
        open={saving}
        columns={templateColumns(mapping, run.headers)}
        onClose={(id) => {
          setSaving(false);
          if (id !== undefined) onTemplate(id, mapping);
        }}
      />
    </Card>
  );
}

function SaveTemplateDialog({
  target,
  open,
  columns,
  onClose,
}: {
  readonly target: ImportTarget;
  readonly open: boolean;
  readonly columns: Record<string, string>;
  readonly onClose: (savedId?: string) => void;
}) {
  const { t } = useI18n();
  const errorMessage = useErrorMessage();
  const save = useSaveTemplate(target);
  const [name, setName] = useState("");
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
    >
      <DialogContent>
        <form
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            save.mutate(
              { name: name.trim(), columns },
              {
                onSuccess: (template) => {
                  toast.success(t("import.templateSaved"));
                  setName("");
                  onClose(template.id);
                },
              },
            );
          }}
        >
          <DialogHeader>
            <DialogTitle>{t("import.saveTemplate")}</DialogTitle>
            <DialogDescription>{t("import.saveTemplateHint")}</DialogDescription>
          </DialogHeader>
          <Field
            label={t("import.templateName")}
            error={save.isError ? (errorMessage(save.error) ?? undefined) : undefined}
          >
            <Input
              value={name}
              maxLength={60}
              required
              onChange={(event) => {
                setName(event.target.value);
              }}
            />
          </Field>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                onClose();
              }}
            >
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={save.isPending || !name.trim()}>
              {t("common.save")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function ImportResult({
  run,
  target,
  busy,
  summary,
}: {
  readonly run: ImportRun;
  readonly target: ImportTarget;
  readonly busy: boolean;
  readonly summary: string;
}) {
  const { t } = useI18n();
  const [filter, setFilter] = useState<RowFilter>(run.counts.error > 0 ? "error" : "all");
  const rows = filterRows(run.rows, filter);
  const describe = useRowText(target);
  const filters: readonly (readonly [RowFilter, string, number])[] = [
    ["all", t("import.filter.all"), run.rows.length],
    ["new", t("import.status.new"), run.counts.new],
    ["updated", t("import.status.updated"), run.counts.updated],
    ["skipped", t("import.status.skipped"), run.counts.skipped],
    ["error", t("import.status.error"), run.counts.error],
  ];
  return (
    <Card aria-labelledby="import-result-title" aria-busy={busy}>
      <CardHeader>
        <CardTitle id="import-result-title">{t("import.result")}</CardTitle>
        <CardDescription>{summary}</CardDescription>
      </CardHeader>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div
          role="group"
          aria-label={t("import.filter.label")}
          className="inline-flex flex-wrap gap-0.5 rounded-lg bg-muted p-1"
        >
          {filters.map(([value, label, count]) => (
            <Button
              key={value}
              size="sm"
              variant="ghost"
              aria-pressed={filter === value}
              className={cn(filter === value && "bg-card shadow-xs hover:bg-card")}
              onClick={() => {
                setFilter(value);
              }}
            >
              {label} ({count})
            </Button>
          ))}
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            const csv = reportCsv(run.rows, describe.headers, describe.cells);
            const link = document.createElement("a");
            link.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
            link.download = t(`import.reportFile.${target}`);
            link.click();
            // Revoking at once can cancel the download in some browsers.
            window.setTimeout(() => {
              URL.revokeObjectURL(link.href);
            }, 1000);
          }}
        >
          <DownloadIcon aria-hidden="true" />
          {t("import.report")}
        </Button>
      </div>
      {rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("import.noRows")}</p>
      ) : (
        <Table scrollLabel={t("import.resultRows")}>
          <caption className="sr-only">{t("import.result")}</caption>
          <TableHeader>
            <TableRow>
              {describe.headers.map((header) => (
                <TableHead key={header}>{header}</TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.slice(0, SHOWN_ROWS).map((row) => (
              <ResultRow key={row.row} row={row} cells={describe.cells(row)} />
            ))}
          </TableBody>
        </Table>
      )}
      {rows.length > SHOWN_ROWS ? (
        <p className="text-sm text-muted-foreground">
          {t("import.moreRows", { shown: SHOWN_ROWS, total: rows.length })}
        </p>
      ) : null}
      <p className="text-sm text-muted-foreground">{t("import.errorsLeftOut")}</p>
      {target === "invoices" ? <InvoiceNotes run={run} /> : null}
    </Card>
  );
}

/** Files without an invoice, and the number the next invoice gets. */
function InvoiceNotes({ run }: { readonly run: ImportRun }) {
  const { t } = useI18n();
  return (
    <>
      {run.unused_files.length === 0 ? null : (
        <details className="rounded-lg border border-border/70">
          <summary className="flex min-h-11 cursor-pointer items-center px-4 text-sm font-medium">
            {t("import.unused", { count: run.unused_files.length })}
          </summary>
          <div className="flex flex-col gap-2 border-t border-border/70 p-4 text-sm">
            <p className="text-muted-foreground">{t("import.unusedHint")}</p>
            <ul className="flex flex-col gap-1 break-all">
              {run.unused_files.slice(0, SHOWN_ROWS).map((path) => (
                <li key={path}>{path}</li>
              ))}
            </ul>
          </div>
        </details>
      )}
      {run.next_number === null ? null : (
        <p className="text-sm text-muted-foreground">
          {t("import.nextNumber", { number: run.next_number })}
        </p>
      )}
    </>
  );
}

/** The PDF files of the invoices: a whole folder, or single PDF and ZIP files. */
function PdfPicker({
  files,
  disabled,
  onChoose,
}: {
  readonly files: readonly File[];
  readonly disabled: boolean;
  readonly onChoose: (files: readonly File[] | null) => void;
}) {
  const { t, locale } = useI18n();
  const id = useId();
  const folder = useRef<HTMLInputElement>(null);
  useEffect(() => {
    // Not in React's types: the attribute that lets the browser pick a folder.
    folder.current?.setAttribute("webkitdirectory", "");
  }, []);
  const bytes = files.reduce((sum, file) => sum + file.size, 0);
  const pick = (list: FileList | null) => {
    onChoose(invoiceFiles(list ?? []));
  };
  const labelClass = cn(
    buttonVariants({ variant: "outline" }),
    "cursor-pointer has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring has-[:focus-visible]:ring-offset-2 has-[:focus-visible]:ring-offset-background",
    disabled && "pointer-events-none opacity-50",
  );
  return (
    <Card aria-labelledby={`${id}-title`}>
      <div className="flex flex-wrap items-center gap-4">
        <FilesIcon className="size-8 text-muted-foreground" aria-hidden="true" />
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <h2 id={`${id}-title`} className="text-sm font-medium">
            {t("import.pdfs.title")}
          </h2>
          <p id={`${id}-state`} className="text-sm text-muted-foreground">
            {files.length === 0 && bytes === 0
              ? t("import.pdfs.none")
              : t("import.pdfs.chosen", { count: files.length, size: formatBytes(bytes, locale) })}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <label className={labelClass}>
            <FolderOpenIcon aria-hidden="true" />
            {t("import.pdfs.folder")}
            <input
              ref={folder}
              type="file"
              multiple
              className="sr-only"
              disabled={disabled}
              aria-describedby={`${id}-state`}
              onChange={(event) => {
                pick(event.target.files);
                event.target.value = "";
              }}
            />
          </label>
          <label className={labelClass}>
            <FilesIcon aria-hidden="true" />
            {t("import.pdfs.files")}
            <input
              type="file"
              multiple
              accept=".pdf,.zip,application/pdf,application/zip"
              className="sr-only"
              disabled={disabled}
              aria-describedby={`${id}-state`}
              onChange={(event) => {
                pick(event.target.files);
                event.target.value = "";
              }}
            />
          </label>
          {files.length === 0 ? null : (
            <Button
              variant="ghost"
              size="icon"
              disabled={disabled}
              aria-label={t("import.pdfs.clear")}
              onClick={() => {
                onChoose(null);
              }}
            >
              <XIcon aria-hidden="true" />
            </Button>
          )}
        </div>
      </div>
      <p className="text-sm text-muted-foreground">{t("import.pdfs.description")}</p>
    </Card>
  );
}

function ResultRow({ row, cells }: { readonly row: ImportRow; readonly cells: readonly string[] }) {
  const { t } = useI18n();
  const [line, , number, name, detail, ...rest] = cells;
  const problem = rest.at(-1);
  return (
    <TableRow>
      <TableCell className="tabular-nums">{line}</TableCell>
      <TableCell>
        <StatusBadge tone={TONES[row.status]} label={t(`import.status.${row.status}`)} />
      </TableCell>
      <TableCell className="whitespace-nowrap tabular-nums">{number}</TableCell>
      <TableCell>{name}</TableCell>
      <TableCell className="whitespace-nowrap tabular-nums">{detail}</TableCell>
      {rest.length > 1 ? (
        <TableCell className="max-w-72">
          <PdfCell row={row} />
        </TableCell>
      ) : null}
      <TableCell className={row.problem === null ? undefined : "text-status-overdue-fg"}>
        {problem}
      </TableCell>
    </TableRow>
  );
}

/** The PDF of an invoice row: its name, below it the folder and the attachments. */
function PdfCell({ row }: { readonly row: ImportRow }) {
  const { t } = useI18n();
  if (row.status !== "new") return null;
  if (row.file === null) {
    return <span className="text-muted-foreground">{t("import.noPdf")}</span>;
  }
  const slash = row.file.lastIndexOf("/");
  const folder = slash < 0 ? "" : row.file.slice(0, slash);
  const details = [
    folder,
    row.attachments === 0 ? "" : t("import.attachments", { count: row.attachments }),
  ].filter((part) => part !== "");
  return (
    <>
      <span className="block break-words">{row.file.slice(slash + 1)}</span>
      {details.length === 0 ? null : (
        <span className="block text-xs break-words text-muted-foreground">
          {details.join(" · ")}
        </span>
      )}
    </>
  );
}

/** Column headers and cell texts of the result, shared by the table and the CSV report. */
function useRowText(target: ImportTarget) {
  const { t, locale } = useI18n();
  const invoices = target === "invoices";
  return {
    headers: [
      t("import.row"),
      t("import.statusTitle"),
      t("import.number"),
      invoices ? t("import.customer") : t("import.name"),
      t(`import.detail.${target}`),
      ...(invoices ? [t("import.pdf")] : []),
      t("import.problemTitle"),
    ],
    cells: (row: ImportRow): readonly string[] => {
      const problem = row.problem;
      let text = "";
      if (problem !== null) {
        const field = fieldLabelKey(problem.field);
        const reason = problemKey(problem.code);
        const values = {
          field: field === null ? problem.field : t(field),
          reason: reason === null ? problem.message : t(reason),
          value: problem.value,
        };
        text = problem.value ? t("import.problemValue", values) : t("import.problemText", values);
      } else if (row.new_customer) {
        text = t("import.newCustomer");
      }
      if (!invoices) {
        return [
          String(row.row),
          t(`import.status.${row.status}`),
          row.number,
          row.name,
          row.detail,
          text,
        ];
      }
      const pdf =
        row.status !== "new"
          ? ""
          : [
              row.file ?? t("import.noPdf"),
              row.attachments === 0 ? "" : t("import.attachments", { count: row.attachments }),
            ]
              .filter((part) => part !== "")
              .join(" ");
      return [
        String(row.row),
        t(`import.status.${row.status}`),
        row.number,
        row.name,
        amountText(row.detail, locale),
        pdf,
        text,
      ];
    },
  };
}

function ImportDone({
  run,
  target,
  onAgain,
}: {
  readonly run: ImportRun;
  readonly target: ImportTarget;
  readonly onAgain: () => void;
}) {
  const { t } = useI18n();
  const title = useRef<HTMLHeadingElement>(null);
  // The button that started the import is gone: focus moves to the result.
  useEffect(() => {
    title.current?.focus();
  }, []);
  return (
    <Card aria-labelledby="import-done-title">
      <CardHeader>
        <CardTitle id="import-done-title" ref={title} tabIndex={-1} className="outline-none">
          {t("import.doneTitle")}
        </CardTitle>
        <CardDescription>
          {t("import.summary", {
            new: run.counts.new,
            updated: run.counts.updated,
            skipped: run.counts.skipped,
            error: run.counts.error,
          })}
        </CardDescription>
      </CardHeader>
      {run.next_number === null ? null : (
        <p className="text-sm">{t("import.nextNumber", { number: run.next_number })}</p>
      )}
      <div className="flex flex-wrap gap-2">
        <Button asChild>
          <Link to={LIST_PATHS[target]}>{t(`import.show.${target}`)}</Link>
        </Button>
        <Button variant="outline" onClick={onAgain}>
          {t("import.again")}
        </Button>
      </div>
    </Card>
  );
}

/** "CHF 1296.00" from the server, written in the page's language ("CHF 1'296.00"). */
function amountText(detail: string, locale: Locale): string {
  const match = /^([A-Z]{3}) (-?\d+(?:\.\d+)?)$/.exec(detail);
  if (match === null) return detail;
  const [, currency = "", amount = ""] = match;
  return formatMoney(amount, currency, locale);
}
