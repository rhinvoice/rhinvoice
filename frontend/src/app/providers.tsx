import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { MotionConfig } from "motion/react";
import { useState } from "react";

import { createAppRouter, type AppRouter } from "@/app/router";
import { I18nProvider } from "@/components/i18n/i18n-provider";
import { ThemeProvider } from "@/components/theme/theme-provider";
import { useTheme } from "@/components/theme/use-theme";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ApiError } from "@/lib/api-error";

function createQueryClient(onSessionEnded: (error: ApiError) => void): QueryClient {
  const onError = (error: Error) => {
    if (error instanceof ApiError && error.endsSession) onSessionEnded(error);
  };
  return new QueryClient({
    queryCache: new QueryCache({ onError }),
    mutationCache: new MutationCache({ onError }),
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: true,
        retry: (failureCount, error) =>
          !(error instanceof ApiError && error.status >= 400 && error.status < 500) &&
          failureCount < 2,
      },
    },
  });
}

function ThemedToaster() {
  const { theme } = useTheme();
  return <Toaster theme={theme} />;
}

/**
 * A session can end while the app is open: it expired, the user logged out elsewhere, or the
 * public demo was reset. Every request then fails; instead of showing that on each page, go
 * to the login once and say why.
 */
async function endSession(router: AppRouter, queryClient: QueryClient, error: ApiError) {
  const { pathname, href } = router.state.location;
  if (pathname === "/login") return;
  await router.navigate({
    to: "/login",
    search: { redirect: href, ...(error.code === "session_expired" ? { expired: true } : {}) },
  });
  // Nothing of the ended session stays in memory; the login page loads what it needs again.
  queryClient.clear();
}

function createApp(): { queryClient: QueryClient; router: AppRouter } {
  let ending = false;
  const queryClient = createQueryClient((error) => {
    if (ending) return;
    ending = true;
    void endSession(router, queryClient, error).finally(() => {
      ending = false;
    });
  });
  const router = createAppRouter(queryClient);
  return { queryClient, router };
}

export function App() {
  const [{ queryClient, router }] = useState(createApp);
  return (
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <ThemeProvider>
          <MotionConfig reducedMotion="user">
            <TooltipProvider delayDuration={400}>
              <RouterProvider router={router} />
              <ThemedToaster />
            </TooltipProvider>
          </MotionConfig>
        </ThemeProvider>
      </I18nProvider>
    </QueryClientProvider>
  );
}
