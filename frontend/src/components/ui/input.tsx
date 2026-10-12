import type { ComponentProps } from "react";

import { fieldClasses } from "@/components/ui/field-styles";
import { cn } from "@/lib/cn";

export function Input({ className, type = "text", ...props }: ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        fieldClasses,
        "flex h-10 px-3 py-1",
        "file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground",
        className,
      )}
      {...props}
    />
  );
}

export function Textarea({ className, ...props }: ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(fieldClasses, "flex min-h-20 px-3 py-2", className)}
      {...props}
    />
  );
}
