/**
 * Which parts of the page hold changes that are not saved yet. Closing the program for an
 * update asks about them first (ADR 0031); a form says so with useUnsavedChanges.
 */
export interface UnsavedChanges {
  /** Tell whether ``owner`` holds unsaved changes; false forgets it. */
  readonly mark: (owner: object, unsaved: boolean) => void;
  readonly any: () => boolean;
  /** Call ``listener`` after every change of any(); returns the unsubscribe. */
  readonly subscribe: (listener: () => void) => () => void;
}

export function createUnsavedChanges(): UnsavedChanges {
  const owners = new Set<object>();
  const listeners = new Set<() => void>();
  return {
    mark(owner, unsaved) {
      const before = owners.size > 0;
      if (unsaved) {
        owners.add(owner);
      } else {
        owners.delete(owner);
      }
      if (owners.size > 0 !== before) {
        for (const listener of listeners) listener();
      }
    },
    any: () => owners.size > 0,
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}

/** The page's one record. */
export const unsavedChanges = createUnsavedChanges();
