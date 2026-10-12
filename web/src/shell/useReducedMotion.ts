import { useSyncExternalStore } from "react";

const QUERY = "(prefers-reduced-motion: reduce)";

function subscribe(listener: () => void): () => void {
  if (typeof matchMedia !== "function") return () => {};
  const media = matchMedia(QUERY);
  media.addEventListener("change", listener);
  return () => media.removeEventListener("change", listener);
}

/**
 * "reduced" when the visitor asked the system for less motion (FR-018-28), else "full". The prerendered HTML is always "full";
 * the real preference is read after hydration, so server and client markup match.
 */
export function useMotion(): "reduced" | "full" {
  return useSyncExternalStore(
    subscribe,
    () => (typeof matchMedia === "function" && matchMedia(QUERY).matches ? "reduced" : "full"),
    () => "full",
  );
}
