// T-018-063 [red] · FR-018-58 in the browser: on every golden image of the detector fixtures the WASM path (ONNX Runtime Web, post-processor inside the
// graph, no NMS) gives `boxes` within 0.5 px of ONNX Runtime CPU and `labels` in top-1 agreement >= 0.995. Unit half:
// web/src/engines/ml/t_018_063_detector.test.ts. The WebGPU path (1 px) is checked in web/e2e/gpu/t_018_060_onnx_webgpu.spec.ts.
//
// Runner hooks: web/e2e/support/parity.ts (`window.__pitstudio.parity.run("detector", fixture)` on `<base>parity/`, in each Playwright project).
// A ParityResult for the detector carries maxError.abs_px (largest absolute box error in px) and maxError.top1_agreement (fraction of matching labels).
// Oracles: the thresholds web.detector_box_px_max.wasm = 0.5 and web.top1_agreement_min = 0.995 (specs/000-foundation/thresholds.yaml, spec 018 section 7.2);
// the reference outputs inside the fixtures (ONNX Runtime CPU on the spec 009 export, DC-018-04, class detector-wasm).
import { expect, test } from "@playwright/test";
import { loadParityFixtures } from "../../src/test-support/parity-fixtures";
import { openParityRunner, runParity } from "../support/parity";

const fixtures = loadParityFixtures("detector").filter((f) => f.function === "detect");

test.describe("detector parity on the WASM path (FR-018-58)", () => {
  test("FR-018-58 · the committed fixtures hold at least one golden detector set of class detector-wasm with the 0.5 px and 0.995 tolerances", () => {
    expect(
      fixtures.length,
      "a detector fixture under web/tests/fixtures/parity/detector exists",
    ).toBeGreaterThan(0);
    for (const fx of fixtures) {
      expect(fx.tolerance.class, fx.file).toBe("detector-wasm");
      expect(fx.tolerance.max_abs_px, fx.file).toBeLessThanOrEqual(0.5);
      expect(fx.tolerance.top1_agreement_min as number, fx.file).toBeGreaterThanOrEqual(0.995);
      expect(fx.cases.length, `${fx.file}: golden images`).toBeGreaterThan(0);
    }
  });

  for (const fx of fixtures) {
    test(`FR-018-58 · ${fx.file}: boxes within 0.5 px and labels in top-1 agreement >= 0.995 on all ${fx.cases.length} golden images`, async ({
      page,
    }) => {
      await openParityRunner(page);
      const r = await runParity(page, "detector", fx);
      expect(r.vectors).toBe(fx.cases.length);
      expect(r.verdict).toBe("pass");
      expect(r.maxError.abs_px).toBeLessThanOrEqual(0.5);
      expect(r.maxError.top1_agreement).toBeGreaterThanOrEqual(0.995);
    });
  }

  test("FR-018-58 · the runner knows the detector engine (an unknown engine id is reported, not run)", async ({
    page,
  }) => {
    await openParityRunner(page);
    const known = await page.evaluate(async () => {
      const p = (window as unknown as { __pitstudio: { parity: { engines?: string[] } } }).__pitstudio.parity;
      return p.engines ?? [];
    });
    expect(known).toContain("detector");
  });
});
