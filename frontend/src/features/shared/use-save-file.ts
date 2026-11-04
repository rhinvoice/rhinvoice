import { toast } from "sonner";

import { useI18n } from "@/components/i18n/use-i18n";
import { fetchFile, saveFile } from "@/features/shared/file-download";
import { useErrorMessage } from "@/features/shared/use-error-message";

/** Load a file of the API and save it; a failure shows as a toast that stays. */
export function useSaveFile(): (url: string) => void {
  const { t } = useI18n();
  const errorMessage = useErrorMessage();
  return (url) => {
    fetchFile(url, "document.pdf")
      .then(saveFile)
      .catch((caught: unknown) => {
        toast.error(errorMessage(caught) ?? t("error.generic"), { duration: Infinity });
      });
  };
}
