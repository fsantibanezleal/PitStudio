// T-018-095 [red] · FR-018-72: the Built with groups derived from the case registry, the tool registry and the published runs.
// Oracles: the case registry example (hand transcribed in fixtures), the FR text. No code under test produces an expected value.
import { describe, expect, it } from "vitest";
import { loadCaseRegistry } from "../test-support/fixtures";
import { attributionText, deriveBuiltWith, NVIDIA_TOOL_IDS } from "./builtWith";
import type { CaseEntry } from "./types";

const registry = loadCaseRegistry();
const tools = [
  { id: "warp", name: "Warp", version: "1.17.0", licence: "Apache-2.0" },
  { id: "pytorch", name: "PyTorch", version: "2.14.1", licence: "BSD-3-Clause" },
  { id: "onnx-runtime", name: "ONNX Runtime (+Web)", version: "1.30.0", licence: "MIT" },
  { id: "isaac-sim-replicator", name: "Isaac Sim + Replicator", version: null, licence: null },
  { id: "pitstudio", name: "PitStudio", version: "0.1.0", licence: "Apache-2.0" },
];
const methods = [
  { id: "M14", name: { en: "Slope forecasting", es: "Pronostico de taludes" }, slug: "m14" },
  { id: "M13", name: { en: "Slope stability LEM", es: "LEM de estabilidad" }, slug: "m13" },
  { id: "M23", name: { en: "RTX sensor simulation", es: "Simulacion de sensores RTX" }, slug: "m23" },
];
const c1 = registry.cases.C1 as unknown as CaseEntry;
const b2 = registry.cases.B2 as unknown as CaseEntry;

describe("FR-018-72 deriveBuiltWith", () => {
  it("lists every method of the case by its registry name, never a tier label", () => {
    const g = deriveBuiltWith({ entry: c1, tools, methods, usedTools: new Set(), usedMethods: new Set(), lang: "en" });
    expect(g.methods.map((m) => m.name)).toEqual(["Slope stability LEM", "Slope forecasting", "RTX sensor simulation"]);
    for (const m of g.methods) expect(m.name).not.toMatch(/classical|SOTA|beyond/i);
    expect(g.methods.map((m) => m.href)).toEqual(["/methods/m13/", "/methods/m14/", "/methods/m23/"]);
  });

  it("marks NVIDIA and Omniverse tools, links studio tools and keeps the others as frameworks", () => {
    const g = deriveBuiltWith({ entry: b2, tools, methods, usedTools: new Set(), usedMethods: new Set(), lang: "en" });
    const replicator = g.omniverse.find((i) => i.id === "isaac-sim-replicator");
    expect(replicator).toMatchObject({ nvidia: true, href: "/studio/tools/isaac-sim-replicator/", status: "planned" });
    expect(g.frameworks.map((i) => i.id)).toContain("pytorch");
    expect(g.frameworks.every((i) => !i.nvidia)).toBe(true);
    expect(NVIDIA_TOOL_IDS).toEqual(expect.arrayContaining(["warp", "tensorrt", "isaac-lab", "newton", "ovrtx"]));
  });

  it("says used only for a tool or method that produced a published run of the case", () => {
    const g = deriveBuiltWith({
      entry: c1,
      tools,
      methods,
      usedTools: new Set(["pytorch"]),
      usedMethods: new Set(["M14"]),
      lang: "en",
    });
    expect(g.frameworks.find((i) => i.id === "pytorch")).toMatchObject({ status: "used", version: "2.14.1", licence: "BSD-3-Clause" });
    expect(g.frameworks.find((i) => i.id === "onnx-runtime")).toMatchObject({ status: "planned" });
    expect(g.methods.find((i) => i.id === "M14")?.status).toBe("used");
    expect(g.methods.find((i) => i.id === "M13")?.status).toBe("planned");
  });

  it("builds the in-place attribution text with tool, version, method, mark and status", () => {
    const g = deriveBuiltWith({ entry: c1, tools, methods, usedTools: new Set(["pytorch"]), usedMethods: new Set(["M14"]), lang: "en" });
    const text = attributionText("Forecast by", [g.frameworks.find((i) => i.id === "pytorch")!], [g.methods.find((i) => i.id === "M14")!]);
    expect(text).toBe("Forecast by PyTorch 2.14.1, Slope forecasting. Used in the published result.");
    const warp = deriveBuiltWith({ entry: registry.cases.A3 as unknown as CaseEntry, tools, methods, usedTools: new Set(), usedMethods: new Set(), lang: "en" })
      .omniverse.filter((i) => i.id === "warp");
    expect(attributionText("Simulated with", warp, [])).toBe("Simulated with NVIDIA Warp 1.17.0. Planned, not yet run.");
  });
});
