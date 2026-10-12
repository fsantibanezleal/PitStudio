// Capability probe (FR-018-29) and the `?tier=` override (FR-018-30). T1 WebGPU > T2 WebAssembly > T0 baked results.
// The probe downloads nothing and never rejects; it runs once per page load and finishes before any engine starts.

export type Tier = "t1" | "t2" | "t0";

export const TIER_ORDER: Record<Tier, number> = { t0: 0, t2: 1, t1: 2 };

interface GpuLike {
  requestAdapter(): Promise<{ requestDevice(): Promise<unknown> } | null>;
}

export const PROBE_MS = 2000;
const MAX_SEARCH = 2000;

/** A WebAssembly module with exactly one function: `() -> ()` with an empty body (core spec 5.5). */
const ONE_FUNCTION_MODULE = new Uint8Array([
  0x00,
  0x61,
  0x73,
  0x6d,
  0x01,
  0x00,
  0x00,
  0x00, // magic and version 1
  0x01,
  0x04,
  0x01,
  0x60,
  0x00,
  0x00, // type section: one type () -> ()
  0x03,
  0x02,
  0x01,
  0x00, // function section: one function of type 0
  0x0a,
  0x04,
  0x01,
  0x02,
  0x00,
  0x0b, // code section: one body, no locals, end
]);

function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("timeout")), ms);
    promise.then(
      (value) => {
        clearTimeout(timer);
        resolve(value);
      },
      (error) => {
        clearTimeout(timer);
        reject(error);
      },
    );
  });
}

async function probeGpu(timeoutMs: number): Promise<boolean> {
  try {
    const gpu = (navigator as unknown as { gpu?: GpuLike }).gpu;
    if (!gpu) return false;
    // One deadline covers both requests: requestDevice must resolve within `timeoutMs` of the start.
    return await withTimeout(
      (async () => {
        const adapter = await gpu.requestAdapter();
        if (!adapter) return false;
        await adapter.requestDevice();
        return true;
      })(),
      timeoutMs,
    );
  } catch {
    return false;
  }
}

async function probeWasm(): Promise<boolean> {
  try {
    if (typeof WebAssembly !== "object" || typeof WebAssembly?.instantiate !== "function") return false;
    await WebAssembly.instantiate(ONE_FUNCTION_MODULE);
    return true;
  } catch {
    return false;
  }
}

export async function probeTier(options: { timeoutMs?: number } = {}): Promise<Tier> {
  const timeoutMs = options.timeoutMs ?? PROBE_MS;
  if (await probeGpu(timeoutMs)) return "t1";
  if (await probeWasm()) return "t2";
  return "t0";
}

let probed: Promise<Tier> | undefined;

/** The probe runs once per page load; every caller shares its result. */
export function whenProbed(): Promise<Tier> {
  probed ??= probeTier();
  return probed;
}

export function resetProbeForTests(): void {
  probed = undefined;
}

/** `start` is not called before the probe has finished and receives the resolved tier. */
export async function startAfterProbe<T>(start: (tier: Tier) => T): Promise<T> {
  return start(await whenProbed());
}

/** `?tier=t2` or `?tier=t0` lower the tier; a higher, unknown, malformed or over-long request is ignored. */
export function resolveTier(probedTier: Tier, search: string): Tier {
  if (typeof search !== "string" || search.length > MAX_SEARCH) return probedTier;
  let asked: string | null = null;
  try {
    asked = new URLSearchParams(search).get("tier");
  } catch {
    return probedTier;
  }
  if (asked !== "t2" && asked !== "t0") return probedTier;
  return TIER_ORDER[asked] <= TIER_ORDER[probedTier] ? asked : probedTier;
}

/** True when a 3D renderer can run: WebGPU or a WebGL 2 context (FR-018-08). */
export function detectThreeD(): boolean {
  try {
    if ((navigator as unknown as { gpu?: unknown }).gpu) return true;
    const canvas = document.createElement("canvas");
    return canvas.getContext("webgl2") !== null;
  } catch {
    return false;
  }
}
