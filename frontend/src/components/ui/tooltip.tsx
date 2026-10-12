import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import type { ComponentProps, ReactNode } from "react";

import { cn } from "@/lib/cn";

export const TooltipProvider = TooltipPrimitive.Provider;

interface TooltipProps {
  readonly content: ReactNode;
  readonly children: ReactNode;
  readonly side?: ComponentProps<typeof TooltipPrimitive.Content>["side"];
}

/** A tooltip for supplementary information; never the only carrier of a label. */
export function Tooltip({ content, children, side = "bottom" }: TooltipProps) {
  return (
    <TooltipPrimitive.Root>
      <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Content
          side={side}
          sideOffset={6}
          className={cn(
            "z-50 flex animate-in items-center gap-2 rounded-md bg-foreground px-2 py-1 text-xs text-background shadow-md duration-150 fade-in-0 zoom-in-95 data-[state=closed]:animate-out data-[state=closed]:fade-out-0",
          )}
        >
          {content}
        </TooltipPrimitive.Content>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  );
}
