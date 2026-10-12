import { queryOptions, useMutation, useQueryClient } from "@tanstack/react-query";

import { api, unwrap, type components } from "@/api/client";

export type DunningItem = components["schemas"]["DunningItemResponse"];
export type Reminder = components["schemas"]["ReminderResponse"];
export type DunningLevel = components["schemas"]["DunningLevelSchema-Output"];
export type DunningLevelRequest = components["schemas"]["DunningLevelSchema-Input"];

const DUNNING_KEY = ["dunning"] as const;

export const dunningQuery = queryOptions({
  queryKey: DUNNING_KEY,
  queryFn: () => unwrap(api.GET("/api/dunning")),
});

export const dunningLevelsQuery = queryOptions({
  queryKey: [...DUNNING_KEY, "levels"] as const,
  queryFn: () => unwrap(api.GET("/api/dunning/levels")),
});

export function reminderPdfUrl(reminder: Pick<Reminder, "id">, download = false): string {
  return `/api/reminders/${reminder.id}/pdf${download ? "?download=true" : ""}`;
}

export function useWriteReminder() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (request: { invoiceId: string; level: number; early: boolean }) =>
      unwrap(
        api.POST("/api/documents/{document_id}/reminders", {
          params: { path: { document_id: request.invoiceId } },
          body: { level: request.level, early: request.early },
        }),
      ),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: DUNNING_KEY });
      // The invoice's history shows the reminder.
      void client.invalidateQueries({ queryKey: ["documents"] });
    },
  });
}

export function useSaveDunningLevels() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: DunningLevelRequest[]) => unwrap(api.PUT("/api/dunning/levels", { body })),
    onSuccess: (levels) => {
      client.setQueryData(dunningLevelsQuery.queryKey, levels);
      void client.invalidateQueries({ queryKey: DUNNING_KEY });
    },
  });
}
