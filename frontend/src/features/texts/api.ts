import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api, unwrap, type components } from "@/api/client";
import { textKeys, type TextTemplate } from "@/features/shared/texts-api";

export type TextTemplateRequest = components["schemas"]["TextTemplateRequest"];
export type TaxTreatment = components["schemas"]["TaxTreatment"];
export type Language = components["schemas"]["Language"];
export {
  legalNoticesQuery,
  textTemplatesQuery,
  type LegalNotice,
  type TextKind,
  type TextTemplate,
} from "@/features/shared/texts-api";

export function useSaveTextTemplate() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      body,
    }: {
      readonly id: string | null;
      readonly body: TextTemplateRequest;
    }) =>
      id === null
        ? unwrap(api.POST("/api/text-templates", { body }))
        : unwrap(
            api.PUT("/api/text-templates/{template_id}", {
              params: { path: { template_id: id } },
              body,
            }),
          ),
    onSuccess: () => client.invalidateQueries({ queryKey: textKeys.templates }),
  });
}

export function useMoveTextTemplate() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, up }: { readonly id: string; readonly up: boolean }) =>
      unwrap(
        api.POST("/api/text-templates/{template_id}/move", {
          params: { path: { template_id: id } },
          body: { up },
        }),
      ),
    onSuccess: (templates: TextTemplate[]) => {
      client.setQueryData(textKeys.templates, templates);
    },
  });
}

export function useDeleteTextTemplate() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(
        api.DELETE("/api/text-templates/{template_id}", {
          params: { path: { template_id: id } },
        }),
      ),
    onSuccess: () => client.invalidateQueries({ queryKey: textKeys.templates }),
  });
}

export function useSaveLegalNotice() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      treatment,
      language,
      text,
    }: {
      readonly treatment: TaxTreatment;
      readonly language: Language;
      readonly text: string;
    }) =>
      unwrap(
        api.PUT("/api/legal-notices/{treatment}/{language}", {
          params: { path: { treatment, language } },
          body: { text },
        }),
      ),
    onSuccess: () => client.invalidateQueries({ queryKey: textKeys.notices }),
  });
}
