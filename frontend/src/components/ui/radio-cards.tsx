import { forwardRef, type ComponentProps } from "react";

import { cn } from "@/lib/cn";

/** A native radio button styled as a selectable card (keyboard: arrow keys). */
export const RadioCard = forwardRef<
  HTMLInputElement,
  ComponentProps<"input"> & { readonly label: string }
>(function RadioCard({ label, className, id, ...props }, ref) {
  return (
    <label
      htmlFor={id}
      className={cn(
        "flex min-h-10 cursor-pointer items-center gap-2 rounded-md border border-transparent bg-muted px-3 text-sm font-medium has-[:checked]:border-primary has-[:checked]:bg-accent has-[:checked]:text-accent-foreground has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring has-[:focus-visible]:ring-offset-2 has-[:focus-visible]:ring-offset-background",
        className,
      )}
    >
      <input
        ref={ref}
        id={id}
        type="radio"
        className="size-4 accent-primary focus-visible:ring-0"
        {...props}
      />
      {label}
    </label>
  );
});
