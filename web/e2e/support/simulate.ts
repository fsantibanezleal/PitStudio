// Shared, locked E2E support (first used by T-018-014; later tasks import it). Not a test file.
//
// The Simulate (live) tab of a case page (FR-018-14) has no DOM contract in spec 018, so this file fixes the observation hooks
// that every E2E task about engines, runtimes and hostile inputs relies on. They are test hooks invented by the test author
// (flagged in the red report); the green commit must provide them.
//
//   Route:  /cases/<ID>/?tab=simulate  (or a click on the "Simulate (live)" tab)
//   One engine panel per engine listed for the case in the registry (`engines`, spec 018 section 7.1):
//     [data-testid="engine-panel"][data-engine="<engine id>"]
//        data-state     idle | loading | running | done | error | replay     "replay": the T0 fallback, or a GPU-compute engine on T2
//        data-requests  integer, engine requests sent so far: starts at 0, +1 per accepted request, never for a rejected input
//        data-tier      t1 | t2 | t0, the tier this engine currently runs on
//        [data-testid="lane-badge"]          text LIVE (computed in this browser) or REPLAY (baked / T0 fallback)
//        input[data-control="<name>"]        numeric controls, with data-min, data-max (numbers) and data-unit (text)
//        [data-testid="control-message"]     inline message of a rejected value (allowed range and unit); absent when the value is valid
//        [data-testid="engine-notice"]       texts such as "needs WebGPU to compute live", "parity not confirmed — showing
//                                            precomputed results", "<runtime> could not load — showing precomputed results"
//   Runtime progress: [data-testid="runtime-progress"][role="progressbar"] with aria-valuenow (bytes received), aria-valuemax
//        (manifest size in bytes) and a text "<received> / <total>"; its button [data-testid="runtime-abort"] (name "Abort").
//   Python button: a button named "Run in Python" inside the panel of an analytical engine; its result table has
//        [data-testid="python-result"] with data-verdict="pass" | "fail" and "Python reference could not load" on failure.
//   Page hook (read only): window.__pitstudio = { runtime: { ort?: { numThreads: number } } }
//
// Runtime files are same-origin under `<base>assets/runtimes/<ort|rapier|pyodide>/...` (budget class `runtimes`, NFR-020-03).
import { expect, type Locator, type Page, type Request } from "@playwright/test";
import { open } from "../helpers";

export const RUNTIME_URL = /\/assets\/runtimes\/(ort|rapier|pyodide)\//;

/** Opens the Simulate tab of a case through its URL and waits for the tab list. */
export async function openSimulate(page: Page, caseId: string, extra = ""): Promise<void> {
  await open(page, `cases/${caseId}/?tab=simulate${extra}`);
  await expect(page.getByRole("tab", { selected: true })).toContainText(/Simulate|Simular/);
}

export function enginePanel(page: Page, engine: string): Locator {
  return page.locator(`[data-testid="engine-panel"][data-engine="${engine}"]`);
}

/** Records every request the page makes, with its URL (resolved) and resource type. */
export function recordRequests(page: Page): {
  urls: () => string[];
  runtime: () => string[];
  clear: () => void;
} {
  let seen: string[] = [];
  page.on("request", (r: Request) => {
    seen.push(r.url());
  });
  return {
    urls: () => [...seen],
    runtime: () => seen.filter((u) => RUNTIME_URL.test(u)),
    clear: () => {
      seen = [];
    },
  };
}

export function isLoopbackHost(hostname: string): boolean {
  return (
    hostname === "localhost" ||
    hostname === "127.0.0.1" ||
    hostname === "[::1]" ||
    hostname === "::1" ||
    hostname === "0.0.0.0" ||
    /^127\.\d+\.\d+\.\d+$/.test(hostname)
  );
}
