import { useEffect, useState } from "react";

export type Tier = "t1" | "t2" | "t0";

interface GpuLike {
  requestAdapter(): Promise<{ requestDevice(): Promise<unknown> } | null>;
}

const PROBE_MS = 2000;

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

/**
 * Capability probe of FR-018-29: T1 when WebGPU gives an adapter and a device within 2 s, else T2 when WebAssembly
 * is available, else T0. It downloads nothing. (The `?tier=` override and the fallback chain belong to T-018-010/011.)
 */
export async function probeTier(): Promise<Tier> {
  try {
    const gpu = (navigator as unknown as { gpu?: GpuLike }).gpu;
    if (gpu) {
      const adapter = await withTimeout(gpu.requestAdapter(), PROBE_MS);
      if (adapter) {
        await withTimeout(adapter.requestDevice(), PROBE_MS);
        return "t1";
      }
    }
  } catch {
    // no usable WebGPU device: fall through to WebAssembly
  }
  try {
    if (typeof WebAssembly === "object" && typeof WebAssembly.instantiate === "function") {
      // The smallest valid module: magic number and version 1.
      const module = new Uint8Array([0x00, 0x61, 0x73, 0x6d, 0x01, 0x00, 0x00, 0x00]);
      await WebAssembly.instantiate(module);
      return "t2";
    }
  } catch {
    // no WebAssembly: baked results only
  }
  return "t0";
}

/** True when a 3D renderer can run: WebGPU or a WebGL 2 context (FR-018-08). null until it has been checked. */
export function detectThreeD(): boolean {
  try {
    if ((navigator as unknown as { gpu?: unknown }).gpu) return true;
    const canvas = document.createElement("canvas");
    return canvas.getContext("webgl2") !== null;
  } catch {
    return false;
  }
}

export function useTier(): Tier | null {
  const [tier, setTier] = useState<Tier | null>(null);
  useEffect(() => {
    let live = true;
    void probeTier().then((t) => {
      if (live) setTier(t);
    });
    return () => {
      live = false;
    };
  }, []);
  return tier;
}

export function useThreeD(): boolean | null {
  const [available, setAvailable] = useState<boolean | null>(null);
  useEffect(() => setAvailable(detectThreeD()), []);
  return available;
}
