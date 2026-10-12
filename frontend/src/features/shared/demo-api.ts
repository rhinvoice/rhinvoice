import { queryOptions } from "@tanstack/react-query";

import { api, unwrap, type components } from "@/api/client";

export type DemoInfo = components["schemas"]["DemoResponse"];

/** Whether this installation is a public demo, and its shared login; needs no login. */
export const demoQuery = queryOptions({
  queryKey: ["demo"],
  queryFn: () => unwrap(api.GET("/api/demo")),
  staleTime: Number.POSITIVE_INFINITY,
});
