// T-018-031 [red] · FR-018-14 (Simulate tab: one engine panel per engine of the registry, LIVE badge for a result computed in this browser, REPLAY for a T0 fallback) and
// FR-018-15 (Studio replay tab: artefact cards of the replay artefacts of the case, "Not yet run" otherwise). E2E half: web/e2e/t_018_031_case_tabs.spec.ts.
//
// Expected API (new components, to be created):
//   `~/cases/ReplayTab` (web/src/cases/ReplayTab.tsx): named export ReplayTab({ caseId: string; artefacts: ArtefactJson[]; runs?: RunSummaryJson[] })
//       renders one `~/cards/ArtefactCard` (`article[data-artefact="<id>"]`) for every artefact whose `cases` array lists `caseId` and whose lane is `replay`
//       (artefacts of another case, of lane live or static, or without a `cases` array are NOT listed), in the order given; with none it shows "Not yet run" and no card.
//       (The field is `cases`, an array, as in data-model 001 section 2.5; FR-018-15 writes `case`: a documented ambiguity.)
//   `~/cases/EnginePanel` (web/src/cases/EnginePanel.tsx): named export EnginePanel(props: { engine: string; mode: "live" | "replay"; state: "idle" | "loading" |
//       "running" | "done" | "error" | "replay"; requests: number; tier: "t1" | "t2" | "t0"; notice?: string | null;
//       controls?: Array<{ name: string; value: number; min: number; max: number; unit: string }> })
//       renders `[data-testid="engine-panel"][data-engine][data-state][data-requests][data-tier]` with `[data-testid="lane-badge"]` ("LIVE" iff mode is live, else "REPLAY"),
//       `[data-testid="engine-notice"]` when a notice is given, and one `input[data-control="<name>"][data-min][data-max][data-unit]` per control showing its value and unit.
//   `~/cases/SimulateTab` (web/src/cases/SimulateTab.tsx): named export SimulateTab({ caseId: string; registry: CaseRegistryJson })
//       renders one engine panel per engine listed for the case in the registry, in registry order (no other engine, none missing).
// Oracles: the EARS text; the case registry example (engines per case, specs/018-web-cases/contracts/examples/cases.valid.json); hand-built artefact records
// (web/src/test-support/fixtures.ts, data-model 001 section 2.5).
import { screen, within } from "@testing-library/react";
import { createElement } from "react";
import { describe, expect, it } from "vitest";
import { EnginePanel } from "~/cases/EnginePanel";
import { ReplayTab } from "~/cases/ReplayTab";
import { SimulateTab } from "~/cases/SimulateTab";
import { CASE_IDS, loadCaseRegistry, makeArtefact } from "~/test-support/fixtures";
import { renderApp } from "~/test-support/render";

describe("Studio replay tab (FR-018-15)", () => {
  const artefacts = [
    makeArtefact({ id: "a1-replay-1", cases: ["A1"], lane: "replay" }),
    makeArtefact({ id: "a1-replay-2", cases: ["A1"], lane: "replay" }),
    makeArtefact({ id: "a1-live", cases: ["A1"], lane: "live" }),
    makeArtefact({ id: "a1-static", cases: ["A1"], lane: "static", kind: "image", budget_class: "own-code" }),
    makeArtefact({ id: "b1-replay", cases: ["B1"], lane: "replay" }),
    makeArtefact({ id: "shared-replay", cases: ["A1", "B1"], lane: "replay" }),
    makeArtefact({ id: "no-case-replay", cases: [], lane: "replay" }),
  ];
  const listed = () =>
    Array.from(document.querySelectorAll("article[data-artefact]")).map((a) =>
      a.getAttribute("data-artefact"),
    );

  it("FR-018-15 · lists every replay artefact that names the case, as artefact cards, and nothing else", async () => {
    await renderApp(createElement(ReplayTab, { caseId: "A1", artefacts: artefacts as never }));
    expect(listed()).toEqual(["a1-replay-1", "a1-replay-2", "shared-replay"]);
  });

  it("FR-018-15 · an artefact that names two cases appears on both pages", async () => {
    await renderApp(createElement(ReplayTab, { caseId: "B1", artefacts: artefacts as never }));
    expect(listed()).toEqual(["b1-replay", "shared-replay"]);
  });

  it("FR-018-15 · every card carries the REPLAY badge of FR-018-18", async () => {
    await renderApp(createElement(ReplayTab, { caseId: "A1", artefacts: artefacts as never }));
    for (const card of document.querySelectorAll("article[data-artefact]")) {
      expect(card.querySelector("[data-lane]")?.getAttribute("data-lane")).toBe("replay");
      expect(within(card as HTMLElement).getByText("REPLAY")).toBeTruthy();
    }
  });

  it("FR-018-15 · with no replay artefact for the case it shows 'Not yet run' and no card", async () => {
    await renderApp(createElement(ReplayTab, { caseId: "C3", artefacts: artefacts as never }));
    expect(screen.getByText(/Not yet run/)).toBeTruthy();
    expect(listed()).toEqual([]);
  });

  it("FR-018-15 · an empty manifest gives 'Not yet run' for every case id", async () => {
    for (const id of CASE_IDS) {
      const { unmount } = await renderApp(createElement(ReplayTab, { caseId: id, artefacts: [] }));
      expect(screen.getByText(/Not yet run/), id).toBeTruthy();
      unmount();
    }
  });

  it("FR-018-15 · only live and static artefacts of the case: still 'Not yet run'", async () => {
    const onlyOthers = [
      makeArtefact({ id: "x-live", cases: ["E1"], lane: "live" }),
      makeArtefact({
        id: "x-static",
        cases: ["E1"],
        lane: "static",
        kind: "image",
        budget_class: "own-code",
      }),
    ];
    await renderApp(createElement(ReplayTab, { caseId: "E1", artefacts: onlyOthers as never }));
    expect(screen.getByText(/Not yet run/)).toBeTruthy();
    expect(listed()).toEqual([]);
  });

  it("FR-018-15 · a very long artefact id is rendered as text and the list stays intact", async () => {
    const hostile = [
      makeArtefact({ id: "x".repeat(90), cases: ["A2"], lane: "replay" }),
      makeArtefact({ id: "a2-ok", cases: ["A2"], lane: "replay" }),
    ];
    await renderApp(createElement(ReplayTab, { caseId: "A2", artefacts: hostile as never }));
    expect(listed()).toHaveLength(2);
    expect(document.querySelector("script")).toBeNull();
  });
});

describe("engine panel (FR-018-14)", () => {
  const props = {
    engine: "geotech",
    mode: "live" as const,
    state: "done" as const,
    requests: 3,
    tier: "t2" as const,
  };

  it("FR-018-14 · a result computed in this browser carries the LIVE badge and the panel exposes engine, state, request count and tier", async () => {
    await renderApp(createElement(EnginePanel, props));
    const panel = screen.getByTestId("engine-panel");
    expect(panel.getAttribute("data-engine")).toBe("geotech");
    expect(panel.getAttribute("data-state")).toBe("done");
    expect(panel.getAttribute("data-requests")).toBe("3");
    expect(panel.getAttribute("data-tier")).toBe("t2");
    expect(within(panel).getByTestId("lane-badge").textContent).toBe("LIVE");
  });

  it("FR-018-14 · a result taken from the T0 fallback carries the REPLAY badge, never LIVE", async () => {
    await renderApp(
      createElement(EnginePanel, { ...props, mode: "replay", state: "replay", tier: "t0", requests: 0 }),
    );
    expect(screen.getByTestId("lane-badge").textContent).toBe("REPLAY");
    expect(screen.getByTestId("engine-panel").getAttribute("data-state")).toBe("replay");
    expect(screen.queryByText("LIVE")).toBeNull();
  });

  it("FR-018-14 · a notice is shown in the panel when there is one, and only then", async () => {
    const { unmount } = await renderApp(
      createElement(EnginePanel, {
        ...props,
        mode: "replay",
        state: "replay",
        notice: "needs WebGPU to compute live",
      }),
    );
    expect(screen.getByTestId("engine-notice").textContent).toContain("needs WebGPU to compute live");
    unmount();
    await renderApp(createElement(EnginePanel, props));
    expect(screen.queryByTestId("engine-notice")).toBeNull();
  });

  it("FR-018-14 · numeric controls expose their range and unit for the hostile-input handling: min, max, unit and the current value", async () => {
    await renderApp(
      createElement(EnginePanel, {
        ...props,
        controls: [{ name: "cohesion", value: 15, min: 0, max: 100, unit: "kPa" }],
      }),
    );
    const input = document.querySelector('input[data-control="cohesion"]') as HTMLInputElement;
    expect(input).not.toBeNull();
    expect(input.getAttribute("data-min")).toBe("0");
    expect(input.getAttribute("data-max")).toBe("100");
    expect(input.getAttribute("data-unit")).toBe("kPa");
    expect(Number(input.value)).toBe(15);
    expect(screen.getByText(/kPa/)).toBeTruthy();
  });
});

describe("Simulate tab (FR-018-14)", () => {
  const registry = loadCaseRegistry();

  for (const id of CASE_IDS) {
    it(`FR-018-14 · ${id}: one engine panel per engine of the registry, in registry order`, async () => {
      await renderApp(createElement(SimulateTab, { caseId: id, registry }));
      const shown = Array.from(document.querySelectorAll('[data-testid="engine-panel"]')).map((p) =>
        p.getAttribute("data-engine"),
      );
      expect(shown).toEqual((registry.cases[id] as { engines: string[] }).engines);
    });
  }
});
