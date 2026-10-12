import { Toaster as Sonner, type ToasterProps } from "sonner";

/**
 * Toasts: bottom right on desktop, max. 3 visible. Undo toasts use a 10 s
 * duration (WCAG 2.2.1), error toasts stay until dismissed.
 */
export function Toaster({ theme, ...props }: ToasterProps) {
  return (
    <Sonner
      {...(theme === undefined ? {} : { theme })}
      position="bottom-right"
      visibleToasts={3}
      // Show toasts side by side instead of a scaled stack: every toast and its
      // buttons stay fully visible and at least 24 px large (WCAG 2.5.8).
      expand
      // Above the mobile tab bar (4rem) so toasts never cover navigation.
      mobileOffset={{ bottom: "5rem" }}
      closeButton
      toastOptions={{
        classNames: {
          toast:
            "bg-popover! text-popover-foreground! border-border! shadow-md! rounded-lg! font-sans!",
          description: "text-muted-foreground!",
          actionButton: "bg-primary! text-primary-foreground! min-h-8! px-3!",
          // At least 24 × 24 px (WCAG 2.5.8); Sonner's default is 20 px.
          closeButton: "size-6! bg-popover! text-popover-foreground! border-border!",
        },
      }}
      {...props}
    />
  );
}
