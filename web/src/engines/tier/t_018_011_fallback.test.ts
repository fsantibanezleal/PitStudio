// T-018-011 [red] · FR-018-31 (fallback chain T1 -> T2 -> T0, notice, badge, page stays interactive), FR-018-06 (badge)
// and FR-000-02 (a failing runtime never blocks the page).
//
// Expected API (module `~/engines/tier/fallback`, file web/src/engines/tier/fallback.ts):
//   type Tier = "t1" | "t2" | "t0"
//   type FailureKind = "init" | "throw" | "timeout" | "device-lost"
//   interface Notice { engineId: string; runtime: string; kind: FailureKind; from: Tier; to: Tier; message: string; modal: false }
//   createFallbackChain(opts: { probed: Tier; requested?: Tier }): FallbackChain
//       `requested` is the already resolved `?tier=` value (see t_018_010); a request higher than `probed` is ignored.
//   FallbackChain:
//       tierOf(engineId): Tier                    the engine's current tier (the page tier until it fails)
//       start(engineId): void                     marks the engine as in use
//       fail(engineId, f: { runtime: string; kind: FailureKind; detail?: string }): Tier
//                                                 moves THAT engine one tier down (T1 -> T2 -> T0; T0 stays T0), records a
//                                                 Notice whose message names the runtime, returns the new tier
//       badge(): Tier                             tier shown by the page badge: the lowest tier among engines in use, else the page tier
//       notices(): readonly Notice[]              oldest first, never modal
//       subscribe(listener: () => void): () => void
//   watchDevice(chain, engineId, device: { lost: Promise<{ reason: string; message: string }> }): void
//       when the device is lost (reason "unknown") the engine falls back with runtime "WebGPU" and kind "device-lost"
//   runWithFallback<T>(chain, engineId, attempt: (tier: Tier) => Promise<T>, runtimes?: Partial<Record<Tier, string>>):
//       Promise<{ tier: Tier; value: T }>       runs `attempt` on the engine's tier; a rejection calls `chain.fail(kind "throw")`
//                                               and retries one tier lower; a rejection at T0 is returned to the caller.
//                                               Default runtime names: t1 "WebGPU", t2 "WebAssembly", t0 "baked results".
//
// Oracles: the EARS text of FR-018-31 (T1 -> T2 -> T0 within 1 s, notice naming the failed runtime, non-modal); WebGPU spec
// GPUDeviceLostInfo (reason "unknown" for a real loss). The tier badge texts are fixed by FR-018-06 and the e2e file.
import fc from "fast-check";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createFakeGpu } from "~/engines/tier/fake-gpu";
import { createFallbackChain, runWithFallback, watchDevice } from "~/engines/tier/fallback";

type Tier = "t1" | "t2" | "t0";
const ORDER: Record<Tier, number> = { t0: 0, t2: 1, t1: 2 };

beforeEach(() => {
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
});

describe("tier of each engine", () => {
  it("FR-018-31 · every engine starts on the probed tier", () => {
    const chain = createFallbackChain({ probed: "t1" });
    expect(chain.tierOf("geotech")).toBe("t1");
    expect(chain.tierOf("des")).toBe("t1");
    expect(chain.badge()).toBe("t1");
  });

  it("FR-018-30 · a lower requested tier is used from the start; a higher one is ignored", () => {
    expect(createFallbackChain({ probed: "t1", requested: "t2" }).tierOf("gns")).toBe("t2");
    expect(createFallbackChain({ probed: "t2", requested: "t1" }).tierOf("gns")).toBe("t2");
    expect(createFallbackChain({ probed: "t2", requested: "t0" }).tierOf("gns")).toBe("t0");
  });

  it("FR-018-31 · fail moves the engine T1 -> T2 -> T0 and T0 stays T0", () => {
    const chain = createFallbackChain({ probed: "t1" });
    expect(chain.fail("gns", { runtime: "WebGPU", kind: "device-lost" })).toBe("t2");
    expect(chain.tierOf("gns")).toBe("t2");
    expect(chain.fail("gns", { runtime: "ORT-web", kind: "init" })).toBe("t0");
    expect(chain.tierOf("gns")).toBe("t0");
    expect(chain.fail("gns", { runtime: "baked results", kind: "throw" })).toBe("t0");
    expect(chain.tierOf("gns")).toBe("t0");
  });

  it("FR-018-31 · a failure moves only the failing engine", () => {
    const chain = createFallbackChain({ probed: "t1" });
    chain.fail("gns", { runtime: "ORT-web", kind: "init" });
    expect(chain.tierOf("gns")).toBe("t2");
    expect(chain.tierOf("des")).toBe("t1");
    expect(chain.tierOf("geotech")).toBe("t1");
  });

  it("FR-018-31 · each failure kind is accepted (init, throw, timeout, device-lost)", () => {
    for (const kind of ["init", "throw", "timeout", "device-lost"] as const) {
      const chain = createFallbackChain({ probed: "t1" });
      expect(chain.fail("des", { runtime: "worker", kind })).toBe("t2");
      expect(chain.notices()[0]?.kind).toBe(kind);
    }
  });
});

describe("badge and notices (FR-018-31, FR-018-06)", () => {
  it("FR-018-31 · the badge follows the lowest tier among engines in use", () => {
    const chain = createFallbackChain({ probed: "t1" });
    chain.start("des");
    expect(chain.badge()).toBe("t1");
    chain.fail("des", { runtime: "WebGPU", kind: "device-lost" });
    expect(chain.badge()).toBe("t2");
    chain.start("gns");
    expect(chain.badge()).toBe("t2");
    chain.fail("gns", { runtime: "ORT-web", kind: "init" });
    chain.fail("gns", { runtime: "WebAssembly", kind: "init" });
    expect(chain.badge()).toBe("t0");
  });

  it("FR-018-31 · the badge ignores engines that were never started", () => {
    const chain = createFallbackChain({ probed: "t1" });
    chain.fail("gns", { runtime: "ORT-web", kind: "init" });
    expect(chain.badge()).toBe("t1");
  });

  it("FR-018-31 · a failure leaves one notice naming the failed runtime, the engine and both tiers, and it is not modal", () => {
    const chain = createFallbackChain({ probed: "t1" });
    chain.fail("gns", { runtime: "ORT-web", kind: "timeout", detail: "10 s" });
    const notices = chain.notices();
    expect(notices).toHaveLength(1);
    const n = notices[0];
    expect(n?.engineId).toBe("gns");
    expect(n?.runtime).toBe("ORT-web");
    expect(n?.from).toBe("t1");
    expect(n?.to).toBe("t2");
    expect(n?.kind).toBe("timeout");
    expect(n?.message).toContain("ORT-web");
    expect(n?.modal).toBe(false);
  });

  it("FR-018-31 · notices are kept oldest first", () => {
    const chain = createFallbackChain({ probed: "t1" });
    chain.fail("gns", { runtime: "WebGPU", kind: "device-lost" });
    chain.fail("des", { runtime: "worker", kind: "throw" });
    expect(chain.notices().map((n: { engineId: string }) => n.engineId)).toEqual(["gns", "des"]);
  });

  it("FR-018-31 · subscribers are told about every change until they unsubscribe", () => {
    const chain = createFallbackChain({ probed: "t1" });
    const listener = vi.fn();
    const off = chain.subscribe(listener);
    chain.fail("gns", { runtime: "WebGPU", kind: "device-lost" });
    expect(listener).toHaveBeenCalledTimes(1);
    off();
    chain.fail("gns", { runtime: "ORT-web", kind: "init" });
    expect(listener).toHaveBeenCalledTimes(1);
  });
});

describe("device lost (FR-018-31 with the fake GPU)", () => {
  it("FR-018-31 · a device lost 500 ms after the grant moves the engine to T2 within 1 s and names WebGPU", async () => {
    const gpu = createFakeGpu({ kind: "device-lost", afterMs: 500 });
    const device = await (await gpu?.requestAdapter())?.requestDevice();
    const chain = createFallbackChain({ probed: "t1" });
    chain.start("granular");
    watchDevice(chain, "granular", device as NonNullable<typeof device>);
    await vi.advanceTimersByTimeAsync(499);
    expect(chain.tierOf("granular")).toBe("t1");
    await vi.advanceTimersByTimeAsync(1 + 1000);
    expect(chain.tierOf("granular")).toBe("t2");
    expect(chain.badge()).toBe("t2");
    const n = chain.notices()[0];
    expect(n?.runtime).toBe("WebGPU");
    expect(n?.kind).toBe("device-lost");
  });

  it("FR-018-31 · a healthy device never triggers a fallback", async () => {
    const gpu = createFakeGpu({ kind: "ok" });
    const device = await (await gpu?.requestAdapter())?.requestDevice();
    const chain = createFallbackChain({ probed: "t1" });
    watchDevice(chain, "granular", device as NonNullable<typeof device>);
    await vi.advanceTimersByTimeAsync(60_000);
    expect(chain.tierOf("granular")).toBe("t1");
    expect(chain.notices()).toHaveLength(0);
  });
});

describe("runWithFallback (FR-018-31)", () => {
  it("FR-018-31 · an attempt that works on the engine's tier is returned as is", async () => {
    const chain = createFallbackChain({ probed: "t2" });
    const attempt = vi.fn(async (tier: Tier) => `ok on ${tier}`);
    await expect(runWithFallback(chain, "geotech", attempt)).resolves.toEqual({
      tier: "t2",
      value: "ok on t2",
    });
    expect(attempt).toHaveBeenCalledTimes(1);
    expect(chain.notices()).toHaveLength(0);
  });

  it("FR-018-31 · a rejection on T1 retries on T2 and records the notice", async () => {
    const chain = createFallbackChain({ probed: "t1" });
    const attempt = vi.fn(async (tier: Tier) => {
      if (tier === "t1") throw new Error("pipeline creation failed");
      return `ok on ${tier}`;
    });
    await expect(runWithFallback(chain, "geotech", attempt, { t1: "WebGPU" })).resolves.toEqual({
      tier: "t2",
      value: "ok on t2",
    });
    expect(attempt.mock.calls.map((c) => c[0])).toEqual(["t1", "t2"]);
    expect(chain.tierOf("geotech")).toBe("t2");
    expect(chain.notices()[0]?.runtime).toBe("WebGPU");
    expect(chain.notices()[0]?.kind).toBe("throw");
  });

  it("FR-018-31 · two failing tiers end on T0 with the baked result", async () => {
    const chain = createFallbackChain({ probed: "t1" });
    const attempt = vi.fn(async (tier: Tier) => {
      if (tier !== "t0") throw new Error(`no ${tier}`);
      return "baked";
    });
    await expect(runWithFallback(chain, "gns", attempt)).resolves.toEqual({ tier: "t0", value: "baked" });
    expect(chain.notices().map((n: { runtime: string }) => n.runtime)).toEqual(["WebGPU", "WebAssembly"]);
  });

  it("FR-000-02 · a failure at T0 is returned to the caller as a rejection, never swallowed or thrown elsewhere", async () => {
    const chain = createFallbackChain({ probed: "t0" });
    await expect(
      runWithFallback(chain, "gns", async () => {
        throw new Error("baked file missing");
      }),
    ).rejects.toThrow("baked file missing");
  });
});

describe("properties (FR-018-31)", () => {
  it("FR-018-31 · for any sequence of failures an engine's tier never rises and stops at T0 after at most two failures", () => {
    fc.assert(
      fc.property(
        fc.constantFrom<Tier>("t1", "t2", "t0"),
        fc.array(fc.constantFrom("a", "b", "c"), { maxLength: 12 }),
        (probed, engines) => {
          const chain = createFallbackChain({ probed });
          const last = new Map<string, Tier>();
          const count = new Map<string, number>();
          for (const id of engines) {
            const before = chain.tierOf(id);
            const after = chain.fail(id, { runtime: "r", kind: "throw" });
            if (ORDER[after as Tier] > ORDER[before as Tier]) return false;
            last.set(id, after);
            count.set(id, (count.get(id) ?? 0) + 1);
          }
          for (const [id, n] of count) {
            if (n >= 2 && last.get(id) !== "t0") return false;
          }
          return true;
        },
      ),
      { numRuns: 200 },
    );
  });
});
