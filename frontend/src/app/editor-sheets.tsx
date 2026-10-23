import { useQuery } from "@tanstack/react-query";
import { useMemo, useState, type ReactNode } from "react";

import { CompanyTaxDialog, NewBankAccountDialog } from "@/features/company/editor-dialogs";
import type { Customer } from "@/features/customers/api";
import { CustomerSheet } from "@/features/customers/customer-sheet";
import { companyQuery } from "@/features/shared/company-api";
import { EditorSheetsContext, type EditorSheets } from "@/features/shared/editor-sheets";

type Open =
  | {
      readonly kind: "customer";
      readonly id: string | null;
      readonly name: string;
      readonly done: (customer: Customer | null) => void;
    }
  | { readonly kind: "bank"; readonly currency: "CHF" | "EUR"; readonly done: () => void }
  | { readonly kind: "tax"; readonly done: () => void };

/** Customer, bank account and tax ID forms for the document editor (one at a time). */
export function EditorSheetsProvider({ children }: { readonly children: ReactNode }) {
  const [open, setOpen] = useState<Open | null>(null);
  const company = useQuery(companyQuery).data;
  const sheets = useMemo<EditorSheets>(
    () => ({
      createCustomer: (name) =>
        new Promise((resolve) => {
          setOpen({ kind: "customer", id: null, name, done: resolve });
        }),
      editCustomer: (id) =>
        new Promise((resolve) => {
          setOpen({
            kind: "customer",
            id,
            name: "",
            done: () => {
              resolve();
            },
          });
        }),
      addBankAccount: (currency) =>
        new Promise((resolve) => {
          setOpen({ kind: "bank", currency, done: resolve });
        }),
      editCompanyTaxIds: () =>
        new Promise((resolve) => {
          setOpen({ kind: "tax", done: resolve });
        }),
    }),
    [],
  );
  const close = () => {
    setOpen(null);
  };

  return (
    <EditorSheetsContext.Provider value={sheets}>
      {children}
      {open?.kind === "customer" ? (
        <CustomerSheet
          customerId={open.id}
          name={open.name}
          defaultCountry={company?.country ?? "CH"}
          onDone={(customer) => {
            close();
            open.done(customer);
          }}
        />
      ) : null}
      {open?.kind === "bank" ? (
        <NewBankAccountDialog
          currency={open.currency}
          onClose={() => {
            close();
            open.done();
          }}
        />
      ) : null}
      {open?.kind === "tax" ? (
        <CompanyTaxDialog
          onClose={() => {
            close();
            open.done();
          }}
        />
      ) : null}
    </EditorSheetsContext.Provider>
  );
}
