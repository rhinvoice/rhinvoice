import { useEffect, useRef } from "react";

import { isEditableTarget, isModified, isPlainKey, type KeyEventLike } from "@/lib/shortcuts";

export interface GlobalShortcutHandlers {
  readonly openPalette: () => void;
  readonly openHelp: () => void;
  readonly newInvoice: () => void;
  readonly newQuote: () => void;
  readonly newCustomer: () => void;
  readonly newArticle: () => void;
  /** Run the undo of the visible undo toast; false when there is none. */
  readonly undo: () => boolean;
  readonly focusSearch: () => void;
  readonly goTo: (key: string) => boolean;
}

const CREATE_KEYS: readonly (readonly [
  string,
  "newInvoice" | "newQuote" | "newCustomer" | "newArticle",
])[] = [
  ["i", "newInvoice"],
  ["n", "newInvoice"],
  ["q", "newQuote"],
  ["c", "newCustomer"],
  ["a", "newArticle"],
];

/** How long the "G" prefix of a two-key navigation shortcut stays armed. */
export const GO_PREFIX_TIMEOUT_MS = 1500;

/**
 * Global keyboard shortcuts. Single-key shortcuts are ignored while an input
 * has focus (WCAG 2.1.4); ⌘K / Ctrl+K works everywhere.
 */
export function handleShortcut(
  event: KeyEventLike,
  handlers: GlobalShortcutHandlers,
  platform: string,
  goPending: boolean,
  singleKeys = true,
): { readonly handled: boolean; readonly goPending: boolean } {
  if (isModified(event, "k", platform)) {
    handlers.openPalette();
    return { handled: true, goPending: false };
  }
  // ⌘Z / Ctrl+Z outside of inputs (inputs keep their own undo).
  if (isModified(event, "z", platform) && !event.shiftKey && !isEditableTarget(event.target)) {
    return { handled: handlers.undo(), goPending: false };
  }
  if (!singleKeys) {
    return { handled: false, goPending: false };
  }
  if (goPending && isPlainKey(event, event.key)) {
    return { handled: handlers.goTo(event.key.toLowerCase()), goPending: false };
  }
  if (isPlainKey(event, "g")) {
    return { handled: true, goPending: true };
  }
  if (isPlainKey(event, "?")) {
    handlers.openHelp();
    return { handled: true, goPending: false };
  }
  // One letter per thing: alone it creates one, after "G" it opens the list.
  // "N" stays as the familiar second key for a new invoice.
  const create = CREATE_KEYS.find(([key]) => isPlainKey(event, key));
  if (create !== undefined) {
    handlers[create[1]]();
    return { handled: true, goPending: false };
  }
  if (isPlainKey(event, "/")) {
    handlers.focusSearch();
    return { handled: true, goPending: false };
  }
  return { handled: false, goPending: false };
}

export function useGlobalShortcuts(
  handlers: GlobalShortcutHandlers,
  { enabled = true, singleKeys = true }: { enabled?: boolean; singleKeys?: boolean } = {},
): void {
  const latest = useRef(handlers);
  useEffect(() => {
    latest.current = handlers;
  });

  useEffect(() => {
    if (!enabled) {
      return undefined;
    }
    let goPending = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const listener = (event: KeyboardEvent) => {
      if (event.defaultPrevented) {
        return;
      }
      const result = handleShortcut(
        event,
        latest.current,
        navigator.platform,
        goPending,
        singleKeys,
      );
      goPending = result.goPending;
      clearTimeout(timer);
      if (goPending) {
        timer = setTimeout(() => {
          goPending = false;
        }, GO_PREFIX_TIMEOUT_MS);
      }
      if (result.handled) {
        event.preventDefault();
      }
    };
    window.addEventListener("keydown", listener);
    return () => {
      clearTimeout(timer);
      window.removeEventListener("keydown", listener);
    };
  }, [enabled, singleKeys]);
}
