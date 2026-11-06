import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { LoaderCircleIcon } from "lucide-react";
import type { ComponentProps, MouseEvent } from "react";

import { useRunOnce } from "@/components/use-run-once";
import { cn } from "@/lib/cn";

export const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-2 rounded-md text-sm font-medium whitespace-nowrap transition-colors duration-150 disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground shadow-xs hover:bg-primary/90",
        destructive: "bg-destructive text-destructive-foreground shadow-xs hover:bg-destructive/90",
        outline: "bg-muted text-foreground hover:bg-field-hover",
        secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/80",
        ghost: "hover:bg-accent hover:text-accent-foreground",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-8 px-3",
        lg: "h-11 px-6",
        icon: "size-10",
        "icon-sm": "size-8",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

/** Shown instead of a button's icon while what it started still runs. */
export function Spinner() {
  return (
    <LoaderCircleIcon data-spinner="" className="motion-safe:animate-spin" aria-hidden="true" />
  );
}

/** While busy, the spinner takes the place of the button's own icons. */
export const BUSY_ICONS = "[&>svg:not([data-spinner])]:hidden";

export interface ButtonProps
  extends Omit<ComponentProps<"button">, "onClick">, VariantProps<typeof buttonVariants> {
  readonly asChild?: boolean;
  /**
   * A promise returned here locks the button until it settles: further clicks do nothing
   * meanwhile, and a spinner shows. Its failure is the action's to report (e.g. a mutation's
   * onError or error state), the button only unlocks again.
   */
  readonly onClick?: ((event: MouseEvent<HTMLButtonElement>) => unknown) | undefined;
  /** Something this button started elsewhere (e.g. its form's submit) still runs. */
  readonly busy?: boolean | undefined;
}

export function Button({
  className,
  variant,
  size,
  asChild = false,
  type,
  onClick,
  busy = false,
  disabled,
  children,
  ...props
}: ButtonProps) {
  const once = useRunOnce();
  const working = busy || once.busy;
  const Component = asChild ? Slot : "button";
  return (
    <Component
      data-slot="button"
      className={cn(buttonVariants({ variant, size }), working && BUSY_ICONS, className)}
      {...(asChild ? {} : { type: type ?? "button" })}
      // A link (asChild) keeps its own attributes; it starts nothing that could run twice.
      {...(asChild ? { disabled } : { disabled: disabled === true || working })}
      aria-busy={working || undefined}
      onClick={
        onClick === undefined
          ? undefined
          : (event: MouseEvent<HTMLButtonElement>) => {
              once
                .run(async () => {
                  await onClick(event);
                })
                .catch(() => undefined);
            }
      }
      {...props}
    >
      {/* A link (asChild) takes exactly one child: its own element. */}
      {asChild ? (
        children
      ) : (
        <>
          {working ? <Spinner /> : null}
          {children}
        </>
      )}
    </Component>
  );
}
