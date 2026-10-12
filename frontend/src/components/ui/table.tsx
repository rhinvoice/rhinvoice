import { ArrowDownIcon, ArrowUpDownIcon, ArrowUpIcon } from "lucide-react";
import type { ComponentProps, ReactNode } from "react";

import { cn } from "@/lib/cn";

interface TableProps extends ComponentProps<"table"> {
  /**
   * Name of the scroll area for tables that may be wider than the screen: the area
   * becomes a labelled region that can be focused and scrolled with the keyboard.
   */
  readonly scrollLabel?: string;
}

export function Table({ className, scrollLabel, ...props }: TableProps) {
  return (
    <div
      className="relative w-full overflow-x-auto rounded-xl border border-border/70 bg-card shadow-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
      {...(scrollLabel === undefined
        ? {}
        : {
            role: "region",
            "aria-label": scrollLabel,
            // A scrolling region must be reachable by keyboard (WCAG 2.1.1, axe
            // scrollable-region-focusable).
            tabIndex: 0,
          })}
    >
      <table
        className={cn("w-full caption-bottom border-collapse text-sm", className)}
        {...props}
      />
    </div>
  );
}

export function TableHeader(props: ComponentProps<"thead">) {
  return <thead className="bg-muted/50 [&_tr]:border-b" {...props} />;
}

export function TableBody(props: ComponentProps<"tbody">) {
  return <tbody className="[&_tr:last-child]:border-0" {...props} />;
}

export function TableRow({ className, ...props }: ComponentProps<"tr">) {
  return (
    <tr
      className={cn(
        "border-b transition-colors hover:bg-muted/40 has-[a:focus-visible]:bg-muted/40",
        className,
      )}
      {...props}
    />
  );
}

export function TableHead({ className, ...props }: ComponentProps<"th">) {
  return (
    <th
      scope="col"
      className={cn(
        "h-10 px-3 text-left align-middle text-xs font-medium whitespace-nowrap text-muted-foreground",
        className,
      )}
      {...props}
    />
  );
}

export function TableCell({ className, ...props }: ComponentProps<"td">) {
  return <td className={cn("h-11 px-3 align-middle", className)} {...props} />;
}

export type SortState = "ascending" | "descending" | "none";

interface SortableHeadProps {
  readonly children: ReactNode;
  readonly state: SortState;
  readonly onSort: () => void;
  readonly className?: string;
}

/** Column header that sorts on click; the state is exposed via aria-sort. */
export function SortableHead({ children, state, onSort, className }: SortableHeadProps) {
  const Icon =
    state === "ascending" ? ArrowUpIcon : state === "descending" ? ArrowDownIcon : ArrowUpDownIcon;
  return (
    <TableHead aria-sort={state} className={cn("px-1", className)}>
      <button
        type="button"
        onClick={onSort}
        className="inline-flex min-h-8 items-center gap-1 rounded-sm px-2 hover:text-foreground"
      >
        {children}
        <Icon className={cn("size-3.5", state === "none" && "opacity-50")} aria-hidden="true" />
      </button>
    </TableHead>
  );
}
