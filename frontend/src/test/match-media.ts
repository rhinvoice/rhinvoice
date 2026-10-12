/** A controllable window.matchMedia for tests (jsdom has none). */
export function installMatchMedia(initialDark: boolean) {
  let dark = initialDark;
  const listeners = new Set<() => void>();
  window.matchMedia = (query: string) =>
    ({
      get matches() {
        return query.includes("dark") && dark;
      },
      media: query,
      onchange: null,
      addEventListener: (_type: string, listener: () => void) => listeners.add(listener),
      removeEventListener: (_type: string, listener: () => void) => listeners.delete(listener),
      addListener: () => undefined,
      removeListener: () => undefined,
      dispatchEvent: () => true,
    }) as unknown as MediaQueryList;
  return {
    setDark(value: boolean) {
      dark = value;
      for (const listener of listeners) listener();
    },
    get listenerCount() {
      return listeners.size;
    },
  };
}
