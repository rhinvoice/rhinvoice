import { useQuery } from "@tanstack/react-query";
import {
  ArrowDownIcon,
  ArrowUpIcon,
  PencilIcon,
  PlusIcon,
  RotateCcwIcon,
  Trash2Icon,
} from "lucide-react";
import { useState, type SyntheticEvent } from "react";
import { toast } from "sonner";

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
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { FormAlert } from "@/features/shared/form-alert";
import { DOCUMENT_LANGUAGES } from "@/features/shared/document-languages";
import { useErrorMessage } from "@/features/shared/use-error-message";
import {
  legalNoticesQuery,
  textTemplatesQuery,
  useDeleteTextTemplate,
  useMoveTextTemplate,
  useSaveLegalNotice,
  useSaveTextTemplate,
  type Language,
  type LegalNotice,
  type TextKind,
  type TextTemplate,
} from "@/features/texts/api";
import { ApiError } from "@/lib/api-error";
import { errorMessageKey } from "@/lib/i18n";
import { cn } from "@/lib/cn";

type DocumentType = "invoice" | "quote";
const KINDS: readonly TextKind[] = ["intro", "payment", "closing"];
const PLACEHOLDERS = [
  "nummer",
  "datum",
  "faellig",
  "kunde",
  "betrag",
  "waehrung",
  "firma",
] as const;
const MAX_NAME = 70;
const MAX_TEXT = 2000;
const MAX_NOTICE = 500;

interface Editing {
  readonly kind: TextKind;
  readonly template: TextTemplate | null;
}

/** Settings → Texts: ready-made texts for new documents and the legal notices. */
export function TextsSettings() {
  const { t } = useI18n();
  const [type, setType] = useState<DocumentType>("invoice");
  const [language, setLanguage] = useState<Language>("de");
  const templates = useQuery(textTemplatesQuery);
  const [editing, setEditing] = useState<Editing | null>(null);
  const [deleting, setDeleting] = useState<TextTemplate | null>(null);
  const move = useMoveTextTemplate();
  const remove = useDeleteTextTemplate();
  const errorMessage = useErrorMessage();
  const fail = (caught: unknown) => {
    toast.error(errorMessage(caught) ?? t("error.generic"), { duration: Infinity });
  };

  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <p className="text-sm text-muted-foreground">{t("texts.intro")}</p>
      <div className="flex flex-wrap gap-3">
        <Segmented
          label={t("texts.documentType")}
          value={type}
          options={[
            ["invoice", t("documentType.invoice")],
            ["quote", t("documentType.quote")],
          ]}
          onChange={setType}
        />
        <Segmented
          label={t("documents.language")}
          value={language}
          options={DOCUMENT_LANGUAGES.map((option) => [option, t(`language.${option}`)])}
          onChange={setLanguage}
        />
      </div>

      {templates.isPending ? (
        <Skeleton className="h-64 w-full" />
      ) : (
        KINDS.map((kind) => {
          const list = (templates.data ?? [])
            .filter(
              (template) =>
                template.kind === kind &&
                template.document_type === type &&
                template.language === language,
            )
            .sort((a, b) => a.position - b.position);
          return (
            <Card key={kind} aria-labelledby={`texts-${kind}`}>
              <CardHeader className="flex-row items-start justify-between gap-3">
                <div className="flex flex-col gap-1">
                  <CardTitle id={`texts-${kind}`} className="text-base">
                    {t(`texts.kind.${kind}`)}
                  </CardTitle>
                  <CardDescription>{t(`texts.kindHint.${kind}`)}</CardDescription>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    setEditing({ kind, template: null });
                  }}
                >
                  <PlusIcon aria-hidden="true" />
                  {t("texts.add")} <span className="sr-only">{t(`texts.kind.${kind}`)}</span>
                </Button>
              </CardHeader>
              {list.length === 0 ? (
                <p className="text-sm text-muted-foreground">{t("texts.empty")}</p>
              ) : (
                <ul className="flex flex-col divide-y">
                  {list.map((template, index) => (
                    <li key={template.id} className="flex items-start gap-3 py-3">
                      <div className="flex min-w-0 flex-1 flex-col gap-1">
                        <span className="flex flex-wrap items-center gap-2 font-medium">
                          {template.name}
                          {template.is_default ? (
                            <Badge variant="info">{t("texts.default")}</Badge>
                          ) : null}
                        </span>
                        <span className="text-sm break-words whitespace-pre-line text-muted-foreground">
                          {template.text}
                        </span>
                      </div>
                      <div className="flex shrink-0 gap-0.5">
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          disabled={index === 0 || move.isPending}
                          aria-label={t("texts.moveUp", { name: template.name })}
                          onClick={() => {
                            move.mutate({ id: template.id, up: true }, { onError: fail });
                          }}
                        >
                          <ArrowUpIcon aria-hidden="true" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          disabled={index === list.length - 1 || move.isPending}
                          aria-label={t("texts.moveDown", { name: template.name })}
                          onClick={() => {
                            move.mutate({ id: template.id, up: false }, { onError: fail });
                          }}
                        >
                          <ArrowDownIcon aria-hidden="true" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          aria-label={t("texts.edit", { name: template.name })}
                          onClick={() => {
                            setEditing({ kind, template });
                          }}
                        >
                          <PencilIcon aria-hidden="true" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          aria-label={t("texts.delete", { name: template.name })}
                          onClick={() => {
                            setDeleting(template);
                          }}
                        >
                          <Trash2Icon aria-hidden="true" />
                        </Button>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          );
        })
      )}

      <NoticesCard language={language} />

      {editing === null ? null : (
        <TemplateDialog
          key={editing.template?.id ?? `new-${editing.kind}`}
          editing={editing}
          type={type}
          language={language}
          onClose={() => {
            setEditing(null);
          }}
        />
      )}

      <AlertDialog
        open={deleting !== null}
        onOpenChange={(open) => {
          if (!open) setDeleting(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("texts.deleteTitle")}</AlertDialogTitle>
            <AlertDialogDescription>
              {t("texts.deleteDescription", { name: deleting?.name ?? "" })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("common.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (deleting === null) return;
                remove.mutate(deleting.id, {
                  onSuccess: () => toast.success(t("texts.deleted")),
                  onError: fail,
                });
              }}
            >
              {t("common.delete")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

interface SegmentedProps<V extends string> {
  readonly label: string;
  readonly value: V;
  readonly options: readonly (readonly [V, string])[];
  readonly onChange: (value: V) => void;
}

function Segmented<V extends string>({ label, value, options, onChange }: SegmentedProps<V>) {
  return (
    <div role="group" aria-label={label} className="inline-flex gap-0.5 rounded-lg bg-muted p-1">
      {options.map(([option, text]) => (
        <Button
          key={option}
          size="sm"
          variant="ghost"
          aria-pressed={value === option}
          className={cn(value === option && "bg-card shadow-xs hover:bg-card")}
          onClick={() => {
            onChange(option);
          }}
        >
          {text}
        </Button>
      ))}
    </div>
  );
}

interface TemplateDialogProps {
  readonly editing: Editing;
  readonly type: DocumentType;
  readonly language: Language;
  readonly onClose: () => void;
}

function TemplateDialog({ editing, type, language, onClose }: TemplateDialogProps) {
  const { t } = useI18n();
  const save = useSaveTextTemplate();
  const errorMessage = useErrorMessage();
  const existing = editing.template;
  const [name, setName] = useState(existing?.name ?? "");
  const [text, setText] = useState(existing?.text ?? "");
  const [isDefault, setIsDefault] = useState(existing?.is_default ?? false);
  const [errors, setErrors] = useState<{ name?: string; text?: string; root?: string }>({});

  const submit = (event: SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault();
    const found: { name?: string; text?: string } = {};
    if (name.trim() === "") found.name = t("validation.required");
    if (text.trim() === "") found.text = t("validation.required");
    setErrors(found);
    if (found.name !== undefined || found.text !== undefined) return;
    save.mutate(
      {
        id: existing?.id ?? null,
        body: {
          kind: editing.kind,
          document_type: existing?.document_type ?? type,
          language: existing?.language ?? language,
          name: name.trim(),
          text,
          is_default: isDefault,
        },
      },
      {
        onSuccess: () => {
          toast.success(t("common.saved"));
          onClose();
        },
        onError: (caught) => {
          // Unknown placeholders and other rules of the server belong to the text.
          if (caught instanceof ApiError && caught.status === 422 && "text" in caught.details) {
            const key = errorMessageKey(caught.code);
            setErrors({ text: key === "error.generic" ? (errorMessage(caught) ?? "") : t(key) });
            return;
          }
          setErrors({ root: errorMessage(caught) ?? t("error.generic") });
        },
      },
    );
  };

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent>
        <form className="flex flex-col gap-4" onSubmit={submit} noValidate>
          <DialogHeader>
            <DialogTitle>
              {existing === null ? t("texts.addTitle") : t("texts.editTitle")}:{" "}
              {t(`texts.kind.${editing.kind}`)}
            </DialogTitle>
          </DialogHeader>
          <FormAlert message={errors.root ?? null} />
          <Field label={t("texts.name")} description={t("texts.nameHint")} error={errors.name}>
            <Input
              id="text-template-name"
              value={name}
              maxLength={MAX_NAME}
              onChange={(event) => {
                setName(event.target.value);
              }}
            />
          </Field>
          <Field label={t("texts.text")} error={errors.text}>
            <Textarea
              id="text-template-text"
              rows={4}
              value={text}
              maxLength={MAX_TEXT}
              onChange={(event) => {
                setText(event.target.value);
              }}
            />
          </Field>
          <div className="flex flex-col gap-1.5">
            <span className="text-sm font-medium" id="text-template-placeholders">
              {t("texts.placeholders")}
            </span>
            <div
              role="group"
              aria-labelledby="text-template-placeholders"
              className="flex flex-wrap gap-1.5"
            >
              {PLACEHOLDERS.map((placeholder) => (
                <Button
                  key={placeholder}
                  type="button"
                  size="sm"
                  variant="outline"
                  className="rounded-full font-mono text-xs"
                  aria-label={t("texts.insertPlaceholder", {
                    placeholder: t(`texts.placeholder.${placeholder}`),
                  })}
                  onClick={() => {
                    setText((current) => `${current}{${placeholder}}`);
                  }}
                >
                  {`{${placeholder}}`}
                </Button>
              ))}
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Switch id="text-template-default" checked={isDefault} onCheckedChange={setIsDefault} />
            <Label htmlFor="text-template-default" className="font-normal">
              {t("texts.useAsDefault")}
            </Label>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={save.isPending}>
              {t("common.save")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function NoticesCard({ language }: { readonly language: Language }) {
  const { t } = useI18n();
  const notices = useQuery(legalNoticesQuery);
  return (
    <Card aria-labelledby="texts-notices">
      <CardHeader>
        <CardTitle id="texts-notices" className="text-base">
          {t("texts.notices")}
        </CardTitle>
        <CardDescription>{t("texts.noticesHint")}</CardDescription>
      </CardHeader>
      {notices.isPending ? (
        <Skeleton className="h-40 w-full" />
      ) : (
        <div className="flex flex-col gap-5">
          {(notices.data ?? [])
            .filter((notice) => notice.language === language)
            .map((notice) => (
              <NoticeEditor key={`${notice.treatment}-${notice.text}`} notice={notice} />
            ))}
        </div>
      )}
    </Card>
  );
}

function NoticeEditor({ notice }: { readonly notice: LegalNotice }) {
  const { t } = useI18n();
  const save = useSaveLegalNotice();
  const errorMessage = useErrorMessage();
  const [text, setText] = useState(notice.text);
  const id = `notice-${notice.treatment}`;
  const store = (value: string) => {
    save.mutate(
      { treatment: notice.treatment, language: notice.language, text: value },
      {
        onSuccess: () => toast.success(t("common.saved")),
        onError: (caught) => {
          toast.error(errorMessage(caught) ?? t("error.generic"), { duration: Infinity });
        },
      },
    );
  };
  return (
    <div className="flex flex-col gap-2">
      <Field
        label={t(`treatment.${notice.treatment}`)}
        description={notice.customized ? t("texts.noticeCustomized") : t("texts.noticeBuiltIn")}
      >
        <Textarea
          id={id}
          rows={2}
          value={text}
          maxLength={MAX_NOTICE}
          onChange={(event) => {
            setText(event.target.value);
          }}
        />
      </Field>
      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          disabled={save.isPending || text === notice.text}
          onClick={() => {
            store(text);
          }}
        >
          {t("common.save")} <span className="sr-only">{t(`treatment.${notice.treatment}`)}</span>
        </Button>
        {notice.customized ? (
          <Button
            size="sm"
            variant="ghost"
            disabled={save.isPending}
            onClick={() => {
              store("");
            }}
          >
            <RotateCcwIcon aria-hidden="true" />
            {t("texts.restoreNotice")}{" "}
            <span className="sr-only">{t(`treatment.${notice.treatment}`)}</span>
          </Button>
        ) : null}
      </div>
    </div>
  );
}
