import { useSyncExternalStore } from "react";

const subscribe = () => () => {};

/**
 * False in the prerendered HTML and during hydration, true afterwards. Pages that depend on the query string use it
 * so the client's first render matches the prerendered markup (which has no query), then switches to the real URL.
 */
export function useHydrated(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => true,
    () => false,
  );
}
