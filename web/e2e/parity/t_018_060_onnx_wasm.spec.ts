// T-018-060 [red] · FR-018-57 in CI: every live ONNX model matches ONNX Runtime CPU (Python) on its golden set within max abs 1e-4 on the WASM fp32 path
// (`web.wasm_fp32_max_abs`), with top-1 agreement >= 0.995 for classifiers (`web.top1_agreement_min`), in Chromium, Firefox and WebKit. The WebGPU paths are
// in web/e2e/gpu/t_018_060_onnx_webgpu.spec.ts. Dispatch policies follow FR-007-32 (hosted, T-018-052); the detector is T-018-063.
//
// Runner hooks: web/e2e/support/parity.ts (`window.__pitstudio.parity.run(engine, fixture)`); a ParityResult carries maxError.abs and, for classifiers,
// maxError.top1_agreement. Engines with an ORT-web model of this spec (section 7.1): gns, forecasters, fno, meta-model, unet.
// Oracles: the reference outputs of ONNX Runtime CPU inside the fixtures (DC-018-04, class ml-wasm-fp32: >= 200 inputs each) and the thresholds above.
import { expect, test } from "@playwright/test";
import { loadParityFixtures } from "../../src/test-support/parity-fixtures";
import { openParityRunner, runParity } from "../support/parity";

const ENGINES = ["gns", "forecasters", "fno", "meta-model", "unet"] as const;

test.describe("ORT-web WASM parity (FR-018-57)", () => {
  for (const engine of ENGINES) {
    const fixtures = loadParityFixtures(engine).filter((f) => f.tolerance.class === "ml-wasm-fp32");

    test(`FR-018-57 · ${engine}: a WASM fp32 fixture of at least 200 golden inputs exists with the 1e-4 tolerance`, () => {
      expect(fixtures.length, `a ml-wasm-fp32 fixture for ${engine} exists`).toBeGreaterThan(0);
      for (const fx of fixtures) {
        expect(fx.tolerance.max_abs as number, fx.file).toBeLessThanOrEqual(1e-4);
        expect(fx.cases.length, `${fx.file}: golden inputs`).toBeGreaterThanOrEqual(200);
      }
    });

    for (const fx of fixtures) {
      test(`FR-018-57 · ${fx.file}: max abs difference to ONNX Runtime CPU <= 1e-4 on all ${fx.cases.length} inputs`, async ({
        page,
      }) => {
        await openParityRunner(page);
        const r = await runParity(page, engine, fx);
        expect(r.vectors).toBe(fx.cases.length);
        expect(r.verdict).toBe("pass");
        expect(r.maxError.abs).toBeLessThanOrEqual(1e-4);
        if (r.maxError.top1_agreement !== undefined)
          expect(r.maxError.top1_agreement).toBeGreaterThanOrEqual(0.995);
      });
    }
  }

  test("FR-018-57 · the runner reports the runtime configuration: ORT-web on one thread, WASM execution provider, same origin", async ({
    page,
  }) => {
    await openParityRunner(page);
    const info = await page.evaluate(() => {
      const w = window as unknown as {
        __pitstudio: { runtime?: { ort?: { numThreads?: number; executionProvider?: string } } };
      };
      return w.__pitstudio.runtime?.ort ?? null;
    });
    expect(info).not.toBeNull();
    expect(info?.numThreads).toBe(1);
    expect(info?.executionProvider).toBe("wasm");
  });
});
