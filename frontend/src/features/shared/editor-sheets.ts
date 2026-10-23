import { createContext, useContext } from "react";

import type { components } from "@/api/client";

type Customer = components["schemas"]["CustomerResponse"];

/**
 * Forms the document editor opens on top of the invoice, so a missing customer, bank
 * account or tax ID never sends the user away from it. They belong to other features;
 * the app provides them.
 */
export interface EditorSheets {
  /** Create a customer named ``name``; null when closed without saving. */
  readonly createCustomer: (name: string) => Promise<Customer | null>;
  readonly editCustomer: (id: string) => Promise<void>;
  readonly addBankAccount: (currency: "CHF" | "EUR") => Promise<void>;
  readonly editCompanyTaxIds: () => Promise<void>;
}

export const EditorSheetsContext = createContext<EditorSheets | null>(null);

/** The sheets of the app; null outside of it (then the editor offers none). */
export function useEditorSheets(): EditorSheets | null {
  return useContext(EditorSheetsContext);
}
