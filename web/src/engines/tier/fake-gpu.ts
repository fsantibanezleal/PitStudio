// Fake GPU backend (spec 018 section 7.3). The hosted CI runner has no GPU, so FR-018-29 (capability probe) and
// FR-018-31 (device lost -> fallback) are tested against this scripted double.

export type FakeGpuScript =
  | { kind: "ok" }
  | { kind: "none" }
  | { kind: "null-adapter" }
  | { kind: "device-rejects"; message?: string }
  | { kind: "device-lost"; afterMs: number }
  | { kind: "buffer-alloc-fails" }
  | { kind: "hang" };

export interface FakeBuffer {
  size: number;
  destroy(): void;
}

export interface FakeDevice {
  lost: Promise<{ reason: "unknown" | "destroyed"; message: string }>;
  createBuffer(desc: { size: number; usage: number }): FakeBuffer;
  destroy(): void;
}

export interface FakeAdapter {
  requestDevice(): Promise<FakeDevice>;
  features: Set<string>;
  limits: Record<string, number>;
}

export interface FakeGpu {
  requestAdapter(): Promise<FakeAdapter | null>;
  calls: { requestAdapter: number; requestDevice: number; createBuffer: number };
}

const KINDS = new Set([
  "ok",
  "none",
  "null-adapter",
  "device-rejects",
  "device-lost",
  "buffer-alloc-fails",
  "hang",
]);

function validate(script: unknown): FakeGpuScript {
  if (typeof script !== "object" || script === null) throw new TypeError("fake GPU script must be an object");
  const s = script as Record<string, unknown>;
  if (typeof s.kind !== "string" || !KINDS.has(s.kind))
    throw new TypeError(`unknown fake GPU script kind: ${String(s.kind)}`);
  if (s.kind === "device-lost") {
    if (typeof s.afterMs !== "number" || !Number.isFinite(s.afterMs) || s.afterMs < 0) {
      throw new TypeError("device-lost needs a finite afterMs >= 0");
    }
  }
  if (s.kind === "device-rejects" && s.message !== undefined && typeof s.message !== "string") {
    throw new TypeError("device-rejects message must be a string");
  }
  return script as FakeGpuScript;
}

export function createFakeGpu(input: FakeGpuScript): FakeGpu | undefined {
  const script = validate(input);
  if (script.kind === "none") return undefined;
  const calls = { requestAdapter: 0, requestDevice: 0, createBuffer: 0 };

  const makeDevice = (): FakeDevice => {
    let resolveLost: (info: { reason: "unknown" | "destroyed"; message: string }) => void = () => {};
    const lost = new Promise<{ reason: "unknown" | "destroyed"; message: string }>((resolve) => {
      resolveLost = resolve;
    });
    if (script.kind === "device-lost") {
      setTimeout(() => resolveLost({ reason: "unknown", message: "fake device lost" }), script.afterMs);
    }
    return {
      lost,
      createBuffer(desc) {
        calls.createBuffer += 1;
        if (script.kind === "buffer-alloc-fails") throw new Error("fake GPU: buffer allocation failed");
        return { size: desc.size, destroy() {} };
      },
      destroy() {
        resolveLost({ reason: "destroyed", message: "device destroyed" });
      },
    };
  };

  const adapter: FakeAdapter = {
    features: new Set<string>(),
    limits: { maxBufferSize: 268435456, maxStorageBufferBindingSize: 134217728 },
    requestDevice() {
      calls.requestDevice += 1;
      if (script.kind === "hang") return new Promise<FakeDevice>(() => {});
      if (script.kind === "device-rejects") {
        return Promise.reject(new Error(script.message ?? "fake GPU: requestDevice rejected"));
      }
      return Promise.resolve(makeDevice());
    },
  };

  return {
    calls,
    requestAdapter() {
      calls.requestAdapter += 1;
      return Promise.resolve(script.kind === "null-adapter" ? null : adapter);
    },
  };
}

/** Defines `target.gpu` (default: the global navigator); returns a LIFO-safe restore function. */
export function installFakeGpu(
  script: FakeGpuScript,
  target: { gpu?: unknown } = navigator as { gpu?: unknown },
): () => void {
  const gpu = createFakeGpu(script);
  const had = Object.hasOwn(target, "gpu");
  const previous = (target as { gpu?: unknown }).gpu;
  Object.defineProperty(target, "gpu", { value: gpu, configurable: true, writable: true, enumerable: true });
  return () => {
    if (had) {
      Object.defineProperty(target, "gpu", {
        value: previous,
        configurable: true,
        writable: true,
        enumerable: true,
      });
    } else {
      delete (target as { gpu?: unknown }).gpu;
    }
  };
}
