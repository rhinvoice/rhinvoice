import { queryOptions } from "@tanstack/react-query";

import { api, unwrap } from "@/api/client";

/** Asked when the person copies it: the log must be as fresh as the problem. */
export const supportReportQuery = queryOptions({
  queryKey: ["support", "report"],
  queryFn: () => unwrap(api.GET("/api/support/report")),
  staleTime: 0,
  gcTime: 0,
});
