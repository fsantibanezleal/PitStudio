// Shared, locked E2E support for the @gpu kernel tasks (T-018-059, -065, -067). Not a test file. These tests run only in the Playwright project `webgpu`
// on a machine with a WebGPU adapter; elsewhere they are reported "not run", never "passed" (spec 018 section 7.3).
//
// Hook contract invented by the test author (flagged in the red report): on the parity route `<base>parity/` opened with `?tier=t1`,
//   window.__pitstudio.host.requestWithBuffers(doc, buffers) -> Promise<{ response, buffers }>
// calls the page's engine host with the DC-018-02 request `doc` (engine, engine_version "0.1.0", function, args). Buffer arguments (descriptors with dtype,
// shape and byte_length in `args`) are supplied by name in `buffers` as plain number arrays (float32 data) and the response buffers come back the same way.
import { expect, type Page } from "@playwright/test";
import { open } from "../helpers";

export interface BufferArg {
  /** name of the argument in `args` */
  name: string;
  values: number[];
  /** the shape written in the descriptor, e.g. { particles: 3, components: 3 } */
  shape: Record<string, number>;
}

export async function openGpuRunner(page: Page): Promise<void> {
  await open(page, "parity/?tier=t1");
  await page.waitForFunction(
    () =>
      (window as unknown as { __pitstudio?: { parity?: { ready?: boolean } } }).__pitstudio?.parity?.ready ===
      true,
    undefined,
    { timeout: 60_000 },
  );
  const tier = await page.evaluate(
    () => (window as unknown as { __pitstudio: { tier?: string } }).__pitstudio.tier,
  );
  expect(tier, "the runner is on tier T1 (a WebGPU device was granted)").toBe("t1");
}

export interface GpuReply {
  response: { kind: string; result?: Record<string, unknown>; code?: string; message?: string };
  buffers: Record<string, number[]>;
}

export async function gpuCall(
  page: Page,
  engine: string,
  fn: string,
  args: Record<string, unknown>,
  buffers: BufferArg[] = [],
): Promise<GpuReply> {
  const withDescriptors: Record<string, unknown> = { ...args };
  const data: Record<string, number[]> = {};
  for (const b of buffers) {
    withDescriptors[b.name] = { dtype: "float32", shape: b.shape, byte_length: b.values.length * 4 };
    data[b.name] = b.values;
  }
  const doc = { kind: "input", engine, engine_version: "0.1.0", function: fn, args: withDescriptors };
  return page.evaluate(
    ([d, bufs]) =>
      (
        window as unknown as {
          __pitstudio: {
            host: { requestWithBuffers(doc: unknown, buffers: Record<string, number[]>): Promise<GpuReply> };
          };
        }
      ).__pitstudio.host.requestWithBuffers(d, bufs as Record<string, number[]>),
    [doc, data] as const,
  );
}

/** A small deterministic generator (mulberry32) so a property test can be replayed from its seed. */
export function rng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
