import { queryOptions, useMutation, useQueryClient } from "@tanstack/react-query";

import { api, CLIENT_HEADER, unwrap } from "@/api/client";
import type {
  ImportRun,
  ImportTarget,
  ImportTemplate,
  Mapping,
} from "@/features/importing/import-model";
import { toApiError } from "@/lib/api-error";

export type DuplicateStrategy = "skip" | "update" | "create";

export interface ImportOptions {
  readonly file: File;
  readonly duplicates: DuplicateStrategy;
  /** null: suggested from the column names. */
  readonly mapping: Mapping | null;
}

/** Test run (commit false) or import; multipart, so not through the generated client. */
export async function runImport(
  target: ImportTarget,
  options: ImportOptions,
  commit: boolean,
): Promise<ImportRun> {
  const body = new FormData();
  body.append("file", options.file);
  body.append("duplicates", options.duplicates);
  if (options.mapping !== null) {
    body.append("mapping", JSON.stringify(options.mapping));
  }
  let response: Response;
  try {
    response = await fetch(`/api/imports/${target}${commit ? "" : "/preview"}`, {
      method: "POST",
      body,
      credentials: "same-origin",
      headers: { [CLIENT_HEADER]: "web" },
    });
  } catch {
    throw toApiError(0, undefined);
  }
  if (!response.ok) {
    throw toApiError(response.status, await response.json().catch(() => undefined));
  }
  return (await response.json()) as ImportRun;
}

const templateKey = (target: ImportTarget) => ["import-templates", target];

export function templatesQuery(target: ImportTarget) {
  return queryOptions({
    queryKey: templateKey(target),
    queryFn: () =>
      unwrap(api.GET("/api/imports/{target}/templates", { params: { path: { target } } })),
  });
}

export function useSaveTemplate(target: ImportTarget) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; columns: Record<string, string> }) =>
      unwrap(api.POST("/api/imports/{target}/templates", { params: { path: { target } }, body })),
    onSuccess: () => client.invalidateQueries({ queryKey: templateKey(target) }),
  });
}

export function useDeleteTemplate(target: ImportTarget) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (template: ImportTemplate) =>
      unwrap(
        api.DELETE("/api/imports/templates/{template_id}", {
          params: { path: { template_id: template.id } },
        }),
      ),
    onSuccess: () => client.invalidateQueries({ queryKey: templateKey(target) }),
  });
}
