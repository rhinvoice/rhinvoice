/** localStorage access that never throws (private mode, disabled storage). */

function defaultStorage(): Storage | null {
  try {
    return globalThis.localStorage;
  } catch {
    // Accessing localStorage itself throws when storage is blocked.
    return null;
  }
}

export function readStorage(
  key: string,
  storage: Storage | null = defaultStorage(),
): string | null {
  if (storage === null) {
    return null;
  }
  try {
    return storage.getItem(key);
  } catch {
    return null;
  }
}

export function writeStorage(
  key: string,
  value: string,
  storage: Storage | null = defaultStorage(),
): void {
  if (storage === null) {
    return;
  }
  try {
    storage.setItem(key, value);
  } catch {
    // Storage is a convenience only; the app keeps working without it.
  }
}
