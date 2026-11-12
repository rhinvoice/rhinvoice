import { queryOptions } from "@tanstack/react-query";

import { api, unwrap, type components } from "@/api/client";
import { ApiError } from "@/lib/api-error";

/** Company queries that several features read; mutations live in features/company. */
export type Company = components["schemas"]["CompanyResponse"];
export type BankAccount = components["schemas"]["BankAccountResponse"];

export const companyKeys = {
  company: ["company"] as const,
  logo: ["company", "logo"] as const,
  bankAccounts: ["bank-accounts"] as const,
};

/** The company, or null while it has not been set up (API answers 404). */
export const companyQuery = queryOptions({
  queryKey: companyKeys.company,
  queryFn: async (): Promise<Company | null> => {
    try {
      return await unwrap(api.GET("/api/company"));
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) return null;
      throw error;
    }
  },
  staleTime: 5 * 60_000,
});

export const bankAccountsQuery = queryOptions({
  queryKey: companyKeys.bankAccounts,
  queryFn: () => unwrap(api.GET("/api/bank-accounts")),
});

export type PrintLayout = components["schemas"]["PrintLayoutSchema"];
export type NamedLayout = components["schemas"]["PrintLayoutResponse"];

export const PRINT_LAYOUTS_KEY = ["print-layouts"] as const;

/** The named print layouts, the default first (#48); the editor reads their fields. */
export const printLayoutsQuery = queryOptions({
  queryKey: PRINT_LAYOUTS_KEY,
  queryFn: () => unwrap(api.GET("/api/print-layouts")),
});
