// Fallback chain T1 -> T2 -> T0 (FR-018-31): a failing engine moves one tier down, the page leaves a non-modal notice naming
// the failed runtime, and the page badge follows the lowest tier among the engines in use. A failure at T0 is the caller's.
import { TIER_ORDER, type Tier } from "./probe";

export type { Tier };
export type FailureKind = "init" | "throw" | "timeout" | "device-lost";

export interface Notice {
  engineId: string;
  runtime: string;
  kind: FailureKind;
  from: Tier;
  to: Tier;
  message: string;
  modal: false;
}

export interface FallbackChain {
  tierOf(engineId: string): Tier;
  start(engineId: string): void;
  fail(engineId: string, f: { runtime: string; kind: FailureKind; detail?: string }): Tier;
  badge(): Tier;
  notices(): readonly Notice[];
  subscribe(listener: () => void): () => void;
}

const DOWN: Record<Tier, Tier> = { t1: "t2", t2: "t0", t0: "t0" };

export function createFallbackChain(opts: { probed: Tier; requested?: Tier }): FallbackChain {
  const base: Tier =
    opts.requested && TIER_ORDER[opts.requested] <= TIER_ORDER[opts.probed] ? opts.requested : opts.probed;
  const tiers = new Map<string, Tier>();
  const inUse = new Set<string>();
  let notices: readonly Notice[] = [];
  const listeners = new Set<() => void>();
  const emit = () => {
    for (const l of [...listeners]) l();
  };
  const tierOf = (id: string): Tier => tiers.get(id) ?? base;

  return {
    tierOf,
    start(id) {
      inUse.add(id);
      emit();
    },
    fail(id, f) {
      const from = tierOf(id);
      const to = DOWN[from];
      tiers.set(id, to);
      const detail = f.detail ? ` (${f.detail})` : "";
      notices = [
        ...notices,
        {
          engineId: id,
          runtime: f.runtime,
          kind: f.kind,
          from,
          to,
          message: `${f.runtime} failed for ${id}: ${f.kind}${detail}; continuing on ${to.toUpperCase()}`,
          modal: false,
        },
      ];
      emit();
      return to;
    },
    badge() {
      let lowest: Tier = base;
      let any = false;
      for (const id of inUse) {
        const t = tierOf(id);
        if (!any || TIER_ORDER[t] < TIER_ORDER[lowest]) lowest = t;
        any = true;
      }
      return any ? lowest : base;
    },
    notices: () => notices,
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}

/** When the device is lost (not destroyed by us) the engine falls back with runtime "WebGPU". */
export function watchDevice(
  chain: FallbackChain,
  engineId: string,
  device: { lost: Promise<{ reason: string; message: string }> },
): void {
  void device.lost.then((info) => {
    if (info.reason === "destroyed") return;
    chain.fail(engineId, { runtime: "WebGPU", kind: "device-lost", detail: info.message });
  });
}

const DEFAULT_RUNTIMES: Record<Tier, string> = { t1: "WebGPU", t2: "WebAssembly", t0: "baked results" };

export async function runWithFallback<T>(
  chain: FallbackChain,
  engineId: string,
  attempt: (tier: Tier) => Promise<T>,
  runtimes: Partial<Record<Tier, string>> = {},
): Promise<{ tier: Tier; value: T }> {
  for (;;) {
    const tier = chain.tierOf(engineId);
    try {
      return { tier, value: await attempt(tier) };
    } catch (error) {
      if (tier === "t0") throw error;
      chain.fail(engineId, {
        runtime: runtimes[tier] ?? DEFAULT_RUNTIMES[tier],
        kind: "throw",
        detail: error instanceof Error ? error.message : String(error),
      });
    }
  }
}
