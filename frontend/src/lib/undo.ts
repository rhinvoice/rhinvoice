/**
 * The most recent undoable action, for ⌘Z / Ctrl+Z while its undo toast is
 * visible (principles.md 4.7). Registering a new action replaces the old one.
 */
export interface UndoRegistry {
  /** Make ``action`` the current undo; the returned function withdraws it again. */
  register(action: () => void): () => void;
  /** Run and forget the current undo; false when there is none. */
  trigger(): boolean;
}

export function createUndoRegistry(): UndoRegistry {
  let current: { readonly action: () => void } | null = null;
  return {
    register(action) {
      const entry = { action };
      current = entry;
      return () => {
        if (current === entry) current = null;
      };
    },
    trigger() {
      if (current === null) return false;
      const { action } = current;
      current = null;
      action();
      return true;
    },
  };
}
