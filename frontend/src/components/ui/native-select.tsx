import { ChevronDownIcon } from "lucide-react";
import type { ComponentProps } from "react";

import { fieldClasses } from "@/components/ui/field-styles";
import { cn } from "@/lib/cn";

/** The browser's select element: accessible, keyboard friendly and native on mobile. */
export function NativeSelect({ className, children, ...props }: ComponentProps<"select">) {
  return (
    <div className="relative">
      <select
        className={cn(fieldClasses, "flex h-10 appearance-none py-1 pr-9 pl-3", className)}
        {...props}
      >
        {children}
      </select>
      <ChevronDownIcon
        className="pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2 text-muted-foreground"
        aria-hidden="true"
      />
    </div>
  );
}
