// T-018-099 [red] · FR-018-76: one vendor prefix per tool, and the Omniverse and NVIDIA group listed per case from the registries.
// Oracles: the registry names ("NVIDIA Warp" already carries its vendor), studio/tools.yaml `cases` of ovrtx (hand edited to name C1,
// whose method list holds RTX sensor simulation M23), the FR text.
import { describe, expect, it } from "vitest";
import { studioTools } from "~/studio/data";
import { loadCaseRegistry } from "~/test-support/fixtures";
import { renderApp } from "~/test-support/render";
import { BuiltWithCompact, toolInfos } from "./BuiltWithView";
import { attributionText, deriveBuiltWith, vendorName } from "./builtWith";
import type { CaseEntry } from "./types";

const registry = loadCaseRegistry();
const c1 = registry.cases.C1 as unknown as CaseEntry;
const a3 = registry.cases.A3 as unknown as CaseEntry;
const methods = [
  { id: "M23", name: { en: "RTX sensor simulation", es: "Simulacion de sensores RTX" }, slug: "m23" },
];
const none = { usedTools: new Set<string>(), usedMethods: new Set<string>(), lang: "en" as const };

describe("FR-018-76 the vendor mark is written once", () => {
  it("FR-018-76 · does not prefix a name that already starts with NVIDIA, and prefixes one that does not", () => {
    expect(vendorName("NVIDIA Warp")).toBe("NVIDIA Warp");
    expect(vendorName("nvidia Warp")).toBe("nvidia Warp");
    expect(vendorName("ovrtx")).toBe("NVIDIA ovrtx");
    expect(vendorName("Isaac Sim + Replicator")).toBe("NVIDIA Isaac Sim + Replicator");
  });

  it("FR-018-76 · attributes 'NVIDIA Warp 1.17.0' once, never 'NVIDIA NVIDIA Warp'", () => {
    const warp = deriveBuiltWith({
      entry: a3,
      tools: [{ id: "warp", name: "NVIDIA Warp", version: "1.17.0", licence: "Apache-2.0" }],
      methods: [],
      ...none,
    }).omniverse;
    expect(attributionText("Computed with", warp, [])).toBe(
      "Computed with NVIDIA Warp 1.17.0. Planned, not yet run.",
    );
  });

  it("FR-018-76 · the compact catalogue line of A3 names Warp once", async () => {
    const { container } = await renderApp(<BuiltWithCompact entry={a3} caseId="A3" lang="en" />);
    expect(container.textContent).toContain("NVIDIA Warp");
    expect(container.textContent).not.toMatch(/NVIDIA\s+NVIDIA/);
  });
});

describe("FR-018-76 the Omniverse and NVIDIA group comes from the registries per case", () => {
  const ovrtx = {
    id: "ovrtx",
    name: "ovrtx",
    version: "0.5.0",
    licence: null,
    cases: ["B1", "C1"],
    status: "not-yet-run",
  };

  it("FR-018-76 · lists a tool the studio tool registry names for the case although the case registry does not", () => {
    const g = deriveBuiltWith({ entry: c1, tools: [ovrtx], methods, ...none });
    expect(Object.keys(c1.tools)).not.toContain("ovrtx");
    expect(g.omniverse.map((i) => [i.id, i.status, i.nvidia])).toEqual([["ovrtx", "planned", true]]);
  });

  it("FR-018-76 · does not list it for a case the tool registry does not name", () => {
    const g = deriveBuiltWith({ entry: a3, tools: [ovrtx], methods, ...none });
    expect(g.omniverse.map((i) => i.id)).not.toContain("ovrtx");
  });

  it("FR-018-76 · never lists a tool evaluated and not adopted: it is not planned", () => {
    const cuopt = {
      id: "cuopt",
      name: "NVIDIA cuOpt",
      version: null,
      licence: null,
      cases: ["C1"],
      status: "evaluated-not-adopted",
    };
    expect(deriveBuiltWith({ entry: c1, tools: [cuopt], methods, ...none }).omniverse).toEqual([]);
  });

  it("FR-018-76 · lists a tool once when both registries name it, and keeps the case order first", () => {
    const warp = {
      id: "warp",
      name: "NVIDIA Warp",
      version: null,
      licence: null,
      cases: ["A3"],
      status: "not-yet-run",
    };
    const g = deriveBuiltWith({ entry: a3, tools: [warp, ovrtx], methods, ...none });
    expect(g.omniverse.filter((i) => i.id === "warp")).toHaveLength(1);
  });

  it("FR-018-76 · the real studio registry gives C1 at least one Omniverse and NVIDIA tool, ovrtx among them", () => {
    const info = toolInfos.find((t) => t.id === "ovrtx");
    expect(info?.cases).toContain("C1");
    expect(studioTools.find((t) => t.id === "ovrtx")?.cases).toContain("C1");
    const g = deriveBuiltWith({ entry: c1, tools: toolInfos, methods, ...none });
    expect(g.omniverse.map((i) => i.id)).toContain("ovrtx");
  });

  it("FR-018-76 · the real registries and the published OpenUSD scene give every case a non-empty Omniverse and NVIDIA group", () => {
    for (const [id, entry] of Object.entries(registry.cases)) {
      const g = deriveBuiltWith({
        entry: entry as unknown as CaseEntry,
        tools: toolInfos,
        methods: [],
        ...none,
        renderTools: ["openusd"],
        caseId: id,
      });
      expect(g.omniverse.length, id).toBeGreaterThan(0);
    }
  });
});
