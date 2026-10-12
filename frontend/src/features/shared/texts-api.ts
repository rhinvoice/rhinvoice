import { queryOptions } from "@tanstack/react-query";

import { api, unwrap, type components } from "@/api/client";

/** Text templates and legal notices: read by the editor, managed in the settings. */
export type TextTemplate = components["schemas"]["TextTemplateResponse"];
export type TextKind = components["schemas"]["TextKind"];
export type LegalNotice = components["schemas"]["LegalNoticeResponse"];

export const textKeys = {
  templates: ["text-templates"] as const,
  notices: ["legal-notices"] as const,
};

export const textTemplatesQuery = queryOptions({
  queryKey: textKeys.templates,
  queryFn: () => unwrap(api.GET("/api/text-templates")),
  staleTime: 60_000,
});

export const legalNoticesQuery = queryOptions({
  queryKey: textKeys.notices,
  queryFn: () => unwrap(api.GET("/api/legal-notices")),
});
