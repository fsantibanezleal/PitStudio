// Shared, locked E2E support (first used by T-018-051; later parity tasks import it). Not a test file.
//
// The in-browser parity runner (spec 018 plan, `web/e2e/parity/`): an unlisted prerendered route `<base>parity/` that loads the browser
// engines and exposes them to Playwright. Hook contract invented by the test author (flagged in the red report):
//   window.__pitstudio.parity.ready === true once the runner has loaded
//   window.__pitstudio.parity.pcg64Words(entropy: string, spawnKey: number[], n: number): string[]      n 64-bit words, decimal strings
//   window.__pitstudio.parity.pcg64Doubles(entropy: string, spawnKey: number[], n: number): number[]    n random() values
//   window.__pitstudio.parity.run(engine: string, fixture: unknown): Promise<ParityResult>     runs a DC-018-04 fixture through the engine
// The runner never touches the network after load. Tests run in every Playwright project (chromium, firefox, webkit).
import { expect, type Page } from "@playwright/test";
import { open } from "../helpers";

export interface ParityResult {
  engine: string;
  fixture: string;
  vectors: number;
  mismatches: number;
  verdict: "pass" | "fail";
  maxError: Record<string, number>;
  details?: string[];
}

export async function openParityRunner(page: Page): Promise<void> {
  await open(page, "parity/");
  await page.waitForFunction(
    () =>
      (window as unknown as { __pitstudio?: { parity?: { ready?: boolean } } }).__pitstudio?.parity?.ready ===
      true,
    undefined,
    { timeout: 30_000 },
  );
  await expect(page).toHaveURL(/parity\/?/);
}

export async function runParity(page: Page, engine: string, fixture: unknown): Promise<ParityResult> {
  return page.evaluate(
    ([e, f]) =>
      (
        window as unknown as {
          __pitstudio: { parity: { run(engine: string, fixture: unknown): Promise<ParityResult> } };
        }
      ).__pitstudio.parity.run(e as string, f),
    [engine, fixture] as const,
  );
}
