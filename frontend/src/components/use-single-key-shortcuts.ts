import { useCallback, useSyncExternalStore } from "react";

import { SINGLE_KEY_SHORTCUTS_STORAGE_KEY } from "@/lib/shortcuts";
import { readStorage, writeStorage } from "@/lib/storage";

const CHANGE_EVENT = "rhinvoice:single-key-shortcuts";

function subscribe(callback: () => void): () => void {
  window.addEventListener(CHANGE_EVENT, callback);
  window.addEventListener("storage", callback);
  return () => {
    window.removeEventListener(CHANGE_EVENT, callback);
    window.removeEventListener("storage", callback);
  };
}

function enabledSnapshot(): boolean {
  return readStorage(SINGLE_KEY_SHORTCUTS_STORAGE_KEY) !== "off";
}

/** Per-browser preference for single-key shortcuts (WCAG 2.1.4), on by default. */
export function useSingleKeyShortcuts(): [boolean, (enabled: boolean) => void] {
  const enabled = useSyncExternalStore(subscribe, enabledSnapshot);
  const setEnabled = useCallback((value: boolean) => {
    writeStorage(SINGLE_KEY_SHORTCUTS_STORAGE_KEY, value ? "on" : "off");
    window.dispatchEvent(new Event(CHANGE_EVENT));
  }, []);
  return [enabled, setEnabled];
}
