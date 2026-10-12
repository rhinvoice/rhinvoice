import { readStorage, writeStorage } from "@/lib/storage";

const KEY = "rhinvoice.setup-deferred";

/** Without storage (private mode) the choice holds until the page is reloaded. */
let deferredInMemory = false;

/**
 * "Set up later" in the first-start wizard: the dashboard no longer sends this
 * browser to the wizard; its checklist keeps the step.
 */
export function deferSetup(storage?: Storage | null): void {
  deferredInMemory = true;
  writeStorage(KEY, "1", storage);
}

export function isSetupDeferred(storage?: Storage | null): boolean {
  return deferredInMemory || readStorage(KEY, storage) === "1";
}

/** For tests: forget the choice of this page. */
export function resetSetupDeferral(): void {
  deferredInMemory = false;
}
