// The 011 scenes in their declared availability states (FR-011-09, FR-011-11, FR-011-31, FR-011-38, FR-011-39): controls and labels
// are real, nothing is computed or drawn while the model is not published.
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fetchAvailability, isDescriptorOf, readEvaluation } from "~/engines/surrogates/availability";
import { renderApp } from "~/test-support/render";
import { CalibrationReplay } from "./CalibrationReplay";
import { FnoScene } from "./FnoScene";
import { GnsScene } from "./GnsScene";

const EXTRAPOLATION = "extrapolation — no accuracy claim";

function stubDocs(docs: { descriptor?: boolean; evaluation?: unknown }) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url.endsWith(".surrogate-io.json") && docs.descriptor)
        return new Response(JSON.stringify({ model_id: "gns-a3" }), { status: 200 });
      if (url.endsWith(".evaluation.json") && docs.evaluation !== undefined)
        return new Response(JSON.stringify(docs.evaluation), { status: 200 });
      return new Response("not found", { status: 404 });
    }),
  );
}

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response("not found", { status: 404 })),
  );
});
afterEach(() => vi.unstubAllGlobals());

async function setNumber(region: HTMLElement, name: string, value: string) {
  const input = within(region).getByRole("spinbutton", { name });
  fireEvent.change(input, { target: { value } });
  fireEvent.blur(input);
}

describe("A3 GNS scene", () => {
  it("has the region, the family combobox, the particle count capped at 5,000 with a default of 2,000, and no rollout", async () => {
    await renderApp(<GnsScene tier="t2" />);
    const region = screen.getByRole("region", { name: "GNS granular flow" });
    expect(within(region).getByRole("combobox", { name: "Geometry family" })).toBeTruthy();
    const count = within(region).getByRole("spinbutton", { name: "Particle count" });
    expect(Number((count as HTMLInputElement).value)).toBe(2000);
    expect(Number(count.getAttribute("max"))).toBe(5000);
    expect(within(region).getByRole("button", { name: "Start" })).toBeTruthy();
    expect(screen.queryByRole("img", { name: "Live GNS rollout" })).toBeNull();
    expect(screen.queryByText("LIVE")).toBeNull();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("declares 'not yet trained' when no model is published, and never shows a step time", async () => {
    await renderApp(<GnsScene tier="t2" />);
    const region = screen.getByRole("region", { name: "GNS granular flow" });
    fireEvent.click(within(region).getByRole("button", { name: "Start" }));
    await waitFor(() => expect(screen.getByRole("status").textContent).toContain("not yet trained"));
    expect(screen.queryByRole("status", { name: "Step time" })).toBeNull();
  });

  it("FR-011-11: aspect ratio 0.5 and 4 are inside the envelope, 6 shows the label", async () => {
    await renderApp(<GnsScene tier="t2" />);
    const region = screen.getByRole("region", { name: "GNS granular flow" });
    for (const v of ["0.5", "4", "2"]) {
      await setNumber(region, "Aspect ratio", v);
      expect(screen.queryByText(EXTRAPOLATION)).toBeNull();
    }
    await setNumber(region, "Aspect ratio", "6");
    expect(screen.getByText(EXTRAPOLATION)).toBeTruthy();
    await setNumber(region, "Aspect ratio", "abc"); // not a number: the last value stays
    expect((within(region).getByRole("spinbutton", { name: "Aspect ratio" }) as HTMLInputElement).value).toBe(
      "6",
    );
  });

  it("the family selector swaps the parameter controls", async () => {
    await renderApp(<GnsScene tier="t1" />);
    const region = screen.getByRole("region", { name: "GNS granular flow" });
    fireEvent.change(within(region).getByRole("combobox", { name: "Geometry family" }), {
      target: { value: "pile-formation" },
    });
    expect(within(region).queryByRole("spinbutton", { name: "Aspect ratio" })).toBeNull();
    expect(within(region).getByRole("spinbutton", { name: "Pour height (m)" })).toBeTruthy();
  });

  it("a model published without an evaluation report is not offered", async () => {
    stubDocs({ descriptor: true });
    await renderApp(<GnsScene tier="t2" />);
    await waitFor(() =>
      expect(screen.getByRole("status").textContent).toContain("without an evaluation report"),
    );
    expect(screen.queryByRole("img", { name: "Live GNS rollout" })).toBeNull();
  });

  it("a model whose evaluation failed says so with the counts and offers no rollout", async () => {
    stubDocs({
      descriptor: true,
      evaluation: { sc_011_01: "fail", geometries: [{ pass: true }, { pass: false }, { pass: false }] },
    });
    await renderApp(<GnsScene tier="t2" />);
    await waitFor(() =>
      expect(screen.getByRole("status").textContent).toContain("Evaluation failed: 1 of 3"),
    );
    expect(screen.queryByRole("img", { name: "Live GNS rollout" })).toBeNull();
    expect(screen.queryByText("LIVE")).toBeNull();
  });

  it("a passing evaluation still shows nothing computed while ONNX Runtime is not wired in", async () => {
    stubDocs({ descriptor: true, evaluation: { sc_011_01: "pass", geometries: [{ pass: true }] } });
    await renderApp(<GnsScene tier="t2" />);
    await waitFor(() => expect(screen.getByRole("status").textContent).toContain("ONNX Runtime"));
    expect(screen.queryByRole("img", { name: "Live GNS rollout" })).toBeNull();
  });
});

describe("C2 and C3 FNO scenes", () => {
  it("C2 carries the five controls with the training ranges as min and max (FR-011-38)", async () => {
    await renderApp(<FnoScene variant="C2" tier="t2" />);
    const region = screen.getByRole("region", { name: "FNO tailings flow" });
    const ranges: Array<[string, string, string]> = [
      ["Breach row", "0", "63"],
      ["Breach column", "0", "63"],
      ["Release volume (m³)", "10000", "200000"],
      ["Yield stress τ_y (Pa)", "10", "200"],
      ["Plastic viscosity μ_B (Pa·s)", "0.05", "1"],
    ];
    for (const [name, min, max] of ranges) {
      const input = within(region).getByRole("spinbutton", { name });
      expect(input.getAttribute("min")).toBe(min);
      expect(input.getAttribute("max")).toBe(max);
    }
    expect(screen.queryByRole("img", { name: "FNO depth field" })).toBeNull();
    expect(screen.queryByText("LIVE")).toBeNull();
  });

  it("FR-011-39: 500 Pa is labelled, 10 and 200 Pa and a return to 100 Pa are not", async () => {
    await renderApp(<FnoScene variant="C2" tier="t2" />);
    const region = screen.getByRole("region", { name: "FNO tailings flow" });
    const name = "Yield stress τ_y (Pa)";
    for (const v of ["10", "200"]) {
      await setNumber(region, name, v);
      expect(screen.queryByText(EXTRAPOLATION)).toBeNull();
    }
    await setNumber(region, name, "500");
    expect(screen.getByText(EXTRAPOLATION)).toBeTruthy();
    expect(screen.queryByRole("status", { name: "Relative L2 of the nearest scenario" })).toBeNull();
    await setNumber(region, name, "100");
    expect(screen.queryByText(EXTRAPOLATION)).toBeNull();
  });

  it("C3 has wind speed and direction (0 ... 359) and labels 80 m/s", async () => {
    await renderApp(<FnoScene variant="C3" tier="t2" />);
    const region = screen.getByRole("region", { name: "FNO dust plume" });
    const direction = within(region).getByRole("spinbutton", { name: "Wind direction (°)" });
    expect(direction.getAttribute("min")).toBe("0");
    expect(direction.getAttribute("max")).toBe("359");
    await setNumber(region, "Wind speed (m/s)", "80");
    expect(screen.getByText(EXTRAPOLATION)).toBeTruthy();
  });
});

describe("A3 calibration replay", () => {
  it("is a REPLAY region with the declared not-run state, no LIVE badge and no chart", async () => {
    await renderApp(<CalibrationReplay />);
    const region = screen.getByRole("region", { name: "Calibration replay" });
    expect(within(region).getByText("REPLAY")).toBeTruthy();
    expect(within(region).queryByText("LIVE")).toBeNull();
    expect(region.textContent).toContain("has not been run on the GPU");
    expect(within(region).queryByRole("img")).toBeNull();
    expect(within(region).queryByRole("table")).toBeNull();
  });
});

describe("model availability", () => {
  it("a descriptor belongs to its model only", () => {
    expect(isDescriptorOf({ model_id: "gns-a3" }, "gns-a3")).toBe(true);
    for (const doc of [{ model_id: "other" }, {}, null, [], "gns-a3", 5])
      expect(isDescriptorOf(doc, "gns-a3")).toBe(false);
  });

  it("the evaluation verdict needs sc_011_01 pass and every geometry passing", () => {
    expect(readEvaluation({ sc_011_01: "pass", geometries: [{ pass: true }, { pass: true }] })).toEqual({
      pass: true,
      passed: 2,
      total: 2,
    });
    expect(readEvaluation({ sc_011_01: "pass", geometries: [{ pass: true }, { pass: false }] })?.pass).toBe(
      false,
    );
    expect(readEvaluation({ sc_011_01: "fail", geometries: [{ pass: true }] })?.pass).toBe(false);
    for (const doc of [null, [], {}, { sc_011_01: "pass" }, { geometries: [] }])
      expect(readEvaluation(doc)).toBeNull();
  });

  it("a 404, an HTML page and a network error publish nothing; the states follow the documents", async () => {
    const make = (impl: (url: string) => Promise<Response>) => vi.fn(impl) as unknown as typeof fetch;
    const res = (body: string, status = 200) => Promise.resolve(new Response(body, { status }));
    expect(
      (
        await fetchAvailability(
          "/",
          "gns-a3",
          undefined,
          make(() => res("", 404)),
        )
      ).state,
    ).toBe("not-published");
    expect(
      (
        await fetchAvailability(
          "/",
          "gns-a3",
          undefined,
          make(() => res("<html>")),
        )
      ).state,
    ).toBe("not-published");
    expect(
      (
        await fetchAvailability(
          "/",
          "gns-a3",
          undefined,
          make(() => Promise.reject(new Error("offline"))),
        )
      ).state,
    ).toBe("not-published");
    const doc = (url: string) =>
      url.endsWith("surrogate-io.json") ? res('{"model_id":"gns-a3"}') : res("", 404);
    expect((await fetchAvailability("/", "gns-a3", undefined, make(doc))).state).toBe("unevaluated");
    const ok = (url: string) =>
      url.endsWith("surrogate-io.json")
        ? res('{"model_id":"gns-a3"}')
        : res('{"sc_011_01":"pass","geometries":[{"pass":true}]}');
    expect((await fetchAvailability("/", "gns-a3", undefined, make(ok))).state).toBe("ready");
  });
});
