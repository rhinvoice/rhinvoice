import { queryOptions, useMutation, useQueryClient } from "@tanstack/react-query";

import { api, unwrap, type components } from "@/api/client";

export type Sequence = components["schemas"]["SequenceResponse"];
export type SequenceRequest = components["schemas"]["SequenceRequest"];
export type SequenceKind = components["schemas"]["SequenceKind"];

export const sequencesQuery = queryOptions({
  queryKey: ["number-sequences"],
  queryFn: () => unwrap(api.GET("/api/number-sequences")),
});

export function sequencePreviewQuery(kind: SequenceKind, body: SequenceRequest) {
  return queryOptions({
    queryKey: ["number-sequences", "preview", kind, body],
    queryFn: () =>
      unwrap(
        api.POST("/api/number-sequences/{kind}/preview", { params: { path: { kind } }, body }),
      ),
    retry: false,
  });
}

export function useSaveSequence(kind: SequenceKind) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: SequenceRequest) =>
      unwrap(api.PUT("/api/number-sequences/{kind}", { params: { path: { kind } }, body })),
    onSuccess: () => client.invalidateQueries({ queryKey: ["number-sequences"] }),
  });
}
