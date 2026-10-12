import { useEffect } from "react";

/** Set document.title per page, e.g. "Kunden · Rhinvoice" (WCAG 2.4.2). */
export function useDocumentTitle(title: string): void {
  useEffect(() => {
    document.title = title;
  }, [title]);
}
