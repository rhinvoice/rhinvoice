import { CircleAlertIcon } from "lucide-react";
import { useEffect, useRef } from "react";

export interface ErrorSummaryItem {
  readonly fieldId: string;
  readonly message: string;
}

interface ErrorSummaryProps {
  readonly title: string;
  readonly items: readonly ErrorSummaryItem[];
  /** Changes on every submit attempt (e.g. react-hook-form's submitCount). */
  readonly submitCount: number;
}

/**
 * Summary at the top of a form. It receives focus after each failed submit
 * attempt (WCAG 3.3.1), but never while the user is typing.
 */
export function ErrorSummary({ title, items, submitCount }: ErrorSummaryProps) {
  const ref = useRef<HTMLDivElement>(null);
  const hasItems = items.length > 0;
  useEffect(() => {
    if (hasItems) {
      ref.current?.focus();
    }
    // Only a new submit attempt moves the focus.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [submitCount]);
  if (items.length === 0) {
    return null;
  }
  return (
    <div
      ref={ref}
      tabIndex={-1}
      role="alert"
      className="rounded-lg border border-destructive/50 bg-destructive/5 p-4 text-foreground"
    >
      <p className="flex items-center gap-2 font-medium text-destructive">
        <CircleAlertIcon className="size-4" aria-hidden="true" />
        {title}
      </p>
      <ul className="mt-2 list-disc space-y-1 pl-10 text-sm">
        {items.map((item) => (
          <li key={item.fieldId}>
            <a className="underline underline-offset-2" href={`#${item.fieldId}`}>
              {item.message}
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}
