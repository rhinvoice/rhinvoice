import { queryOptions } from "@tanstack/react-query";

import { api, unwrap, type components } from "@/api/client";

export type Dashboard = components["schemas"]["DashboardResponse"];

export const dashboardQuery = queryOptions({
  // Same key the documents feature invalidates after every change.
  queryKey: ["dashboard"],
  queryFn: () => unwrap(api.GET("/api/dashboard")),
});
