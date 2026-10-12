import { toast } from "sonner";

import { createUndoRegistry } from "@/lib/undo";

/** Undo toasts stay 10 s instead of the default 4 s (WCAG 2.2.1, principles.md 4.7). */
export const UNDO_DURATION_MS = 10_000;

/** The undo of the newest visible undo toast, also reachable with ⌘Z / Ctrl+Z. */
export const undoRegistry = createUndoRegistry();

/** A success toast with an "Undo" button; the undo runs at most once. */
export function showUndoToast(message: string, undoLabel: string, onUndo: () => void): void {
  let done = false;
  const undo = () => {
    if (done) return;
    done = true;
    withdraw();
    toast.dismiss(id);
    onUndo();
  };
  const withdraw = undoRegistry.register(undo);
  const id = toast.success(message, {
    duration: UNDO_DURATION_MS,
    action: { label: undoLabel, onClick: undo },
    onDismiss: withdraw,
    onAutoClose: withdraw,
  });
}
