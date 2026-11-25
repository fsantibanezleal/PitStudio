// T-020-035 [red] · FR-020-28 (Acceleration tab: per model and backend latency p50 and p95 (ms), throughput (items/s), energy per inference (J), accuracy change (percentage points) and the parity verdict; failing variants listed as
// "rejected" with the reason; the conditions: GPU, driver, enforced power limit, throttle fractions, TensorRT licence SHA-256 and "our hardware, not a comparative benchmark"), FR-020-30 (a TensorRT row whose licence SHA-256 differs from the
// reviewed c86915fd95bbefbdda3135aace3e6ad6b4612846dcbdbc5d2f5a38b139dd88b4 has its numbers replaced by "measured locally, not published (licence)") and FR-000-08.
//
// Expected API: `~/results/tabs/AccelerationTab` (web/src/results/tabs/AccelerationTab.tsx): named export AccelerationTab({ bundles: AccelerationBundle[] }), the published acceleration bundles of DC-020-02
// (`conditions` { gpu, driver, power_limit_enforced_w, throttle_frac { sw_power_cap, sw_thermal, hw_thermal, hw_slowdown, power_brake }, versions }, `rows` [{ model, backend, precision, status "accepted" | "rejected" | "not-run", reason?,
// latency_ms { p50, p95 }, throughput_items_per_s, energy_j_per_inference, accuracy_delta_pp, parity "pass" | "rejected" | "not-run", tensorrt_licence_sha256? }]).
// Hooks: tr[data-accel-row][data-model][data-backend][data-precision][data-status] with [data-field="latency-p50" | "latency-p95" | "throughput" | "energy" | "accuracy-delta" | "parity"] (numbers as text with the unit), a rejected row also
//   [data-field="reason"]; a row whose numbers are replaced carries [data-field="licence-withheld"] with the sentence and none of the numeric fields; [data-testid="conditions"] with the GPU, the driver, "<W> W", the five throttle fractions
//   as percentages, the licence SHA-256 in full and "our hardware, not a comparative benchmark"; "Not yet run" when there is no bundle. The reviewed digest is exported as `REVIEWED_TENSORRT_LICENCE_SHA256`.
// Oracles: the valid acceleration bundle of DC-020-02 (specs/020-web-knowledge/contracts/examples/results.valid-acceleration.json: d-fine-n on pytorch fp32 9.8 / 11.2 ms, 410 items/s, 0.21 J, 0.0 pp; tensorrt fp16 2.1 / 2.6 ms, 1890 items/s,
// 0.05 J, -0.3 pp with the reviewed digest; tensorrt int8 rejected: "parity: task metric moved by 1.8 percentage points"; GPU 582.78 driver, 110 W, sw_power_cap 0.12), the reviewed digest written in the spec, hand variations.
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { describe, expect, it } from "vitest";
import { AccelerationTab, REVIEWED_TENSORRT_LICENCE_SHA256 } from "~/results/tabs/AccelerationTab";
import { renderApp } from "~/test-support/render";

const REVIEWED = "c86915fd95bbefbdda3135aace3e6ad6b4612846dcbdbc5d2f5a38b139dd88b4";
const example = JSON.parse(
  readFileSync(
    resolve(
      dirname(fileURLToPath(import.meta.url)),
      "../../../specs/020-web-knowledge/contracts/examples/results.valid-acceleration.json",
    ),
    "utf8",
  ),
) as { rows: Array<Record<string, unknown>>; conditions: Record<string, unknown> };
const render = (bundles: unknown[] = [example], lang: "en" | "es" = "en") =>
  renderApp(createElement(AccelerationTab, { bundles: bundles as never }), { lang });
const row = (model: string, backend: string, precision: string) =>
  document.querySelector<HTMLElement>(
    `tr[data-accel-row][data-model="${model}"][data-backend="${backend}"][data-precision="${precision}"]`,
  ) as HTMLElement;
const field = (r: HTMLElement, f: string) => r.querySelector(`[data-field="${f}"]`)?.textContent ?? "";
const withRows = (rows: unknown[]) => ({ ...example, rows });
const trt = (sha: string, over: Record<string, unknown> = {}) => ({
  model: "d-fine-n",
  backend: "tensorrt",
  precision: "fp16",
  status: "accepted",
  latency_ms: { p50: 2.1, p95: 2.6 },
  throughput_items_per_s: 1890,
  energy_j_per_inference: 0.05,
  accuracy_delta_pp: -0.3,
  parity: "pass",
  tensorrt_licence_sha256: sha,
  ...over,
});

describe("rows per model and backend (FR-020-28)", () => {
  it("FR-020-28 · the pytorch fp32 row shows latency p50 and p95, throughput, energy, accuracy change and parity", async () => {
    await render();
    const r = row("d-fine-n", "pytorch", "fp32");
    expect(field(r, "latency-p50")).toContain("9.8");
    expect(field(r, "latency-p95")).toContain("11.2");
    expect(field(r, "latency-p50")).toMatch(/ms/);
    expect(field(r, "throughput")).toContain("410");
    expect(field(r, "energy")).toContain("0.21");
    expect(field(r, "accuracy-delta")).toMatch(/0(\.0)?/);
    expect(field(r, "accuracy-delta")).toMatch(/pp|percentage/i);
    expect(field(r, "parity")).toContain("pass");
  });

  it("FR-020-28 · a TensorRT row with the reviewed licence digest shows its numbers, the accuracy change with its sign", async () => {
    await render();
    const r = row("d-fine-n", "tensorrt", "fp16");
    expect(field(r, "latency-p50")).toContain("2.1");
    expect(field(r, "latency-p95")).toContain("2.6");
    expect(field(r, "throughput")).toContain("1890");
    expect(field(r, "energy")).toContain("0.05");
    expect(field(r, "accuracy-delta")).toMatch(/-0\.3|−0\.3/);
    expect(r.querySelector('[data-field="licence-withheld"]')).toBeNull();
  });

  it("FR-020-28 · a failing variant is listed as 'rejected' with its reason", async () => {
    await render();
    const r = row("d-fine-n", "tensorrt", "int8");
    expect(r.getAttribute("data-status")).toBe("rejected");
    expect(r.textContent).toMatch(/rejected/i);
    expect(field(r, "reason")).toContain("parity: task metric moved by 1.8 percentage points");
  });

  it("FR-020-28 · every row of the bundle is on the page, once, in the order of the bundle", async () => {
    await render();
    const seen = Array.from(document.querySelectorAll("tr[data-accel-row]")).map(
      (r) => `${r.getAttribute("data-backend")}/${r.getAttribute("data-precision")}`,
    );
    expect(seen).toEqual(example.rows.map((r) => `${r.backend}/${r.precision}`));
  });

  it("FR-020-28 · a row that did not run reads 'Not yet run' and shows no number", async () => {
    await render([
      withRows([
        { model: "m", backend: "ort-cuda", precision: "fp16", status: "not-run", parity: "not-run" },
      ]),
    ]);
    const r = row("m", "ort-cuda", "fp16");
    expect(r.textContent).toContain("Not yet run");
    expect(r.querySelector('[data-field="latency-p50"]')).toBeNull();
  });

  it("FR-020-28 · with no bundle the tab reads 'Not yet run' and shows no row and no number", async () => {
    await render([]);
    expect(document.body.textContent).toContain("Not yet run");
    expect(document.querySelectorAll("tr[data-accel-row]")).toHaveLength(0);
  });
});

describe("conditions (FR-020-28)", () => {
  it("FR-020-28 · the GPU, the driver, the enforced power limit, the throttle fractions, the licence digest and 'our hardware, not a comparative benchmark'", async () => {
    await render();
    const t = document.querySelector('[data-testid="conditions"]')?.textContent ?? "";
    for (const needle of [
      "NVIDIA RTX 5000 Ada Generation Laptop GPU",
      "582.78",
      "110 W",
      REVIEWED,
      "our hardware, not a comparative benchmark",
    ])
      expect(t, needle).toContain(needle);
    expect(t).toMatch(/12\s?%/);
    for (const reason of [
      "software power cap",
      "software thermal",
      "hardware thermal",
      "hardware slowdown",
      "power brake",
    ])
      expect(t.toLowerCase(), reason).toContain(reason);
  });

  it("FR-020-28 · the conditions come from the bundle: another GPU and limit are reflected", async () => {
    await render([
      {
        ...example,
        conditions: {
          ...example.conditions,
          gpu: "Another GPU",
          driver: "999.1",
          power_limit_enforced_w: 140,
        },
      },
    ]);
    const t = document.querySelector('[data-testid="conditions"]')?.textContent ?? "";
    expect(t).toContain("Another GPU");
    expect(t).toContain("999.1");
    expect(t).toContain("140 W");
    expect(t).not.toContain("110 W");
  });
});

describe("the TensorRT licence pin (FR-020-30, FR-000-08)", () => {
  it("FR-020-30 · the reviewed digest is the one of the spec", () => {
    expect(REVIEWED_TENSORRT_LICENCE_SHA256).toBe(REVIEWED);
  });

  it("FR-020-30 · a TensorRT row whose digest differs has its numbers replaced by 'measured locally, not published (licence)'", async () => {
    const changed = `${"0".repeat(63)}1`;
    await render([withRows([trt(changed)])]);
    const r = row("d-fine-n", "tensorrt", "fp16");
    expect(field(r, "licence-withheld")).toContain("measured locally, not published (licence)");
    for (const f of ["latency-p50", "latency-p95", "throughput", "energy", "accuracy-delta"])
      expect(r.querySelector(`[data-field="${f}"]`), f).toBeNull();
    for (const planted of ["2.1", "2.6", "1890", "0.05"])
      expect(r.textContent?.split(/[\s/]+/), planted).not.toContain(planted);
  });

  it("FR-020-30 · a digest that differs in one character, or only in case, is a different digest", async () => {
    for (const sha of [
      `${REVIEWED.slice(0, 63)}3`,
      REVIEWED.toUpperCase(),
      ` ${REVIEWED}`,
      REVIEWED.slice(0, 63),
    ]) {
      const { unmount } = await render([withRows([trt(sha)])]);
      expect(
        row("d-fine-n", "tensorrt", "fp16").querySelector('[data-field="licence-withheld"]'),
        JSON.stringify(sha),
      ).not.toBeNull();
      unmount();
    }
  });

  it("FR-020-30 · ort-tensorrt is a TensorRT backend too; the other backends are not subject to the pin", async () => {
    const changed = "f".repeat(64);
    await render([
      withRows([
        trt(changed, { backend: "ort-tensorrt" }),
        {
          model: "d-fine-n",
          backend: "ort-cuda",
          precision: "fp16",
          status: "accepted",
          latency_ms: { p50: 3, p95: 4 },
          throughput_items_per_s: 900,
          energy_j_per_inference: 0.1,
          accuracy_delta_pp: 0,
          parity: "pass",
        },
      ]),
    ]);
    expect(
      row("d-fine-n", "ort-tensorrt", "fp16").querySelector('[data-field="licence-withheld"]'),
    ).not.toBeNull();
    expect(row("d-fine-n", "ort-cuda", "fp16").querySelector('[data-field="licence-withheld"]')).toBeNull();
    expect(field(row("d-fine-n", "ort-cuda", "fp16"), "latency-p50")).toContain("3");
  });

  it("FR-020-30 · a TensorRT row with no digest at all is withheld, never shown", async () => {
    const r0 = trt(REVIEWED);
    delete (r0 as Record<string, unknown>).tensorrt_licence_sha256;
    await render([withRows([r0])]);
    expect(
      row("d-fine-n", "tensorrt", "fp16").querySelector('[data-field="licence-withheld"]'),
    ).not.toBeNull();
  });

  it("FR-020-30 · a row whose numbers are withheld still says what it is (model, backend, precision), and the rest of the table is unaffected", async () => {
    await render([
      withRows([
        trt("e".repeat(64)),
        {
          model: "d-fine-n",
          backend: "pytorch",
          precision: "fp32",
          status: "accepted",
          latency_ms: { p50: 9.8, p95: 11.2 },
          throughput_items_per_s: 410,
          energy_j_per_inference: 0.21,
          accuracy_delta_pp: 0,
          parity: "pass",
        },
      ]),
    ]);
    expect(row("d-fine-n", "tensorrt", "fp16").textContent).toMatch(/tensorrt/i);
    expect(field(row("d-fine-n", "pytorch", "fp32"), "latency-p50")).toContain("9.8");
  });

  it("FR-000-08 · hostile numbers and strings (NaN, markup in a reason or in the GPU name) never print NaN and create no element", async () => {
    const hostile = withRows([
      {
        model: "<b>x</b>",
        backend: "pytorch",
        precision: "fp32",
        status: "rejected",
        reason: "<img src=x onerror=alert(1)>",
        latency_ms: { p50: Number.NaN, p95: Number.POSITIVE_INFINITY },
        throughput_items_per_s: Number.NaN,
        energy_j_per_inference: -1,
        accuracy_delta_pp: Number.NaN,
        parity: "rejected",
      },
    ]);
    await render([
      { ...hostile, conditions: { ...example.conditions, gpu: "<img src=x onerror=alert(1)>" } },
    ]);
    expect(document.querySelector("img[src='x']")).toBeNull();
    expect(document.querySelector("b")).toBeNull();
    expect(document.body.textContent).not.toMatch(/NaN|Infinity/);
  });
});
