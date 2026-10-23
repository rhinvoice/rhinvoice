import { describe, expect, it } from "vitest";

import {
  isEditableTarget,
  isInFormOrOverlay,
  isMacPlatform,
  isModified,
  isPlainKey,
  modifierLabel,
  type KeyEventLike,
} from "@/lib/shortcuts";

function key(value: string, overrides: Partial<KeyEventLike> = {}): KeyEventLike {
  return {
    key: value,
    metaKey: false,
    ctrlKey: false,
    altKey: false,
    shiftKey: false,
    target: document.body,
    ...overrides,
  };
}

function input(type: string): HTMLInputElement {
  const element = document.createElement("input");
  element.type = type;
  return element;
}

describe("isInFormOrOverlay", () => {
  it("detects targets in forms, dialogs, menus and lists", () => {
    for (const container of [
      document.createElement("form"),
      ...["dialog", "alertdialog", "menu", "listbox"].map((role) => {
        const element = document.createElement("div");
        element.setAttribute("role", role);
        return element;
      }),
    ]) {
      const checkbox = input("checkbox");
      container.append(checkbox);
      expect(isInFormOrOverlay(checkbox)).toBe(true);
      expect(isPlainKey(key("a", { target: checkbox }), "a")).toBe(false);
    }
  });

  it("ignores other targets", () => {
    expect(isInFormOrOverlay(document.body)).toBe(false);
    expect(isInFormOrOverlay(null)).toBe(false);
    expect(isInFormOrOverlay(window)).toBe(false);
  });
});

describe("isEditableTarget", () => {
  it("detects editable elements", () => {
    expect(isEditableTarget(input("text"))).toBe(true);
    expect(isEditableTarget(input("email"))).toBe(true);
    expect(isEditableTarget(document.createElement("textarea"))).toBe(true);
    expect(isEditableTarget(document.createElement("select"))).toBe(true);
    const editable = document.createElement("div");
    editable.contentEditable = "true";
    Object.defineProperty(editable, "isContentEditable", { value: true });
    expect(isEditableTarget(editable)).toBe(true);
    const combobox = document.createElement("button");
    combobox.setAttribute("role", "combobox");
    expect(isEditableTarget(combobox)).toBe(true);
  });

  it("ignores non-editable targets", () => {
    expect(isEditableTarget(input("checkbox"))).toBe(false);
    expect(isEditableTarget(document.createElement("button"))).toBe(false);
    expect(isEditableTarget(null)).toBe(false);
    expect(isEditableTarget(window)).toBe(false);
  });
});

describe("platform helpers", () => {
  it("detects Apple platforms", () => {
    expect(isMacPlatform("MacIntel")).toBe(true);
    expect(isMacPlatform("iPhone")).toBe(true);
    expect(isMacPlatform("Win32")).toBe(false);
    expect(modifierLabel("MacIntel")).toBe("⌘");
    expect(modifierLabel("Linux x86_64")).toBe("Ctrl");
  });

  it("matches the platform modifier", () => {
    expect(isModified(key("k", { metaKey: true }), "k", "MacIntel")).toBe(true);
    expect(isModified(key("K", { metaKey: true }), "k", "MacIntel")).toBe(true);
    expect(isModified(key("k", { ctrlKey: true }), "k", "MacIntel")).toBe(false);
    expect(isModified(key("k", { ctrlKey: true }), "k", "Win32")).toBe(true);
    expect(isModified(key("k", { ctrlKey: true, altKey: true }), "k", "Win32")).toBe(false);
    expect(isModified(key("j", { ctrlKey: true }), "k", "Win32")).toBe(false);
  });

  it("matches plain keys outside of inputs only", () => {
    expect(isPlainKey(key("n"), "n")).toBe(true);
    expect(isPlainKey(key("m"), "n")).toBe(false);
    expect(isPlainKey(key("n", { metaKey: true }), "n")).toBe(false);
    expect(isPlainKey(key("n", { ctrlKey: true }), "n")).toBe(false);
    expect(isPlainKey(key("n", { altKey: true }), "n")).toBe(false);
    expect(isPlainKey(key("n", { target: input("text") }), "n")).toBe(false);
    expect(isPlainKey(key("?", { shiftKey: true }), "?")).toBe(true);
    expect(isPlainKey(key("N"), "n")).toBe(true);
  });
});
