import { Link } from "@tanstack/react-router";
import { ArrowLeftIcon } from "lucide-react";

type BackTarget = "/invoices" | "/quotes" | "/customers" | "/articles" | "/recurring";

/** The way back to the page a sub-page belongs to, above its title. */
export function BackLink({ to, label }: { readonly to: BackTarget; readonly label: string }) {
  return (
    <Link
      to={to}
      className="inline-flex min-h-6 w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
    >
      <ArrowLeftIcon className="size-4" aria-hidden="true" />
      {label}
    </Link>
  );
}
