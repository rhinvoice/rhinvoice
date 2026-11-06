import * as AlertDialogPrimitive from "@radix-ui/react-alert-dialog";
import { useRef, type ComponentProps, type MouseEvent } from "react";

import { BUSY_ICONS, buttonVariants, Spinner } from "@/components/ui/button";
import { useRunOnce } from "@/components/use-run-once";
import { cn } from "@/lib/cn";

export const AlertDialog = AlertDialogPrimitive.Root;
export const AlertDialogTrigger = AlertDialogPrimitive.Trigger;

export function AlertDialogContent({
  className,
  ...props
}: ComponentProps<typeof AlertDialogPrimitive.Content>) {
  return (
    <AlertDialogPrimitive.Portal>
      <AlertDialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/50 duration-200 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:animate-in data-[state=open]:fade-in-0" />
      <AlertDialogPrimitive.Content
        className={cn(
          "fixed top-1/2 left-1/2 z-50 flex w-[calc(100%-2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2 flex-col gap-4 rounded-xl border bg-popover p-6 text-popover-foreground shadow-lg duration-200 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95",
          className,
        )}
        {...props}
      />
    </AlertDialogPrimitive.Portal>
  );
}

export function AlertDialogHeader({ className, ...props }: ComponentProps<"div">) {
  return <div className={cn("flex flex-col gap-2", className)} {...props} />;
}

export function AlertDialogFooter({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      className={cn("flex flex-col-reverse gap-2 sm:flex-row sm:justify-end", className)}
      {...props}
    />
  );
}

export function AlertDialogTitle({
  className,
  ...props
}: ComponentProps<typeof AlertDialogPrimitive.Title>) {
  return (
    <AlertDialogPrimitive.Title
      className={cn("text-lg leading-7 font-semibold", className)}
      {...props}
    />
  );
}

export function AlertDialogDescription({
  className,
  ...props
}: ComponentProps<typeof AlertDialogPrimitive.Description>) {
  return (
    <AlertDialogPrimitive.Description
      className={cn("text-sm text-muted-foreground", className)}
      {...props}
    />
  );
}

/**
 * The dialog's confirming button. It acts once per opening: the dialog stays clickable while
 * it closes, and a second click then would run the action again. An action that keeps the
 * dialog open (preventDefault) may run again once a promise it returns has settled.
 */
export function AlertDialogAction({
  className,
  destructive = false,
  onClick,
  disabled,
  children,
  ...props
}: Omit<ComponentProps<typeof AlertDialogPrimitive.Action>, "onClick"> & {
  readonly destructive?: boolean;
  readonly onClick?: ((event: MouseEvent<HTMLButtonElement>) => unknown) | undefined;
}) {
  const once = useRunOnce();
  const done = useRef(false);
  return (
    <AlertDialogPrimitive.Action
      className={cn(
        buttonVariants({ variant: destructive ? "destructive" : "default" }),
        once.busy && BUSY_ICONS,
        className,
      )}
      disabled={disabled === true || once.busy}
      aria-busy={once.busy || undefined}
      onClick={(event) => {
        const click = { started: false };
        if (!done.current) {
          once
            .run(async () => {
              click.started = true;
              await onClick?.(event);
            })
            .catch(() => undefined);
        }
        // The action runs synchronously up to its first await: whether it started is known here.
        if (!click.started) {
          event.preventDefault();
        } else if (!event.defaultPrevented) {
          done.current = true;
        }
      }}
      {...props}
    >
      {once.busy ? <Spinner /> : null}
      {children}
    </AlertDialogPrimitive.Action>
  );
}

export function AlertDialogCancel({
  className,
  ...props
}: ComponentProps<typeof AlertDialogPrimitive.Cancel>) {
  return (
    <AlertDialogPrimitive.Cancel
      className={cn(buttonVariants({ variant: "outline" }), className)}
      {...props}
    />
  );
}
