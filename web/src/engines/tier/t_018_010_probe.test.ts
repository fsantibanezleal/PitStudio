// T-018-010 [red] · FR-018-29 (capability probe) and FR-018-30 (`?tier=` override), with the fake GPU of T-018-006.
//
// Expected API (module `~/engines/tier/probe`, file web/src/engines/tier/probe.ts; the current minimal probe lives in
// web/src/tier/probe.ts and is to be moved and completed):
//   type Tier = "t1" | "t2" | "t0"                         T1 WebGPU > T2 WebAssembly > T0 baked
//   probeTier(options?: { timeoutMs?: number }): Promise<Tier>
//       T1 iff `navigator.gpu` exists, requestAdapter() gives an adapter and requestDevice() resolves within `timeoutMs`
//       (default 2000); else T2 iff `WebAssembly.instantiate` exists and a module with ONE function compiles; else T0.
//       It downloads nothing (no fetch / XHR / beacon) and never rejects.
//   whenProbed(): Promise<Tier>                            memoised: the probe runs once per page load (module state is
//                                                           reset with `resetProbeForTests()`)
//   resetProbeForTests(): void
//   startAfterProbe<T>(start: (tier: Tier) => T): Promise<T>   `start` is not called before the probe has finished and
//                                                           receives the resolved tier ("shall finish before any engine starts")
//   resolveTier(probed: Tier, search: string): Tier        `?tier=t2` / `?tier=t0` lower the tier, a request that is higher
//                                                           than `probed`, unknown, malformed or longer than 2,000 characters is
//                                                           ignored (FR-018-30, FR-018-42). `search` may start with "?".
//
// Oracles: the EARS text of FR-018-29 / FR-018-30; the WebAssembly binary format (core spec 5.5: magic, version, section ids,
// the function section id 3 holds a vector whose first byte is its length) to check "a 1-function test module".
import fc from "fast-check";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { installFakeGpu } from "~/engines/tier/fake-gpu";
import {
  probeTier,
  resetProbeForTests,
  resolveTier,
  startAfterProbe,
  whenProbed,
} from "~/engines/tier/probe";

type Tier = "t1" | "t2" | "t0";
const ORDER: Record<Tier, number> = { t0: 0, t2: 1, t1: 2 };

let restoreGpu: (() => void) | undefined;
beforeEach(() => {
  vi.useFakeTimers();
  resetProbeForTests();
});
afterEach(() => {
  restoreGpu?.();
  restoreGpu = undefined;
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

/** Reads the function-section vector length of a WebAssembly binary (WebAssembly core spec 5.5.2 and 5.5.5). */
function functionCount(bytes: Uint8Array): number | null {
  const magic = [0x00, 0x61, 0x73, 0x6d, 0x01, 0x00, 0x00, 0x00];
  for (let i = 0; i < 8; i++) if (bytes[i] !== magic[i]) return null;
  let pos = 8;
  const leb = (): number => {
    let result = 0;
    let shift = 0;
    for (;;) {
      const b = bytes[pos++] as number;
      result |= (b & 0x7f) << shift;
      if ((b & 0x80) === 0) return result;
      shift += 7;
    }
  };
  while (pos < bytes.length) {
    const id = bytes[pos++] as number;
    const size = leb();
    if (id === 3) {
      const start = pos;
      const count = leb();
      pos = start;
      return count;
    }
    pos += size;
  }
  return 0;
}

describe("tier selection (FR-018-29)", () => {
  it("FR-018-29 · a working adapter and device give T1", async () => {
    restoreGpu = installFakeGpu({ kind: "ok" });
    await expect(probeTier()).resolves.toBe("t1");
  });

  it("FR-018-29 · no navigator.gpu gives T2 when WebAssembly works", async () => {
    restoreGpu = installFakeGpu({ kind: "none" });
    await expect(probeTier()).resolves.toBe("t2");
  });

  it("FR-018-29 · a null adapter gives T2", async () => {
    restoreGpu = installFakeGpu({ kind: "null-adapter" });
    await expect(probeTier()).resolves.toBe("t2");
  });

  it("FR-018-29 · a rejected requestDevice gives T2", async () => {
    restoreGpu = installFakeGpu({ kind: "device-rejects", message: "denied" });
    await expect(probeTier()).resolves.toBe("t2");
  });

  it("FR-018-29 · a requestDevice that never settles gives T2 at the 2 s limit, not before and not much after", async () => {
    restoreGpu = installFakeGpu({ kind: "hang" });
    let tier: Tier | undefined;
    const probe = probeTier().then((t: Tier) => {
      tier = t;
      return t;
    });
    await vi.advanceTimersByTimeAsync(1999);
    expect(tier).toBeUndefined();
    await vi.advanceTimersByTimeAsync(100);
    // the WebAssembly compile that follows runs on the real event loop, so wait for the promise itself
    await expect(probe).resolves.toBe("t2");
  });

  it("FR-018-29 · a custom timeout is honoured (500 ms)", async () => {
    restoreGpu = installFakeGpu({ kind: "hang" });
    let tier: Tier | undefined;
    const probe = probeTier({ timeoutMs: 500 }).then((t: Tier) => {
      tier = t;
      return t;
    });
    await vi.advanceTimersByTimeAsync(499);
    expect(tier).toBeUndefined();
    await vi.advanceTimersByTimeAsync(50);
    await expect(probe).resolves.toBe("t2");
  });

  it("FR-018-29 · a requestAdapter that throws synchronously still gives T2 and never rejects", async () => {
    Object.defineProperty(navigator, "gpu", {
      configurable: true,
      value: {
        requestAdapter() {
          throw new Error("boom");
        },
      },
    });
    restoreGpu = () => {
      Reflect.deleteProperty(navigator, "gpu");
    };
    await expect(probeTier()).resolves.toBe("t2");
  });

  it("FR-018-29 · without WebAssembly (and no GPU) the tier is T0", async () => {
    restoreGpu = installFakeGpu({ kind: "none" });
    vi.stubGlobal("WebAssembly", undefined);
    await expect(probeTier()).resolves.toBe("t0");
  });

  it("FR-018-29 · a WebAssembly whose instantiate rejects (blocked by policy) gives T0", async () => {
    restoreGpu = installFakeGpu({ kind: "none" });
    vi.stubGlobal("WebAssembly", {
      instantiate: () => Promise.reject(new Error("CSP")),
      compile: () => Promise.reject(new Error("CSP")),
    });
    await expect(probeTier()).resolves.toBe("t0");
  });

  it("FR-018-29 · a WebAssembly without an instantiate function gives T0", async () => {
    restoreGpu = installFakeGpu({ kind: "none" });
    vi.stubGlobal("WebAssembly", {});
    await expect(probeTier()).resolves.toBe("t0");
  });

  it("FR-018-29 · T1 is chosen even when WebAssembly is absent (GPU wins)", async () => {
    restoreGpu = installFakeGpu({ kind: "ok" });
    vi.stubGlobal("WebAssembly", undefined);
    await expect(probeTier()).resolves.toBe("t1");
  });

  it("FR-018-29 · the T2 test module is a valid WebAssembly binary with exactly one function", async () => {
    restoreGpu = installFakeGpu({ kind: "none" });
    const seen: Uint8Array[] = [];
    const real = globalThis.WebAssembly;
    vi.stubGlobal("WebAssembly", {
      ...real,
      instantiate: (bytes: BufferSource, imports?: WebAssembly.Imports) => {
        seen.push(new Uint8Array(bytes as ArrayBuffer));
        return real.instantiate(bytes as ArrayBuffer, imports);
      },
      compile: (bytes: BufferSource) => {
        seen.push(new Uint8Array(bytes as ArrayBuffer));
        return real.compile(bytes as ArrayBuffer);
      },
      validate: real.validate.bind(real),
    });
    await expect(probeTier()).resolves.toBe("t2");
    expect(seen.length).toBeGreaterThan(0);
    const module = seen[0] as Uint8Array<ArrayBuffer>;
    expect(real.validate(module)).toBe(true);
    expect(functionCount(module)).toBe(1);
  });

  it("FR-018-29 · the probe downloads no file: no fetch, no XMLHttpRequest, no beacon", async () => {
    restoreGpu = installFakeGpu({ kind: "ok" });
    const fetchSpy = vi.fn(() => Promise.reject(new Error("no network expected")));
    vi.stubGlobal("fetch", fetchSpy);
    const open = vi.spyOn(XMLHttpRequest.prototype, "open");
    const beacon = vi.fn(() => false);
    Object.defineProperty(navigator, "sendBeacon", { configurable: true, value: beacon });
    await probeTier();
    restoreGpu?.();
    restoreGpu = installFakeGpu({ kind: "none" });
    await probeTier();
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(open).not.toHaveBeenCalled();
    expect(beacon).not.toHaveBeenCalled();
    Reflect.deleteProperty(navigator, "sendBeacon");
  });
});

describe("one probe per page, before any engine (FR-018-29)", () => {
  it("FR-018-29 · whenProbed runs the probe once and shares the result", async () => {
    restoreGpu = installFakeGpu({ kind: "ok" });
    const g = (
      navigator as unknown as {
        gpu: { requestAdapter(): Promise<unknown>; calls: { requestAdapter: number } };
      }
    ).gpu;
    const [a, b, c] = await Promise.all([whenProbed(), whenProbed(), whenProbed()]);
    expect([a, b, c]).toEqual(["t1", "t1", "t1"]);
    expect(g.calls.requestAdapter).toBe(1);
  });

  it("FR-018-29 · startAfterProbe does not call the engine start before the probe finished and passes the tier", async () => {
    restoreGpu = installFakeGpu({ kind: "hang" });
    const start = vi.fn((tier: Tier) => `started on ${tier}`);
    const done = startAfterProbe(start);
    await vi.advanceTimersByTimeAsync(1999);
    expect(start).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(200);
    await expect(done).resolves.toBe("started on t2");
    expect(start).toHaveBeenCalledTimes(1);
    expect(start).toHaveBeenCalledWith("t2");
  });
});

describe("?tier= override (FR-018-30)", () => {
  const cases: Array<[Tier, string, Tier]> = [
    ["t1", "?tier=t2", "t2"],
    ["t1", "?tier=t0", "t0"],
    ["t2", "?tier=t2", "t2"],
    ["t2", "?tier=t0", "t0"],
    ["t0", "?tier=t0", "t0"],
    ["t2", "?tier=t1", "t2"],
    ["t0", "?tier=t2", "t0"],
    ["t0", "?tier=t1", "t0"],
    ["t1", "", "t1"],
    ["t2", "", "t2"],
    ["t0", "", "t0"],
    ["t1", "tier=t0", "t0"],
    ["t1", "?case=A1&tier=t2&tab=charts", "t2"],
  ];
  for (const [probed, search, expected] of cases) {
    it(`FR-018-30 · probed ${probed} with "${search}" uses ${expected} (a higher request is ignored)`, () => {
      expect(resolveTier(probed, search)).toBe(expected);
    });
  }

  const hostile = [
    "?tier=",
    "?tier=abc",
    "?tier=T2",
    "?tier=<script>alert(1)</script>",
    "?tier=t2%00",
    "?tier=-1",
    "?tier=Infinity",
    "?tier=t3",
    `?tier=${"t".repeat(2001)}`,
  ];
  for (const search of hostile) {
    it(`FR-018-42 · hostile "${search.slice(0, 30)}" is ignored and the probed tier is used`, () => {
      expect(resolveTier("t1", search)).toBe("t1");
      expect(() => resolveTier("t2", search)).not.toThrow();
    });
  }

  it("FR-018-30 · property: the resolved tier is never higher than the probed tier, for any query string", () => {
    fc.assert(
      fc.property(
        fc.constantFrom<Tier>("t1", "t2", "t0"),
        fc.string({ maxLength: 3000 }),
        (probed, search) => {
          const resolved = resolveTier(probed, search);
          return ORDER[resolved as Tier] <= ORDER[probed];
        },
      ),
      { numRuns: 200 },
    );
  });

  it("FR-018-30 · property: with a valid ?tier= lower than or equal to the probe the request is honoured exactly", () => {
    fc.assert(
      fc.property(
        fc.constantFrom<Tier>("t1", "t2", "t0"),
        fc.constantFrom<Tier>("t2", "t0"),
        (probed, asked) => {
          const resolved = resolveTier(probed, `?tier=${asked}`);
          return ORDER[asked] <= ORDER[probed] ? (resolved as Tier) === asked : (resolved as Tier) === probed;
        },
      ),
      { numRuns: 200 },
    );
  });
});
