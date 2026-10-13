import { useEffect, useState, useSyncExternalStore } from "react";
import { createFallbackChain, type FallbackChain } from "~/engines/tier/fallback";
import { detectThreeD, resolveTier, type Tier, whenProbed } from "~/engines/tier/probe";

export type { Tier } from "~/engines/tier/probe";
export { detectThreeD, probeTier } from "~/engines/tier/probe";

let chain: FallbackChain | undefined;
let chainPromise: Promise<FallbackChain> | undefined;

/** The page's fallback chain, created once the capability probe has finished (FR-018-29, FR-018-30, FR-018-31). */
export function whenChain(): Promise<FallbackChain> {
  chainPromise ??= whenProbed().then((probed) => {
    const search = typeof location === "undefined" ? "" : location.search;
    chain = createFallbackChain({ probed, requested: resolveTier(probed, search) });
    return chain;
  });
  return chainPromise;
}

/** Runs the probe and returns the chain (null until it exists). */
export function useChain(): FallbackChain | null {
  const [, setReady] = useState(0);
  useEffect(() => {
    let live = true;
    void whenChain().then(() => {
      if (live) setReady((n) => n + 1);
    });
    return () => {
      live = false;
    };
  }, []);
  useSyncExternalStore(
    (l) => {
      const off = chain?.subscribe(l);
      return () => off?.();
    },
    () => (chain ? `${chain.badge()}:${chain.notices().length}` : "none"),
    () => "none",
  );
  return chain ?? null;
}

/** The tier the badge shows: lowest tier among the engines in use, null while the probe runs. */
export function useTier(): Tier | null {
  const c = useChain();
  return c ? c.badge() : null;
}

export function useThreeD(): boolean | null {
  const [available, setAvailable] = useState<boolean | null>(null);
  useEffect(() => setAvailable(detectThreeD()), []);
  return available;
}
