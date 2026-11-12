import { keepPreviousData, queryOptions, useMutation, useQueryClient } from "@tanstack/react-query";

import { api, CLIENT_HEADER, unwrap, type components } from "@/api/client";
import { PRINT_LAYOUTS_KEY, companyKeys, type PrintLayout } from "@/features/shared/company-api";
import type { DownloadedFile } from "@/features/shared/file-download";
import { toApiError } from "@/lib/api-error";
import { useIdempotentMutation } from "@/features/shared/use-idempotent-mutation";

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
  return useIdempotentMutation({
    mutationFn: (body: BankAccountRequest, { headers }) =>
      id === null
        ? unwrap(api.POST("/api/bank-accounts", { body, headers }))
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

/** The latest invoice (or a sample) laid out with a layout that is not saved yet. */
export function printLayoutPreviewQuery(layout: PrintLayout | null) {
  return queryOptions({
    queryKey: [...PRINT_LAYOUTS_KEY, "preview", layout] as const,
    queryFn: () => {
      if (layout === null) throw new Error("the preview is disabled without a layout");
      return unwrap(api.POST("/api/print-layouts/preview", { body: layout, parseAs: "text" }));
    },
    enabled: layout !== null,
    placeholderData: keepPreviousData,
    staleTime: 60_000,
    retry: false,
  });
}

/** The latest invoice with a layout as a PDF marked as a sample, to send before switching. */
export async function fetchSamplePdf(layout: PrintLayout, name: string): Promise<DownloadedFile> {
  let response: Response;
  try {
    response = await fetch("/api/print-layouts/sample", {
      method: "POST",
      body: JSON.stringify(layout),
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", [CLIENT_HEADER]: "web" },
    });
  } catch {
    throw toApiError(0, undefined);
  }
  if (!response.ok) {
    throw toApiError(response.status, await response.json().catch(() => undefined));
  }
  return { blob: await response.blob(), name };
}

/** Documents look different after a change: their previews are rendered anew. */
function useLayoutsChanged() {
  const client = useQueryClient();
  return () => {
    void client.invalidateQueries({ queryKey: PRINT_LAYOUTS_KEY });
    void client.invalidateQueries({ queryKey: ["documents"] });
    // A deleted layout leaves its customers with the default.
    void client.invalidateQueries({ queryKey: ["customers"] });
  };
}

export function useCreatePrintLayout() {
  const changed = useLayoutsChanged();
  return useIdempotentMutation({
    mutationFn: (body: { name: string; copy_of: string | null }, { headers }) =>
      unwrap(api.POST("/api/print-layouts", { body, headers })),
    onSuccess: changed,
  });
}

export function useSavePrintLayout() {
  const changed = useLayoutsChanged();
  return useMutation({
    mutationFn: ({ id, name, layout }: { id: string; name: string; layout: PrintLayout }) =>
      unwrap(
        api.PUT("/api/print-layouts/{layout_id}", {
          params: { path: { layout_id: id } },
          body: { name, layout },
        }),
      ),
    onSuccess: changed,
  });
}

export function useMakeDefaultPrintLayout() {
  const changed = useLayoutsChanged();
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(
        api.POST("/api/print-layouts/{layout_id}/default", {
          params: { path: { layout_id: id } },
        }),
      ),
    onSuccess: changed,
  });
}

export function useDeletePrintLayout() {
  const changed = useLayoutsChanged();
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(api.DELETE("/api/print-layouts/{layout_id}", { params: { path: { layout_id: id } } })),
    onSuccess: changed,
  });
}
