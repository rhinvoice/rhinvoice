import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

interface FieldsetProps {
  readonly legend: string;
  readonly description?: string;
  readonly children: ReactNode;
  readonly className?: string;
}

/** A titled group of form fields (WCAG 1.3.1), shown as a card. */
export function Fieldset({ legend, description, children, className }: FieldsetProps) {
  return (
    <fieldset
      className={cn(
        "min-w-0 rounded-xl border border-border/70 bg-card p-4 shadow-sm md:p-6",
        className,
      )}
    >
      {/* Floating the legend keeps it inside the card instead of on its border. */}
      <legend className="float-left mb-4 w-full text-base font-semibold">{legend}</legend>
      <div className="clear-left flex flex-col gap-4">
        {description === undefined ? null : (
          <p className="-mt-3 text-sm text-muted-foreground">{description}</p>
        )}
        {children}
      </div>
    </fieldset>
  );
}
