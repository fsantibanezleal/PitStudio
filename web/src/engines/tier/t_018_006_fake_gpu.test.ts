// T-018-006 [red] · the fake GPU backend (spec 018 section 7.3). It serves FR-018-29 (capability probe) and FR-018-31
// (device lost -> fallback), which the hosted CI runner (no GPU) can only test through this double.
//
// Expected API (module `~/engines/tier/fake-gpu`, file web/src/engines/tier/fake-gpu.ts):
//   type FakeGpuScript =
//     | { kind: "ok" }                                  a working adapter and device
//     | { kind: "none" }                                no `navigator.gpu` at all
//     | { kind: "null-adapter" }                        requestAdapter() resolves null
//     | { kind: "device-rejects"; message?: string }    requestDevice() rejects with an Error carrying `message`
//     | { kind: "device-lost"; afterMs: number }        device.lost resolves `afterMs` after requestDevice() resolved
//     | { kind: "buffer-alloc-fails" }                  device.createBuffer() throws an Error whose message mentions "buffer"
//     | { kind: "hang" };                               requestDevice() never settles
//   createFakeGpu(script): FakeGpu | undefined          undefined for { kind: "none" }; throws on an invalid script
//   installFakeGpu(script, target?): () => void         defines `target.gpu` (default: the global `navigator`) and returns a
//                                                       restore function that puts the previous state back (LIFO safe)
//   FakeGpu  = { requestAdapter(): Promise<FakeAdapter | null>, calls: { requestAdapter, requestDevice, createBuffer: number } }
//   FakeAdapter = { requestDevice(): Promise<FakeDevice>, features: Set<string>, limits: Record<string, number> }
//   FakeDevice  = { lost: Promise<{ reason: "unknown" | "destroyed"; message: string }>, createBuffer(desc: { size: number;
//                   usage: number }): { size: number; destroy(): void }, destroy(): void }
// `device.destroy()` resolves `lost` with reason "destroyed" (WebGPU spec 4.1: GPUDeviceLostInfo).
//
// Oracles: the scripted behaviours written in spec 018 section 7.3 (none, null adapter, requestDevice rejection, device lost
// after N ms, buffer allocation failure) and the plan's FR-018-29 row (hang > 2 s); WebGPU spec GPUDeviceLostInfo.reason.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createFakeGpu, type FakeGpuScript, installFakeGpu } from "~/engines/tier/fake-gpu";

beforeEach(() => {
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
});

describe("scripted adapters (section 7.3)", () => {
  it("FR-018-29 · { kind: 'none' } gives no GPU object at all", () => {
    expect(createFakeGpu({ kind: "none" })).toBeUndefined();
  });

  it("FR-018-29 · { kind: 'null-adapter' } resolves requestAdapter with null and counts the call", async () => {
    const gpu = createFakeGpu({ kind: "null-adapter" });
    expect(gpu).toBeDefined();
    await expect(gpu?.requestAdapter()).resolves.toBeNull();
    expect(gpu?.calls.requestAdapter).toBe(1);
    expect(gpu?.calls.requestDevice).toBe(0);
  });

  it("FR-018-29 · { kind: 'ok' } gives an adapter and a device whose buffers can be created and destroyed", async () => {
    const gpu = createFakeGpu({ kind: "ok" });
    const adapter = await gpu?.requestAdapter();
    expect(adapter).not.toBeNull();
    const device = await adapter?.requestDevice();
    expect(device).toBeDefined();
    const buffer = device?.createBuffer({ size: 64, usage: 0 });
    expect(buffer?.size).toBe(64);
    expect(() => buffer?.destroy()).not.toThrow();
    expect(gpu?.calls).toEqual({ requestAdapter: 1, requestDevice: 1, createBuffer: 1 });
  });

  it("FR-018-29 · { kind: 'device-rejects' } rejects requestDevice with the scripted message", async () => {
    const gpu = createFakeGpu({ kind: "device-rejects", message: "no device for you" });
    const adapter = await gpu?.requestAdapter();
    await expect(adapter?.requestDevice()).rejects.toThrow("no device for you");
    expect(gpu?.calls.requestDevice).toBe(1);
  });

  it("FR-018-29 · { kind: 'device-rejects' } without a message still rejects with an Error", async () => {
    const gpu = createFakeGpu({ kind: "device-rejects" });
    const adapter = await gpu?.requestAdapter();
    await expect(adapter?.requestDevice()).rejects.toBeInstanceOf(Error);
  });

  it("FR-018-29 · { kind: 'hang' } leaves requestDevice pending for ever (more than the 2 s probe limit)", async () => {
    const gpu = createFakeGpu({ kind: "hang" });
    const adapter = await gpu?.requestAdapter();
    let settled = false;
    adapter?.requestDevice().then(
      () => {
        settled = true;
      },
      () => {
        settled = true;
      },
    );
    await vi.advanceTimersByTimeAsync(60_000);
    expect(settled).toBe(false);
  });
});

describe("device lost (FR-018-31)", () => {
  it("FR-018-31 · device.lost stays pending until exactly afterMs after the device was granted, then resolves with reason 'unknown'", async () => {
    const gpu = createFakeGpu({ kind: "device-lost", afterMs: 500 });
    const adapter = await gpu?.requestAdapter();
    const device = await adapter?.requestDevice();
    let info: { reason: string; message: string } | undefined;
    device?.lost.then((i: { reason: string; message: string }) => {
      info = i;
    });
    await vi.advanceTimersByTimeAsync(499);
    expect(info).toBeUndefined();
    await vi.advanceTimersByTimeAsync(1);
    expect(info?.reason).toBe("unknown");
    expect(typeof info?.message).toBe("string");
  });

  it("FR-018-31 · afterMs = 0 loses the device on the next tick", async () => {
    const gpu = createFakeGpu({ kind: "device-lost", afterMs: 0 });
    const device = await (await gpu?.requestAdapter())?.requestDevice();
    let reason: string | undefined;
    device?.lost.then((i: { reason: string; message: string }) => {
      reason = i.reason;
    });
    await vi.advanceTimersByTimeAsync(0);
    expect(reason).toBe("unknown");
  });

  it("FR-018-31 · destroy() on a healthy device resolves lost with reason 'destroyed'", async () => {
    const gpu = createFakeGpu({ kind: "ok" });
    const device = await (await gpu?.requestAdapter())?.requestDevice();
    let reason: string | undefined;
    device?.lost.then((i: { reason: string; message: string }) => {
      reason = i.reason;
    });
    device?.destroy();
    await vi.advanceTimersByTimeAsync(0);
    expect(reason).toBe("destroyed");
  });

  it("FR-018-31 · { kind: 'buffer-alloc-fails' } throws from createBuffer and counts the attempt", async () => {
    const gpu = createFakeGpu({ kind: "buffer-alloc-fails" });
    const device = await (await gpu?.requestAdapter())?.requestDevice();
    expect(() => device?.createBuffer({ size: 1 << 30, usage: 0 })).toThrow(/buffer/i);
    expect(gpu?.calls.createBuffer).toBe(1);
  });
});

describe("hostile scripts", () => {
  const bad: Array<[string, unknown]> = [
    ["negative afterMs", { kind: "device-lost", afterMs: -1 }],
    ["NaN afterMs", { kind: "device-lost", afterMs: Number.NaN }],
    ["infinite afterMs", { kind: "device-lost", afterMs: Number.POSITIVE_INFINITY }],
    ["missing afterMs", { kind: "device-lost" }],
    ["string afterMs", { kind: "device-lost", afterMs: "500" }],
    ["unknown kind", { kind: "teleport" }],
    ["missing kind", {}],
    ["null script", null],
    ["a string script", "ok"],
  ];
  for (const [name, script] of bad) {
    it(`FR-018-29 · createFakeGpu rejects ${name} instead of building a half-working double`, () => {
      expect(() => createFakeGpu(script as FakeGpuScript)).toThrow();
    });
  }
});

describe("installFakeGpu", () => {
  it("FR-018-29 · defines navigator.gpu for the script and restore() removes it again", () => {
    const target: { gpu?: unknown } = {};
    const restore = installFakeGpu({ kind: "ok" }, target);
    expect(target.gpu).toBeDefined();
    restore();
    expect(target.gpu).toBeUndefined();
  });

  it("FR-018-29 · { kind: 'none' } hides an existing gpu object and restore() brings the original back", () => {
    const original = { requestAdapter: () => Promise.resolve(null) };
    const target: { gpu?: unknown } = { gpu: original };
    const restore = installFakeGpu({ kind: "none" }, target);
    expect(target.gpu).toBeUndefined();
    restore();
    expect(target.gpu).toBe(original);
  });

  it("FR-018-29 · two installs restore in last-in first-out order", () => {
    const target: { gpu?: unknown } = {};
    const restoreA = installFakeGpu({ kind: "ok" }, target);
    const a = target.gpu;
    const restoreB = installFakeGpu({ kind: "null-adapter" }, target);
    expect(target.gpu).not.toBe(a);
    restoreB();
    expect(target.gpu).toBe(a);
    restoreA();
    expect(target.gpu).toBeUndefined();
  });

  it("FR-018-29 · by default it installs on the global navigator, so code under test sees it", async () => {
    const restore = installFakeGpu({ kind: "null-adapter" });
    try {
      const gpu = (navigator as unknown as { gpu?: { requestAdapter(): Promise<unknown> } }).gpu;
      expect(gpu).toBeDefined();
      await expect(gpu?.requestAdapter()).resolves.toBeNull();
    } finally {
      restore();
    }
    expect((navigator as unknown as { gpu?: unknown }).gpu).toBeUndefined();
  });
});
