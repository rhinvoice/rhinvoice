import { useI18n } from "@/components/i18n/use-i18n";
import { ApiError } from "@/lib/api-error";
import { errorMessageKey } from "@/lib/i18n";

/** Translate an error from a mutation into a user facing message. */
export function useErrorMessage(): (error: unknown) => string | null {
  const { t } = useI18n();
  return (error) => {
    if (error === null || error === undefined) {
      return null;
    }
    if (error instanceof ApiError) {
      if (error.code === "network") {
        return t("error.network");
      }
      const key = errorMessageKey(error.code);
      const text = key === "error.generic" && error.status === 422 ? error.message : t(key);
      // A mail server's own reply usually says exactly what is wrong.
      const refused = error.details["refused"];
      const reply = error.details["server"];
      return [
        text,
        refused === undefined ? "" : t("error.refusedRecipients", { refused }),
        reply === undefined ? "" : t("error.serverSaid", { reply }),
      ]
        .filter((part) => part !== "")
        .join(" ");
    }
    return t("error.generic");
  };
}
