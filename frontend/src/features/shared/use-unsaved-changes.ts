import { useEffect, useRef, useSyncExternalStore } from "react";

import { unsavedChanges } from "@/lib/unsaved-changes";

/** Tell the page that this form holds changes not saved yet (lib/unsaved-changes). */
export function useUnsavedChanges(unsaved: boolean): void {
  const owner = useRef({});
  useEffect(() => {
    const current = owner.current;
    unsavedChanges.mark(current, unsaved);
    return () => {
      unsavedChanges.mark(current, false);
    };
  }, [unsaved]);
}

/** Whether any form on the page holds unsaved changes. */
export function useHasUnsavedChanges(): boolean {
  return useSyncExternalStore(unsavedChanges.subscribe, unsavedChanges.any);
}
