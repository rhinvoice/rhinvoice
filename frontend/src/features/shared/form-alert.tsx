import { CircleAlertIcon } from "lucide-react";

/** Form level error (e.g. wrong credentials), announced immediately. */
export function FormAlert({ message }: { readonly message: string | null }) {
  if (message === null) {
    return null;
  }
  return (
    <p
      role="alert"
      className="flex items-start gap-2 rounded-lg border border-destructive/50 bg-destructive/5 p-3 text-sm text-destructive"
    >
      <CircleAlertIcon className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      {message}
    </p>
  );
}
