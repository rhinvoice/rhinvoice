import { keepPreviousData, queryOptions, useMutation, useQueryClient } from "@tanstack/react-query";

import { api, unwrap, type components } from "@/api/client";

export type Customer = components["schemas"]["CustomerResponse"];
export type CustomerRequest = components["schemas"]["CustomerRequest"];
export type CustomerSort = components["schemas"]["CustomerSort"];
export type SortDirection = components["schemas"]["SortDirection"];

export interface CustomerListParams {
  readonly q: string;
  readonly includeArchived: boolean;
  readonly sort: CustomerSort;
  readonly direction: SortDirection;
  readonly offset: number;
  readonly limit: number;
}

export const customerKeys = {
  all: ["customers"] as const,
  list: (params: CustomerListParams) => ["customers", "list", params] as const,
  detail: (id: string) => ["customers", "detail", id] as const,
};

export function customerListQuery(params: CustomerListParams) {
  return queryOptions({
    queryKey: customerKeys.list(params),
    queryFn: () =>
      unwrap(
        api.GET("/api/customers", {
          params: {
            query: {
              q: params.q,
              include_archived: params.includeArchived,
              sort: params.sort,
              direction: params.direction,
              limit: params.limit,
              offset: params.offset,
            },
          },
        }),
      ),
    placeholderData: keepPreviousData,
  });
}

export function customerQuery(id: string) {
  return queryOptions({
    queryKey: customerKeys.detail(id),
    queryFn: () =>
      unwrap(api.GET("/api/customers/{customer_id}", { params: { path: { customer_id: id } } })),
  });
}

function useInvalidateOnSuccess() {
  const client = useQueryClient();
  return (customer: Customer) => {
    client.setQueryData(customerKeys.detail(customer.id), customer);
    void client.invalidateQueries({ queryKey: [...customerKeys.all, "list"] });
  };
}

export function useCreateCustomer() {
  const onSuccess = useInvalidateOnSuccess();
  return useMutation({
    mutationFn: (body: CustomerRequest) => unwrap(api.POST("/api/customers", { body })),
    onSuccess,
  });
}

export function useUpdateCustomer(id: string) {
  const onSuccess = useInvalidateOnSuccess();
  return useMutation({
    mutationFn: (body: CustomerRequest) =>
      unwrap(
        api.PUT("/api/customers/{customer_id}", { params: { path: { customer_id: id } }, body }),
      ),
    onSuccess,
  });
}

/**
 * Archive or restore optimistically: the page shows the new state at once and
 * rolls back if the server refuses (principles.md 4.7).
 */
export function useArchiveCustomer() {
  const client = useQueryClient();
  const onSuccess = useInvalidateOnSuccess();
  return useMutation({
    mutationFn: ({ id, archived }: { id: string; archived: boolean }) =>
      archived
        ? unwrap(
            api.POST("/api/customers/{customer_id}/archive", {
              params: { path: { customer_id: id } },
            }),
          )
        : unwrap(
            api.POST("/api/customers/{customer_id}/restore", {
              params: { path: { customer_id: id } },
            }),
          ),
    onMutate: async ({ id, archived }) => {
      const key = customerKeys.detail(id);
      await client.cancelQueries({ queryKey: key });
      const previous = client.getQueryData<Customer>(key);
      if (previous !== undefined) client.setQueryData<Customer>(key, { ...previous, archived });
      return { previous };
    },
    onError: (_error, { id }, context) => {
      if (context?.previous !== undefined)
        client.setQueryData(customerKeys.detail(id), context.previous);
    },
    onSuccess,
  });
}
