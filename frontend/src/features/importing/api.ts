import { queryOptions, useMutation, useQueryClient } from "@tanstack/react-query";

import { api, CLIENT_HEADER, unwrap } from "@/api/client";
import {
  uploadName,
  type ImportRun,
  type ImportTarget,
  type ImportTemplate,
  type Mapping,
} from "@/features/importing/import-model";
import { toApiError } from "@/lib/api-error";

export type DuplicateStrategy = "skip" | "update" | "create";

export interface ImportOptions {
  readonly file: File;
  readonly duplicates: DuplicateStrategy;
  /** null: suggested from the column names. */
  readonly mapping: Mapping | null;
  /** Invoices: their PDF (and ZIP) files. */
  readonly files?: readonly File[];
}

/** Test run (commit false) or import; multipart, so not through the generated client. */
export async function runImport(
  target: ImportTarget,
  options: ImportOptions,
  commit: boolean,
  signal?: AbortSignal,
): Promise<ImportRun> {
  const body = new FormData();
  body.append("file", options.file);
  body.append("duplicates", options.duplicates);
  if (options.mapping !== null) {
    body.append("mapping", JSON.stringify(options.mapping));
  }
  for (const file of options.files ?? []) {
    // The folders tell copies apart ("2023/pdf/R1.pdf" next to "2023/R1.pdf").
    body.append("files", file, uploadName(file));
  }
  let response: Response;
  try {
    response = await fetch(`/api/imports/${target}${commit ? "" : "/preview"}`, {
      method: "POST",
      body,
      credentials: "same-origin",
      headers: { [CLIENT_HEADER]: "web" },
      // A newer test run replaces this one: its upload stops.
      ...(signal === undefined ? {} : { signal }),
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
