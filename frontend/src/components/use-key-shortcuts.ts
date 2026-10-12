import { useEffect, useRef } from "react";

import { useSingleKeyShortcuts } from "@/components/use-single-key-shortcuts";
import { isModified, isPlainKey } from "@/lib/shortcuts";

/** ⌘↵ / Ctrl+↵ saves, also while an input has focus. */
export function useSaveShortcut(onSave: () => void, enabled = true): void {
  const latest = useRef(onSave);
  useEffect(() => {
    latest.current = onSave;
  });
  useEffect(() => {
    if (!enabled) return undefined;
    const listener = (event: KeyboardEvent) => {
      if (isModified(event, "Enter", navigator.platform)) {
        event.preventDefault();
        latest.current();
      }
    };
    window.addEventListener("keydown", listener);
    return () => {
      window.removeEventListener("keydown", listener);
    };
  }, [enabled]);
}

/**
 * A page specific single-key shortcut (e.g. "c" for a new customer). Respects
 * the user's preference and never fires while typing (WCAG 2.1.4).
 */
export function usePageShortcut(key: string, handler: () => void): void {
  const [singleKeys] = useSingleKeyShortcuts();
  const latest = useRef(handler);
  useEffect(() => {
    latest.current = handler;
  });
  useEffect(() => {
    if (!singleKeys) return undefined;
    const listener = (event: KeyboardEvent) => {
      if (!event.defaultPrevented && isPlainKey(event, key)) {
        event.preventDefault();
        latest.current();
      }
    };
    window.addEventListener("keydown", listener);
    return () => {
      window.removeEventListener("keydown", listener);
    };
  }, [key, singleKeys]);
}
