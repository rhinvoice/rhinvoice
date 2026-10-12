import type { FieldErrors, FieldValues } from "react-hook-form";

import type { ErrorSummaryItem } from "@/components/ui/error-summary";

/** Flatten react-hook-form errors into error summary items (field id = field name). */
export function summaryItems<T extends FieldValues>(
  errors: FieldErrors<T>,
  order: readonly (keyof T & string)[],
): ErrorSummaryItem[] {
  return order.flatMap((name) => {
    const message = errors[name]?.message;
    return typeof message === "string" ? [{ fieldId: name, message }] : [];
  });
}
