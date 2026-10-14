import { useQuery } from "@tanstack/react-query";
import { CheckIcon, CopyIcon } from "lucide-react";
import { useState, type SyntheticEvent } from "react";
import { toast } from "sonner";

import { useI18n } from "@/components/i18n/use-i18n";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  recoveryKeyQuery,
  useConfirmRecoveryKey,
  useSetUpBackups,
  type BackupSetup,
} from "@/features/backup/api";
import {
  OTHER_FOLDER,
  chosenFolder,
  initialFolderChoice,
  keyGroups,
} from "@/features/backup/backup-model";
import { FormAlert } from "@/features/shared/form-alert";
import { useErrorMessage } from "@/features/shared/use-error-message";
import { ApiError } from "@/lib/api-error";

/**
 * Where the backups of the installation without Docker go (ADR 0023): a folder a cloud
 * service keeps in sync, found on this computer, or another one.
 */
export function FolderChooser({
  setup,
  onDone,
  onCancel,
}: {
  readonly setup: BackupSetup;
  readonly onDone?: () => void;
  readonly onCancel?: () => void;
}) {
  const { t } = useI18n();
  const errorMessage = useErrorMessage();
  const setUp = useSetUpBackups();
  const [folder, setFolder] = useState(() => initialFolderChoice(setup));
  const [missing, setMissing] = useState(false);
  const changing = setup.folder !== null;

  function submit(event: SyntheticEvent<HTMLFormElement>) {
    event.preventDefault();
    const chosen = chosenFolder(folder);
    setMissing(chosen === null);
    if (chosen !== null) {
      setUp.mutate(chosen, { onSuccess: () => onDone?.() });
    }
  }

  const failure = setUp.error;
  const unusable =
    failure instanceof ApiError && failure.code === "backup_folder_unusable"
      ? t("backup.folderUnusable", { reason: failure.details["folder"] ?? failure.message })
      : null;
  return (
    <Card aria-labelledby="backup-folder-title">
      <CardHeader>
        <CardTitle id="backup-folder-title">
          {t(changing ? "backup.setup.changeTitle" : "backup.setup.title")}
        </CardTitle>
        <CardDescription>{t("backup.setup.description")}</CardDescription>
      </CardHeader>
      <form className="flex flex-col gap-4" noValidate onSubmit={submit}>
        <fieldset className="flex flex-col gap-2">
          <legend className="sr-only">{t("backup.setup.folders")}</legend>
          {setup.suggestions.map((suggestion) => (
            <FolderOption
              key={suggestion.path}
              value={suggestion.path}
              checked={folder.choice === suggestion.path}
              title={suggestion.name}
              detail={suggestion.path}
              found
              onChoose={(choice) => {
                setFolder({ ...folder, choice });
              }}
            />
          ))}
          <FolderOption
            value={OTHER_FOLDER}
            checked={folder.choice === OTHER_FOLDER}
            title={t("backup.setup.other")}
            detail={t("backup.setup.otherHint")}
            onChoose={(choice) => {
              setFolder({ ...folder, choice });
            }}
          />
        </fieldset>
        {folder.choice === OTHER_FOLDER ? (
          <Field
            label={t("backup.setup.path")}
            description={t("backup.setup.pathHint")}
            error={missing ? t("backup.setup.pathMissing") : undefined}
          >
            <Input
              value={folder.other}
              autoComplete="off"
              spellCheck={false}
              className="font-mono"
              onChange={(event) => {
                setFolder({ ...folder, other: event.target.value });
              }}
            />
          </Field>
        ) : null}
        <FormAlert message={unusable ?? (failure === null ? null : errorMessage(failure))} />
        <div className="flex flex-wrap gap-2">
          <Button type="submit" disabled={setUp.isPending}>
            {t(changing ? "backup.setup.change" : "backup.setup.continue")}
          </Button>
          {onCancel === undefined ? null : (
            <Button type="button" variant="outline" onClick={onCancel}>
              {t("common.cancel")}
            </Button>
          )}
        </div>
      </form>
    </Card>
  );
}

function FolderOption({
  value,
  checked,
  title,
  detail,
  found = false,
  onChoose,
}: {
  readonly value: string;
  readonly checked: boolean;
  readonly title: string;
  readonly detail: string;
  readonly found?: boolean;
  readonly onChoose: (value: string) => void;
}) {
  const { t } = useI18n();
  return (
    <label className="grid cursor-pointer grid-cols-[auto_1fr_auto] items-start gap-x-3 gap-y-0.5 rounded-xl border border-border bg-card p-3 has-[:checked]:border-primary has-[:checked]:bg-accent has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring has-[:focus-visible]:ring-offset-2">
      <input
        type="radio"
        name="backup-folder"
        value={value}
        checked={checked}
        className="mt-1 size-4 accent-primary focus-visible:ring-0"
        onChange={() => {
          onChoose(value);
        }}
      />
      <span className="font-medium">{title}</span>
      {found ? (
        <span className="rounded-full bg-status-paid-bg px-2 py-0.5 text-xs font-semibold text-status-paid-fg">
          {t("backup.setup.found")}
        </span>
      ) : (
        <span />
      )}
      <span className="col-span-2 col-start-2 text-sm break-all text-muted-foreground">
        {detail}
      </span>
    </label>
  );
}

/**
 * The recovery key: shown until the person confirms it is kept elsewhere, later on request.
 */
export function RecoveryKey({
  mustConfirm,
  onHide,
}: {
  readonly mustConfirm: boolean;
  readonly onHide?: () => void;
}) {
  const { t } = useI18n();
  const errorMessage = useErrorMessage();
  const query = useQuery(recoveryKeyQuery);
  const confirm = useConfirmRecoveryKey();
  const [kept, setKept] = useState(false);
  const key = query.data?.key;
  return (
    <Card aria-labelledby="backup-key-title">
      <CardHeader>
        <CardTitle id="backup-key-title">{t("backup.key.title")}</CardTitle>
        <CardDescription>{t("backup.key.description")}</CardDescription>
      </CardHeader>
      <FormAlert message={query.isError ? errorMessage(query.error) : null} />
      {key === undefined ? (
        query.isPending ? (
          <Skeleton className="h-20" />
        ) : null
      ) : (
        <>
          <div
            role="group"
            aria-label={t("backup.key.label")}
            className="grid grid-cols-2 justify-center gap-x-4 gap-y-1.5 rounded-lg border border-dashed bg-background p-3 text-center font-mono text-base tracking-wider sm:grid-cols-4"
          >
            {keyGroups(key).map((group, index) => (
              // The same group may occur twice; the position identifies it.
              <span key={index}>{group}</span>
            ))}
          </div>
          <CopyKey text={key} />
        </>
      )}
      {mustConfirm ? (
        <div className="flex flex-col gap-3">
          <label className="flex cursor-pointer items-start gap-3">
            <input
              type="checkbox"
              checked={kept}
              className="mt-1 size-4 accent-primary"
              onChange={(event) => {
                setKept(event.target.checked);
              }}
            />
            <span className="text-sm font-medium">{t("backup.key.kept")}</span>
          </label>
          <FormAlert message={confirm.isError ? errorMessage(confirm.error) : null} />
          <div>
            <Button
              disabled={!kept || key === undefined || confirm.isPending}
              onClick={() => {
                confirm.mutate(undefined, {
                  onSuccess: () => toast.success(t("backup.key.done")),
                });
              }}
            >
              {t("backup.key.finish")}
            </Button>
          </div>
        </div>
      ) : (
        <div>
          <Button variant="outline" onClick={onHide}>
            {t("backup.key.hide")}
          </Button>
        </div>
      )}
    </Card>
  );
}

function CopyKey({ text }: { readonly text: string }) {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);
  return (
    <div>
      <Button
        type="button"
        variant="outline"
        onClick={() => {
          navigator.clipboard.writeText(text).then(
            () => {
              setCopied(true);
              window.setTimeout(() => {
                setCopied(false);
              }, 2_000);
            },
            () => {
              // Refused (e.g. plain http on another computer): the key can still be selected.
            },
          );
        }}
      >
        {copied ? <CheckIcon aria-hidden="true" /> : <CopyIcon aria-hidden="true" />}
        {copied ? t("common.copied") : t("common.copy")}
      </Button>
    </div>
  );
}
