import { keepPreviousData, queryOptions, useMutation, useQueryClient } from "@tanstack/react-query";

import { api, CLIENT_HEADER, unwrap, type components } from "@/api/client";
import { companyKeys } from "@/features/shared/company-api";
import { toApiError } from "@/lib/api-error";

export type CompanyRequest = components["schemas"]["CompanyRequest"];
export type BankAccountRequest = components["schemas"]["BankAccountRequest"];
export type { BankAccount, Company } from "@/features/shared/company-api";
export { bankAccountsQuery, companyKeys, companyQuery } from "@/features/shared/company-api";

/** Object URL of the uploaded logo, or null. */
export const logoQuery = queryOptions({
  queryKey: companyKeys.logo,
  queryFn: async (): Promise<string | null> => {
    const response = await fetch("/api/company/logo", { credentials: "same-origin" });
    if (response.status === 404) return null;
    if (!response.ok)
      throw toApiError(response.status, await response.json().catch(() => undefined));
    return URL.createObjectURL(await response.blob());
  },
});

export function useSaveCompany() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: CompanyRequest) => unwrap(api.PUT("/api/company", { body })),
    onSuccess: (company) => {
      client.setQueryData(companyKeys.company, company);
    },
  });
}

export function useUploadLogo() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (file: File) => {
      const body = new FormData();
      body.append("file", file);
      const response = await fetch("/api/company/logo", {
        method: "PUT",
        body,
        credentials: "same-origin",
        headers: { [CLIENT_HEADER]: "web" },
      });
      if (!response.ok)
        throw toApiError(response.status, await response.json().catch(() => undefined));
    },
    onSuccess: () => client.invalidateQueries({ queryKey: companyKeys.logo }),
  });
}

export function useDeleteLogo() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.DELETE("/api/company/logo")),
    onSuccess: () => {
      client.setQueryData(companyKeys.logo, null);
    },
  });
}

export function useSaveBankAccount(id: string | null) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: BankAccountRequest) =>
      id === null
        ? unwrap(api.POST("/api/bank-accounts", { body }))
        : unwrap(
            api.PUT("/api/bank-accounts/{account_id}", {
              params: { path: { account_id: id } },
              body,
            }),
          ),
    onSuccess: () => client.invalidateQueries({ queryKey: companyKeys.bankAccounts }),
  });
}

export function useDeleteBankAccount() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(
        api.DELETE("/api/bank-accounts/{account_id}", { params: { path: { account_id: id } } }),
      ),
    onSuccess: () => client.invalidateQueries({ queryKey: companyKeys.bankAccounts }),
  });
}

export type PrintLayout = components["schemas"]["PrintLayoutSchema"];

const PRINT_LAYOUT_KEY = ["print-layout"] as const;

export const printLayoutQuery = queryOptions({
  queryKey: PRINT_LAYOUT_KEY,
  queryFn: () => unwrap(api.GET("/api/print-layout")),
});

/** The latest invoice (or a sample) laid out with a layout that is not saved yet. */
export function printLayoutPreviewQuery(layout: PrintLayout | null) {
  return queryOptions({
    queryKey: [...PRINT_LAYOUT_KEY, "preview", layout] as const,
    queryFn: () => {
      if (layout === null) throw new Error("the preview is disabled without a layout");
      return unwrap(api.POST("/api/print-layout/preview", { body: layout, parseAs: "text" }));
    },
    enabled: layout !== null,
    placeholderData: keepPreviousData,
    staleTime: 60_000,
    retry: false,
  });
}

export function useSavePrintLayout() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: PrintLayout) => unwrap(api.PUT("/api/print-layout", { body })),
    onSuccess: (layout) => {
      client.setQueryData(PRINT_LAYOUT_KEY, layout);
      // Documents look different now: previews are rendered anew.
      void client.invalidateQueries({ queryKey: ["documents"] });
    },
  });
}
