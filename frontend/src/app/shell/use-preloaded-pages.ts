import { useRouter } from "@tanstack/react-router";
import { useEffect } from "react";

/** How long after the start the pages are loaded: the first page comes first. */
export const PRELOAD_DELAY_MS = 1_500;

/** Whether the page runs in the program window of the installation without Docker. */
export function inProgramWindow(target: object): boolean {
  // pywebview adds its bridge to every page its windows show.
  return "pywebview" in target;
}

/**
 * Load the code of every page shortly after the start, in the program window only.
 *
 * Each page's code is loaded on its first visit otherwise. In the program window it comes
 * from this computer, so loading all of it costs nothing and the first click is as quick
 * as any other; a browser, perhaps on a phone, keeps loading only what it shows.
 */
export function usePreloadedPages(): void {
  const router = useRouter();
  useEffect(() => {
    const timer = window.setTimeout(() => {
      // Asked only now: the web view adds its bridge once the page has loaded.
      if (!inProgramWindow(window)) {
        return;
      }
      for (const route of Object.values(router.routesById)) {
        // A page that fails to load here is loaded again on its visit.
        Promise.resolve(router.loadRouteChunk(route)).catch(() => undefined);
      }
    }, PRELOAD_DELAY_MS);
    return () => {
      window.clearTimeout(timer);
    };
  }, [router]);
}
