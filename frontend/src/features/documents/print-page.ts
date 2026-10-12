/** Removed at the latest after this time, also when "afterprint" never fires. */
export const PRINT_FRAME_LIFETIME_MS = 10 * 60_000;

/**
 * Print a page of the print template with the browser's print dialog. The page
 * goes into an invisible frame that is removed afterwards; its print CSS makes
 * the result identical to the PDF. The frame runs no scripts: it may only be
 * printed from here (same origin) and show the print dialog (modals).
 */
export function printPage(html: string, ownerDocument: Document = document): void {
  const frame = ownerDocument.createElement("iframe");
  frame.setAttribute("sandbox", "allow-same-origin allow-modals");
  frame.setAttribute("aria-hidden", "true");
  frame.tabIndex = -1;
  frame.style.position = "fixed";
  frame.style.width = "0";
  frame.style.height = "0";
  frame.style.border = "0";
  frame.style.opacity = "0";
  const timer = setTimeout(() => {
    frame.remove();
  }, PRINT_FRAME_LIFETIME_MS);
  frame.addEventListener("load", () => {
    const view = frame.contentWindow;
    if (view === null) return;
    view.addEventListener("afterprint", () => {
      clearTimeout(timer);
      frame.remove();
    });
    view.focus();
    view.print();
  });
  frame.srcdoc = html;
  ownerDocument.body.append(frame);
}
