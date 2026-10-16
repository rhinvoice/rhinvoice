import { useQuery } from "@tanstack/react-query";
import { SendIcon } from "lucide-react";
import { useState, type SyntheticEvent } from "react";
import { toast } from "sonner";

import { useI18n } from "@/components/i18n/use-i18n";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import {
  SECURITIES,
  serverProblems,
  toRequest,
  toValues,
  withSecurity,
  type ServerField,
  type ServerProblem,
  type ServerValues,
} from "@/features/mail/mail-settings-model";
import { companyQuery } from "@/features/shared/company-api";
import { DOCUMENT_LANGUAGES } from "@/features/shared/document-languages";
import { FormAlert } from "@/features/shared/form-alert";
import {
  mailServerQuery,
  mailTemplatesQuery,
  useSaveMailServer,
  useSaveMailTemplate,
  useSendTestMail,
  type MailKind,
  type MailServer,
  type MailTemplate,
} from "@/features/shared/mail-api";
import { useErrorMessage } from "@/features/shared/use-error-message";
import { ApiError } from "@/lib/api-error";
import { errorMessageKey } from "@/lib/i18n";
import { NotInDemo } from "@/features/shared/not-in-demo";

const KINDS = [
  "invoice",
  "quote",
  "cancellation",
  "reminder_1",
  "reminder_2",
  "reminder_3",
] as const satisfies readonly MailKind[];
const PLACEHOLDERS = [
  "nummer",
  "datum",
  "faellig",
  "kunde",
  "betrag",
  "waehrung",
  "firma",
] as const;

/** API field names of the server settings, as the form names them. */
const SERVER_FIELDS: Readonly<Record<string, string>> = {
  reply_to: "replyTo",
  sender_name: "senderName",
};

/** Settings → E-mail: the outgoing server, a test mail and the mail templates. */
export function MailSettings() {
  const { t } = useI18n();
  const server = useQuery(mailServerQuery);
  const company = useQuery(companyQuery);
  if (server.data === undefined || company.isPending) {
    return server.isPending ? <Skeleton className="h-96 max-w-3xl" /> : null;
  }
  return (
    <div className="flex max-w-3xl flex-col gap-4">
      <NotInDemo title={t("mail.serverTitle")}>
        <ServerForm server={server.data} companyName={company.data?.name ?? ""} />
        {/* Starts again with the saved sender address after each save. */}
        <TestMail key={server.data.sender} server={server.data} />
      </NotInDemo>
      <Templates />
    </div>
  );
}

function ServerForm({
  server,
  companyName,
}: {
  readonly server: MailServer;
  readonly companyName: string;
}) {
  const { t } = useI18n();
  const errorMessage = useErrorMessage();
  const save = useSaveMailServer();
  const [values, setValues] = useState(() => toValues(server, companyName));
  const [checked, setChecked] = useState(false);
  const [serverErrors, setServerErrors] = useState<Readonly<Record<string, string>>>({});
  const problems = checked ? serverProblems(values) : new Map<ServerField, ServerProblem>();
  const error = (field: ServerField): string | undefined => {
    const problem = problems.get(field);
    return problem === undefined ? serverErrors[field] : t(`mail.problem.${problem}`);
  };
  const change = (patch: Partial<ServerValues>) => {
    setValues((current) => ({ ...current, ...patch }));
  };

  const submit = (event: SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault();
    setChecked(true);
    setServerErrors({});
    if (serverProblems(values).size > 0) return;
    save.mutate(toRequest(values), {
      onSuccess: (stored) => {
        setValues(toValues(stored, companyName));
        setChecked(false);
        toast.success(t("common.saved"));
      },
      onError: (caught) => {
        if (caught instanceof ApiError && caught.status === 422) {
          // e.g. {"sender": "…"}: the server's rules belong to the field.
          const fields: Record<string, string> = {};
          for (const [field, message] of Object.entries(caught.details)) {
            fields[SERVER_FIELDS[field] ?? field] = t("validation.server", { message });
          }
          setServerErrors(fields);
        }
      },
    });
  };

  return (
    <form onSubmit={submit} noValidate>
      <Card aria-labelledby="mail-server-title">
        <CardHeader>
          <CardTitle id="mail-server-title">{t("mail.serverTitle")}</CardTitle>
          <CardDescription>{t("mail.serverDescription")}</CardDescription>
        </CardHeader>
        <FormAlert
          message={
            problems.size > 0
              ? t("mail.problems")
              : save.isError && Object.keys(serverErrors).length === 0
                ? errorMessage(save.error)
                : null
          }
        />
        <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_8rem]">
          <Field label={t("mail.host")} description={t("mail.hostHint")} error={error("host")}>
            <Input
              id="mail-host"
              autoComplete="off"
              spellCheck={false}
              value={values.host}
              onChange={(event) => {
                change({ host: event.target.value });
              }}
            />
          </Field>
          <Field label={t("mail.port")} error={error("port")}>
            <Input
              id="mail-port"
              inputMode="numeric"
              className="tabular-nums"
              value={values.port}
              onChange={(event) => {
                change({ port: event.target.value });
              }}
            />
          </Field>
        </div>
        <Field label={t("mail.security")} description={t(`mail.securityHint.${values.security}`)}>
          <NativeSelect
            id="mail-security"
            value={values.security}
            onChange={(event) => {
              const next = SECURITIES.find((security) => security === event.target.value);
              if (next !== undefined) setValues((current) => withSecurity(current, next));
            }}
          >
            {SECURITIES.map((security) => (
              <option key={security} value={security}>
                {t(`mail.securityOption.${security}`)}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            label={t("mail.username")}
            description={t("mail.usernameHint")}
            optionalLabel={t("common.optional")}
          >
            <Input
              id="mail-username"
              autoComplete="off"
              spellCheck={false}
              value={values.username}
              onChange={(event) => {
                change({ username: event.target.value });
              }}
            />
          </Field>
          <Field
            label={t("mail.password")}
            description={server.password_set ? t("mail.passwordKept") : t("mail.passwordHint")}
            error={error("password")}
            optionalLabel={t("common.optional")}
          >
            <Input
              id="mail-password"
              type="password"
              autoComplete="new-password"
              value={values.password}
              onChange={(event) => {
                change({ password: event.target.value });
              }}
            />
          </Field>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            label={t("mail.sender")}
            description={t("mail.senderHint")}
            error={error("sender")}
          >
            <Input
              id="mail-sender"
              type="email"
              autoComplete="email"
              value={values.sender}
              onChange={(event) => {
                change({ sender: event.target.value });
              }}
            />
          </Field>
          <Field label={t("mail.senderName")} optionalLabel={t("common.optional")}>
            <Input
              id="mail-sender-name"
              value={values.senderName}
              onChange={(event) => {
                change({ senderName: event.target.value });
              }}
            />
          </Field>
        </div>
        <Field
          label={t("mail.replyTo")}
          description={t("mail.replyToHint")}
          error={error("replyTo")}
          optionalLabel={t("common.optional")}
        >
          <Input
            id="mail-reply-to"
            type="email"
            value={values.replyTo}
            onChange={(event) => {
              change({ replyTo: event.target.value });
            }}
          />
        </Field>
        <div className="flex items-center gap-3">
          <Switch
            id="mail-copy"
            checked={values.copyToSender}
            onCheckedChange={(copyToSender) => {
              change({ copyToSender });
            }}
          />
          <Label htmlFor="mail-copy" className="font-normal">
            {t("mail.copyToSender")}
          </Label>
        </div>
        <div className="flex justify-end">
          <Button type="submit" disabled={save.isPending}>
            {t("common.save")}
          </Button>
        </div>
      </Card>
    </form>
  );
}

function TestMail({ server }: { readonly server: MailServer }) {
  const { t } = useI18n();
  const errorMessage = useErrorMessage();
  const test = useSendTestMail();
  const [to, setTo] = useState(server.sender);
  return (
    <Card aria-labelledby="mail-test-title">
      <CardHeader>
        <CardTitle id="mail-test-title">{t("mail.testTitle")}</CardTitle>
        <CardDescription>
          {server.configured ? t("mail.testDescription") : t("mail.testFirstSave")}
        </CardDescription>
      </CardHeader>
      <form
        className="flex flex-col gap-3 sm:flex-row sm:items-end"
        onSubmit={(event) => {
          event.preventDefault();
          test.mutate(to.trim(), {
            onSuccess: () => toast.success(t("mail.testSent", { to: to.trim() })),
          });
        }}
        noValidate
      >
        <Field label={t("mail.testTo")} className="grow">
          <Input
            id="mail-test-to"
            type="email"
            value={to}
            onChange={(event) => {
              setTo(event.target.value);
            }}
          />
        </Field>
        <Button
          type="submit"
          variant="outline"
          disabled={!server.configured || test.isPending || to.trim() === ""}
        >
          <SendIcon aria-hidden="true" />
          {test.isPending ? t("mail.sending") : t("mail.sendTest")}
        </Button>
      </form>
      {test.isError ? <FormAlert message={errorMessage(test.error)} /> : null}
    </Card>
  );
}

function Templates() {
  const { t } = useI18n();
  const templates = useQuery(mailTemplatesQuery);
  const [kind, setKind] = useState<MailKind>("invoice");
  const [language, setLanguage] = useState<(typeof DOCUMENT_LANGUAGES)[number]>("de");
  const template = templates.data?.find(
    (candidate) => candidate.kind === kind && candidate.language === language,
  );
  return (
    <Card aria-labelledby="mail-templates-title">
      <CardHeader>
        <CardTitle id="mail-templates-title">{t("mail.templatesTitle")}</CardTitle>
        <CardDescription>{t("mail.templatesDescription")}</CardDescription>
      </CardHeader>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label={t("mail.templateKind")}>
          <NativeSelect
            id="mail-template-kind"
            value={kind}
            onChange={(event) => {
              const next = KINDS.find((candidate) => candidate === event.target.value);
              if (next !== undefined) setKind(next);
            }}
          >
            {KINDS.map((option) => (
              <option key={option} value={option}>
                {t(`mail.kind.${option}`)}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field label={t("mail.templateLanguage")}>
          <NativeSelect
            id="mail-template-language"
            value={language}
            onChange={(event) => {
              const next = DOCUMENT_LANGUAGES.find((candidate) => candidate === event.target.value);
              if (next !== undefined) setLanguage(next);
            }}
          >
            {DOCUMENT_LANGUAGES.map((option) => (
              <option key={option} value={option}>
                {t(`language.${option}`)}
              </option>
            ))}
          </NativeSelect>
        </Field>
      </div>
      {template === undefined ? (
        <Skeleton className="h-64" />
      ) : (
        <TemplateForm
          key={`${template.kind}-${template.language}-${template.subject}`}
          template={template}
        />
      )}
    </Card>
  );
}

function TemplateForm({ template }: { readonly template: MailTemplate }) {
  const { t } = useI18n();
  const errorMessage = useErrorMessage();
  const save = useSaveMailTemplate();
  const [subject, setSubject] = useState(template.subject);
  const [body, setBody] = useState(template.body);
  const [errors, setErrors] = useState<{ subject?: string; body?: string; root?: string }>({});

  const store = (next: { subject: string; body: string }, done: string) => {
    save.mutate(
      { kind: template.kind, language: template.language, ...next },
      {
        onSuccess: (saved) => {
          setSubject(saved.subject);
          setBody(saved.body);
          setErrors({});
          toast.success(done);
        },
        onError: (caught) => {
          if (caught instanceof ApiError && caught.status === 422) {
            const key = errorMessageKey(caught.code);
            const message = key === "error.generic" ? (errorMessage(caught) ?? "") : t(key);
            setErrors("subject" in caught.details ? { subject: message } : { body: message });
            return;
          }
          setErrors({ root: errorMessage(caught) ?? t("error.generic") });
        },
      },
    );
  };

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        const found = {
          ...(subject.trim() === "" ? { subject: t("validation.required") } : {}),
          ...(body.trim() === "" ? { body: t("validation.required") } : {}),
        };
        setErrors(found);
        if (Object.keys(found).length === 0) store({ subject, body }, t("common.saved"));
      }}
      noValidate
    >
      <FormAlert message={errors.root ?? null} />
      <Field label={t("mail.subject")} error={errors.subject}>
        <Input
          id="mail-template-subject"
          value={subject}
          maxLength={200}
          onChange={(event) => {
            setSubject(event.target.value);
          }}
        />
      </Field>
      <Field
        label={t("mail.body")}
        description={template.customized ? t("mail.templateOwn") : t("mail.templateBuiltIn")}
        error={errors.body}
      >
        <Textarea
          id="mail-template-body"
          rows={9}
          value={body}
          maxLength={5000}
          onChange={(event) => {
            setBody(event.target.value);
          }}
        />
      </Field>
      <div className="flex flex-col gap-1.5">
        <span className="text-sm font-medium" id="mail-template-placeholders">
          {t("texts.placeholders")}
        </span>
        <div
          role="group"
          aria-labelledby="mail-template-placeholders"
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
                setBody((current) => `${current}{${placeholder}}`);
              }}
            >
              {`{${placeholder}}`}
            </Button>
          ))}
        </div>
      </div>
      <div className="flex flex-wrap justify-end gap-2">
        {template.customized ? (
          <Button
            type="button"
            variant="outline"
            disabled={save.isPending}
            onClick={() => {
              store({ subject: "", body: "" }, t("mail.templateRestored"));
            }}
          >
            {t("mail.restoreTemplate")}
          </Button>
        ) : null}
        <Button type="submit" disabled={save.isPending}>
          {t("common.save")}
        </Button>
      </div>
    </form>
  );
}
