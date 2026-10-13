// T-018-060 [red, @gpu, not run here] · FR-018-57 on WebGPU: every live ONNX model matches ONNX Runtime CPU within max abs 1e-3 on the WebGPU fp32 path
// (`web.webgpu_fp32_max_abs`) and 1e-2 on fp16 paths (`web.fp16_max_abs`), top-1 agreement >= 0.995 for classifiers and detectors; the detector's boxes are
// within 1 px (FR-018-58, `web.detector_box_px_max.webgpu`). Runs only in the Playwright project `webgpu` on a machine with a WebGPU adapter and is reported
// "not run" elsewhere, never "passed" (spec 018 section 7.3). The WASM half is web/e2e/parity/t_018_060_onnx_wasm.spec.ts.
//
// Runner hooks: web/e2e/support/parity.ts; with `?tier=t1` the runner uses the ORT-web WebGPU execution provider. Fixtures: DC-018-04 classes ml-webgpu-fp32,
// ml-fp16 and detector-webgpu (the same golden inputs as the WASM class).
import { expect, test } from "@playwright/test";
import { loadParityFixtures } from "../../src/test-support/parity-fixtures";
import { openParityRunner, runParity } from "../support/parity";

const ENGINES = ["gns", "forecasters", "fno", "meta-model", "unet", "detector"] as const;
const BOUND: Record<string, number> = { "ml-webgpu-fp32": 1e-3, "ml-fp16": 1e-2 };

test.describe("ORT-web WebGPU parity @gpu (FR-018-57, FR-018-58)", () => {
  test("FR-018-57 · @gpu a WebGPU adapter is available in this project and the runner uses it", async ({
    page,
  }) => {
    await openParityRunner(page);
    const gpu = await page.evaluate(async () => {
      const adapter = await (
        navigator as unknown as { gpu?: { requestAdapter(): Promise<unknown> } }
      ).gpu?.requestAdapter();
      return adapter !== null && adapter !== undefined;
    });
    expect(gpu).toBe(true);
  });

  for (const engine of ENGINES) {
    const fixtures = loadParityFixtures(engine).filter((f) =>
      ["ml-webgpu-fp32", "ml-fp16", "detector-webgpu"].includes(f.tolerance.class),
    );
    test(`FR-018-57 · @gpu ${engine}: WebGPU fixtures exist`, () => {
      expect(fixtures.length, `a WebGPU or fp16 fixture for ${engine} exists`).toBeGreaterThan(0);
    });
    for (const fx of fixtures) {
      test(`FR-018-57 · @gpu ${fx.file}: within the ${fx.tolerance.class} tolerance on all ${fx.cases.length} inputs`, async ({
        page,
      }) => {
        await openParityRunner(page);
        const r = await runParity(page, engine, fx);
        expect(r.verdict).toBe("pass");
        if (fx.tolerance.class === "detector-webgpu") {
          expect(r.maxError.abs_px).toBeLessThanOrEqual(1);
          expect(r.maxError.top1_agreement).toBeGreaterThanOrEqual(0.995);
        } else {
          expect(r.maxError.abs).toBeLessThanOrEqual(BOUND[fx.tolerance.class] as number);
        }
      });
    }
  }
});
