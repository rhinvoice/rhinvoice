/** Keyboard shortcut helpers (single key shortcuts must not fire while typing, WCAG 2.1.4). */

/** "off" disables single-key shortcuts; ⌘K / Ctrl+K stays available. */
export const SINGLE_KEY_SHORTCUTS_STORAGE_KEY = "rhinvoice.single-key-shortcuts";

export interface KeyEventLike {
  readonly key: string;
  readonly metaKey: boolean;
  readonly ctrlKey: boolean;
  readonly altKey: boolean;
  readonly shiftKey: boolean;
  readonly target: EventTarget | null;
}

const EDITABLE_INPUT_TYPES = new Set([
  "text",
  "search",
  "email",
  "password",
  "number",
  "tel",
  "url",
  "date",
  "datetime-local",
  "month",
  "time",
  "week",
]);

export function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  if (target.isContentEditable) {
    return true;
  }
  if (target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement) {
    return true;
  }
  if (target instanceof HTMLInputElement) {
    return EDITABLE_INPUT_TYPES.has(target.type);
  }
  return target.getAttribute("role") === "combobox";
}

/** Forms and open overlays keep their keys, so a letter there never leaves the page. */
const KEEPS_KEYS = 'form, [role="dialog"], [role="alertdialog"], [role="menu"], [role="listbox"]';

export function isInFormOrOverlay(target: EventTarget | null): boolean {
  return target instanceof Element && target.closest(KEEPS_KEYS) !== null;
}

export function isMacPlatform(platform: string): boolean {
  return /mac|iphone|ipad|ipod/i.test(platform);
}

/** "⌘" on Apple platforms, "Ctrl" elsewhere. */
export function modifierLabel(platform: string): string {
  return isMacPlatform(platform) ? "⌘" : "Ctrl";
}

/** True for ⌘+key on macOS and Ctrl+key elsewhere. */
export function isModified(event: KeyEventLike, key: string, platform: string): boolean {
  const modifier = isMacPlatform(platform) ? event.metaKey : event.ctrlKey;
  return modifier && !event.altKey && event.key.toLowerCase() === key.toLowerCase();
}

/** A plain key press without modifiers, outside of editable fields, forms and overlays. */
export function isPlainKey(event: KeyEventLike, key: string): boolean {
  return (
    // Case-insensitive, so that the shortcuts also work with Caps Lock.
    event.key.toLowerCase() === key.toLowerCase() &&
    !event.metaKey &&
    !event.ctrlKey &&
    !event.altKey &&
    !isEditableTarget(event.target) &&
    !isInFormOrOverlay(event.target)
  );
}
