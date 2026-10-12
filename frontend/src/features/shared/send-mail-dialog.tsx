import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { MailIcon, PaperclipIcon } from "lucide-react";
import { useState, type SyntheticEvent } from "react";
import { toast } from "sonner";

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
import { Input, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { FormAlert } from "@/features/shared/form-alert";
import {
  mailDraftQuery,
  mailServerQuery,
  useSendMail,
  type MailDraft,
  type MailSubject,
} from "@/features/shared/mail-api";
import { MAX_RECIPIENTS, parseRecipients, recipientProblem } from "@/features/shared/mail-model";
import { useErrorMessage } from "@/features/shared/use-error-message";
import { ApiError } from "@/lib/api-error";

interface SendMailDialogProps {
  readonly subject: MailSubject;
  /** Something to consider before sending, e.g. that the invoice is cancelled. */
  readonly warning?: string | undefined;
  readonly title: string;
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  /** Offer to attach the XRechnung too (invoices that can be one). */
  readonly xrechnung?: boolean;
}

/** Check and send the mail of a document or reminder; the server fills in the template. */
export function SendMailDialog({
  subject,
  title,
  open,
  onOpenChange,
  xrechnung = false,
  warning,
}: SendMailDialogProps) {
  const { t } = useI18n();
  const close = () => {
    onOpenChange(false);
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent closeLabel={t("common.close")} className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{t("mail.sendTitle", { title })}</DialogTitle>
          <DialogDescription>{t("mail.sendDescription")}</DialogDescription>
        </DialogHeader>
        {/* Mounted per opening: the mail is prepared anew each time. */}
        {open ? (
          <MailContent subject={subject} xrechnung={xrechnung} warning={warning} onDone={close} />
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

interface MailContentProps {
  readonly subject: MailSubject;
  readonly warning: string | undefined;
  readonly xrechnung: boolean;
  readonly onDone: () => void;
}

function MailContent({ subject, xrechnung, warning, onDone }: MailContentProps) {
  const { t } = useI18n();
  const errorMessage = useErrorMessage();
  const server = useQuery(mailServerQuery);
  const draft = useQuery(mailDraftQuery(subject));
  if (server.isPending || draft.isPending) {
    return <Skeleton className="h-80" />;
  }
  if (server.data?.configured === false) {
    return (
      <div className="flex flex-col gap-4">
        <p className="text-sm">{t("mail.notConfigured")}</p>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onDone}>
            {t("common.close")}
          </Button>
          <Button asChild>
            <Link to="/settings" search={{ tab: "mail" }}>
              {t("mail.setUp")}
            </Link>
          </Button>
        </DialogFooter>
      </div>
    );
  }
  if (draft.data === undefined) {
    return <FormAlert message={errorMessage(draft.error) ?? t("error.generic")} />;
  }
  return (
    <MailForm
      subject={subject}
      draft={draft.data}
      xrechnung={xrechnung}
      warning={warning}
      onDone={onDone}
    />
  );
}

interface MailFormProps {
  readonly subject: MailSubject;
  readonly warning: string | undefined;
  readonly draft: MailDraft;
  readonly xrechnung: boolean;
  readonly onDone: () => void;
}

interface MailErrors {
  readonly to?: string;
  readonly subject?: string;
  readonly body?: string;
  readonly root?: string;
}

function MailForm({ subject, draft, xrechnung, warning, onDone }: MailFormProps) {
  const { t } = useI18n();
  const errorMessage = useErrorMessage();
  const send = useSendMail(subject);
  const [to, setTo] = useState(draft.to.join(", "));
  const [mailSubject, setMailSubject] = useState(draft.subject);
  const [body, setBody] = useState(draft.body);
  const [attachXml, setAttachXml] = useState(false);
  const [errors, setErrors] = useState<MailErrors>({});

  const submit = (event: SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault();
    const recipients = parseRecipients(to);
    const problem = recipientProblem(recipients);
    const found: MailErrors = {
      ...(problem === null
        ? {}
        : {
            to:
              problem.kind === "invalid"
                ? t("mail.invalidRecipient", { address: problem.address })
                : problem.kind === "missing"
                  ? t("mail.recipientMissing")
                  : t("mail.tooManyRecipients", { max: MAX_RECIPIENTS }),
          }),
      ...(mailSubject.trim() === "" ? { subject: t("validation.required") } : {}),
      ...(body.trim() === "" ? { body: t("validation.required") } : {}),
    };
    setErrors(found);
    const invalid = (["to", "subject", "body"] as const).find((field) => field in found);
    if (invalid !== undefined) {
      // The field says what is wrong (aria-describedby); the summary above announces it.
      document.getElementById(`mail-${invalid}`)?.focus();
      return;
    }
    send.mutate(
      { to: recipients, subject: mailSubject, body, xrechnung: xrechnung && attachXml },
      {
        onSuccess: () => {
          toast.success(t("mail.sent", { to: recipients.join(", ") }));
          onDone();
        },
        onError: (caught) => {
          // The server's checks of a field belong to the field.
          const field =
            caught instanceof ApiError && caught.status === 422
              ? (["to", "subject", "body"] as const).find((name) => name in caught.details)
              : undefined;
          const message = errorMessage(caught) ?? t("error.generic");
          setErrors(field === undefined ? { root: message } : { [field]: message });
        },
      },
    );
  };

  const fieldError = errors.to ?? errors.subject ?? errors.body;
  return (
    <form className="flex flex-col gap-4" onSubmit={submit} noValidate>
      <FormAlert
        message={errors.root ?? (fieldError === undefined ? null : t("mail.checkFields"))}
      />
      {warning === undefined ? null : (
        <p className="rounded-md bg-status-overdue-bg px-3 py-2 text-sm text-status-overdue-fg">
          {warning}
        </p>
      )}
      <Field
        label={t("mail.to")}
        description={draft.to.length === 0 ? t("mail.noCustomerAddress") : t("mail.toHint")}
        error={errors.to}
      >
        <Input
          id="mail-to"
          type="text"
          inputMode="email"
          autoComplete="off"
          value={to}
          onChange={(event) => {
            setTo(event.target.value);
          }}
        />
      </Field>
      <Field label={t("mail.subject")} error={errors.subject}>
        <Input
          id="mail-subject"
          value={mailSubject}
          maxLength={200}
          onChange={(event) => {
            setMailSubject(event.target.value);
          }}
        />
      </Field>
      <Field label={t("mail.body")} error={errors.body}>
        <Textarea
          id="mail-body"
          rows={10}
          value={body}
          maxLength={5000}
          onChange={(event) => {
            setBody(event.target.value);
          }}
        />
      </Field>
      <div className="flex flex-col gap-2 text-sm">
        <span className="font-medium">{t("mail.attachments")}</span>
        <span className="inline-flex items-center gap-1.5 text-muted-foreground">
          <PaperclipIcon className="size-4" aria-hidden="true" />
          {draft.attachment}
        </span>
        {xrechnung ? (
          <div className="flex items-center gap-3">
            <Switch id="mail-xrechnung" checked={attachXml} onCheckedChange={setAttachXml} />
            <Label htmlFor="mail-xrechnung" className="font-normal">
              {t("mail.attachXrechnung")}
            </Label>
          </div>
        ) : null}
        {draft.copy_to === null ? null : (
          <span className="text-muted-foreground">
            {t("mail.copyTo", { address: draft.copy_to })}
          </span>
        )}
      </div>
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onDone}>
          {t("common.cancel")}
        </Button>
        <Button type="submit" disabled={send.isPending}>
          <MailIcon aria-hidden="true" />
          {send.isPending ? t("mail.sending") : t("mail.send")}
        </Button>
      </DialogFooter>
    </form>
  );
}
