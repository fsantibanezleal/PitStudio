// Shared, locked E2E support (first used by T-018-011; later tasks import it). Not a test file.
// Injects a scripted `navigator.gpu` before any page script runs, the browser-side twin of the unit-test double
// `~/engines/tier/fake-gpu` (spec 018 section 7.3). The in-page object counts its calls in `window.__fakeGpuCalls`.
import type { Page } from "@playwright/test";

export type PageGpuScript =
  | "ok" //             a working adapter and device
  | "none" //           no navigator.gpu
  | "null-adapter" //   requestAdapter() resolves null
  | "device-rejects" // requestDevice() rejects
  | { lostAfterMs: number }; // device.lost resolves this long after the device was granted

export async function injectGpu(page: Page, script: PageGpuScript): Promise<void> {
  await page.addInitScript((s) => {
    const calls = { requestAdapter: 0, requestDevice: 0, createBuffer: 0 };
    (window as unknown as { __fakeGpuCalls: typeof calls }).__fakeGpuCalls = calls;
    if (s === "none") {
      Object.defineProperty(navigator, "gpu", { value: undefined, configurable: true });
      return;
    }
    const makeDevice = () => {
      let resolveLost: (info: { reason: string; message: string }) => void = () => undefined;
      const lost = new Promise<{ reason: string; message: string }>((r) => {
        resolveLost = r;
      });
      if (typeof s === "object") {
        setTimeout(() => resolveLost({ reason: "unknown", message: "scripted device loss" }), s.lostAfterMs);
      }
      return {
        lost,
        queue: {},
        features: new Set<string>(),
        limits: {},
        createBuffer(desc: { size: number }) {
          calls.createBuffer++;
          return { size: desc.size, destroy() {} };
        },
        destroy() {
          resolveLost({ reason: "destroyed", message: "destroyed by the page" });
        },
      };
    };
    const adapter = {
      features: new Set<string>(),
      limits: {},
      requestDevice() {
        calls.requestDevice++;
        if (s === "device-rejects") return Promise.reject(new Error("scripted requestDevice rejection"));
        return Promise.resolve(makeDevice());
      },
    };
    const gpu = {
      requestAdapter() {
        calls.requestAdapter++;
        return Promise.resolve(s === "null-adapter" ? null : adapter);
      },
      getPreferredCanvasFormat() {
        return "bgra8unorm";
      },
    };
    Object.defineProperty(navigator, "gpu", { value: gpu, configurable: true });
  }, script);
}
