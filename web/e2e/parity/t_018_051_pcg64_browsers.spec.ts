// T-018-051 [red] · P-018-04 and P-018-75 in the browser: the PCG64 + SeedSequence port emits numpy's words and doubles in Chromium,
// Firefox and WebKit (SC-018-01: TS classes pass in the three browsers). Unit half: web/src/engines/random/t_018_051_pcg64.test.ts.
//
// Runner hooks: web/e2e/support/parity.ts (`window.__pitstudio.parity.pcg64Words` / `pcg64Doubles` on the route `<base>parity/`).
// Oracle: numpy 2.5.3 output committed beside the unit test (t_018_051_numpy_reference.json: SHA-256 of the 10^4 words and doubles
// per stream, first words, words at fixed indices) and the exact conversion (word >> 11) x 2^-53.
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import { openParityRunner } from "../support/parity";

const HERE = dirname(fileURLToPath(import.meta.url));
interface Stream {
  entropy: string;
  spawn_key: number[];
  first_words: string[];
  words_sha256: string;
  doubles_sha256: string;
  word_at: Record<string, string>;
}
const ref = JSON.parse(
  readFileSync(resolve(HERE, "../../src/engines/random/t_018_051_numpy_reference.json"), "utf8"),
) as { streams: Stream[] };

declare global {
  interface Window {
    __pitstudio: {
      parity: {
        pcg64Words(entropy: string, spawnKey: number[], n: number): string[];
        pcg64Doubles(entropy: string, spawnKey: number[], n: number): number[];
      };
    };
  }
}

test.describe("PCG64 in the browser (P-018-04, P-018-75)", () => {
  for (const s of ref.streams) {
    test(`P-018-04 · entropy ${s.entropy.slice(0, 10)}, spawn_key [${s.spawn_key}]: 10^4 words and doubles equal numpy's`, async ({
      page,
    }) => {
      await openParityRunner(page);
      const words = await page.evaluate(
        ([e, k]) => window.__pitstudio.parity.pcg64Words(e as string, k as number[], 10_000),
        [s.entropy, s.spawn_key] as const,
      );
      expect(words).toHaveLength(10_000);
      expect(words.slice(0, 6)).toEqual(s.first_words);
      for (const [i, w] of Object.entries(s.word_at)) expect(words[Number(i)]).toBe(w);
      const buf = Buffer.alloc(8 * words.length);
      words.forEach((w, i) => {
        buf.writeBigUInt64LE(BigInt(w), i * 8);
      });
      expect(createHash("sha256").update(buf).digest("hex")).toBe(s.words_sha256);

      const doubles = await page.evaluate(
        ([e, k]) => window.__pitstudio.parity.pcg64Doubles(e as string, k as number[], 10_000),
        [s.entropy, s.spawn_key] as const,
      );
      const f64 = Float64Array.from(doubles);
      expect(createHash("sha256").update(new Uint8Array(f64.buffer)).digest("hex")).toBe(s.doubles_sha256);
      // P-018-75: each double is (word >> 11) x 2^-53 of its word and lies in [0, 1)
      for (let i = 0; i < words.length; i++) {
        const w = BigInt(words[i] as string);
        expect(f64[i]).toBe(Number(w >> 11n) * 2 ** -53);
        expect((f64[i] as number) >= 0 && (f64[i] as number) < 1).toBe(true);
      }
    });
  }

  test("P-018-04 · the runner does not hit the network after it has loaded", async ({ page }) => {
    await openParityRunner(page);
    const seen: string[] = [];
    page.on("request", (r) => seen.push(r.url()));
    await page.evaluate(() => window.__pitstudio.parity.pcg64Words("20261007", [], 1000));
    expect(seen).toEqual([]);
  });
});

test.describe("browser matrix (SC-018-01)", () => {
  test("SC-018-01 · the Playwright configuration defines the projects chromium, firefox and webkit (and webgpu for the @gpu tasks)", () => {
    const config = readFileSync(resolve(HERE, "../../playwright.config.ts"), "utf8");
    for (const name of ["chromium", "firefox", "webkit", "webgpu"]) {
      expect(config, `project ${name}`).toMatch(new RegExp(`name:\\s*["']${name}["']`));
    }
  });
});
