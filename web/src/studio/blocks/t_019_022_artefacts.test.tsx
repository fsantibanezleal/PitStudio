// T-019-022 [red] · FR-019-12 (Artefacts block: every web-manifest artefact whose producer.tool is the page's id, grouped by case, each as an artefact card with its LIVE, REPLAY or STATIC badge),
// FR-019-13 (no artefact and status not evaluated-not-adopted: "Not yet run" and no image, video or metric of the tool), FR-019-14 (evaluated-not-adopted: "Evaluated, not adopted" with the recorded
// reason and a link to the evidence page, no artefact grid), FR-000-06 (badge and provenance on every card) and FR-000-07. E2E half: web/e2e/t_019_022_not_yet_run.spec.ts.
//
// Expected API: `~/studio/blocks/Artefacts` (web/src/studio/blocks/Artefacts.tsx): named export ArtefactsBlock({ tool: ToolEntry; artefacts: ArtefactRecord[]; runs?: RunSummary[] }) rendering
// `section[data-block="artefacts"]` (h2 "Artefacts it produced") with: `[data-case-group="<case id>"]` (h3 = the case id) holding one `~/cards/ArtefactCard` (`article[data-artefact]`) per artefact
// of the tool that lists the case, an artefact that lists several cases appearing in each of them (assumption flagged: the spec says "grouped by case"), and the group `[data-case-group="none"]`
// for an artefact without a case; `[data-testid="not-yet-run"]` ("Not yet run") when there is no artefact and the status is not evaluated-not-adopted; `[data-testid="not-adopted"]` ("Evaluated, not adopted",
// the registry `reason`, an `a[href$="docs/frameworks/not-adopted-<id>.md"]`-style link to `docs_page`) when the status is evaluated-not-adopted.
// Oracles: hand-built manifests; the artefact-card contract of FR-018-18 (lane badge `[data-lane]`, producer, run id, 7-hex commit); the EARS strings.
import { within } from "@testing-library/react";
import { createElement } from "react";
import { describe, expect, it } from "vitest";
import { ArtefactsBlock } from "~/studio/blocks/Artefacts";
import { GIT_SHA, makeArtefact } from "~/test-support/fixtures";
import { renderApp } from "~/test-support/render";
import { makeTool, toolArtefact } from "~/test-support/studio-fixtures";

const block = () => document.querySelector<HTMLElement>('section[data-block="artefacts"]') as HTMLElement;
const cards = () =>
  Array.from(block().querySelectorAll("article[data-artefact]")).map((a) => a.getAttribute("data-artefact"));
const group = (id: string) => block().querySelector<HTMLElement>(`[data-case-group="${id}"]`);
const inGroup = (id: string) =>
  Array.from(group(id)?.querySelectorAll("article[data-artefact]") ?? []).map((a) =>
    a.getAttribute("data-artefact"),
  );
const warp = makeTool("warp", { status: "done" });
const render = (tool = warp, artefacts: unknown[] = []) =>
  renderApp(createElement(ArtefactsBlock, { tool: tool as never, artefacts: artefacts as never }));

describe("the artefacts of the tool (FR-019-12)", () => {
  const manifest = [
    toolArtefact("w-a1-live", "warp", { cases: ["A1"], lane: "live" }),
    toolArtefact("w-a1-replay", "warp", { cases: ["A1"], lane: "replay" }),
    toolArtefact("w-c2-static", "warp", {
      cases: ["C2"],
      lane: "static",
      kind: "image",
      budget_class: "own-code",
    }),
    toolArtefact("w-shared", "warp", { cases: ["A1", "C2"], lane: "replay" }),
    toolArtefact("w-nocase", "warp", { cases: [], lane: "replay" }),
    toolArtefact("n-a1", "newton", { cases: ["A1"] }),
    toolArtefact("p-c2", "pytorch", { cases: ["C2"] }),
  ];

  it("FR-019-12 · lists exactly the artefacts whose producer.tool is the page's id, as cards", async () => {
    await render(warp, manifest);
    expect([...cards()].sort()).toEqual(
      ["w-a1-live", "w-a1-replay", "w-c2-static", "w-nocase", "w-shared", "w-shared"].sort(),
    );
    expect(block().querySelector("h2")?.textContent).toBe("Artefacts it produced");
  });

  it("FR-019-12 · groups them by case: each case has its own group, an artefact of two cases is in both, one without a case is in 'none'", async () => {
    await render(warp, manifest);
    expect(inGroup("A1").sort()).toEqual(["w-a1-live", "w-a1-replay", "w-shared"]);
    expect(inGroup("C2").sort()).toEqual(["w-c2-static", "w-shared"]);
    expect(inGroup("none")).toEqual(["w-nocase"]);
    expect(group("A1")?.querySelector("h3")?.textContent).toContain("A1");
    expect(group("B1")).toBeNull();
  });

  it("FR-019-12 · the case groups follow the canonical case order, not the order of the manifest", async () => {
    await render(warp, [
      toolArtefact("z", "warp", { cases: ["E2"] }),
      toolArtefact("y", "warp", { cases: ["A3"] }),
      toolArtefact("x", "warp", { cases: ["C1"] }),
    ]);
    const order = Array.from(block().querySelectorAll("[data-case-group]")).map((g) =>
      g.getAttribute("data-case-group"),
    );
    expect(order).toEqual(["A3", "C1", "E2"]);
  });

  it("FR-019-12 · each card has its LIVE, REPLAY or STATIC badge (FR-018-18)", async () => {
    await render(warp, manifest);
    const badge = (id: string) =>
      group("A1")?.querySelector(`article[data-artefact="${id}"] [data-lane]`)?.textContent;
    expect(badge("w-a1-live")).toBe("LIVE");
    expect(badge("w-a1-replay")).toBe("REPLAY");
    expect(group("C2")?.querySelector('article[data-artefact="w-c2-static"] [data-lane]')?.textContent).toBe(
      "STATIC",
    );
  });

  it("FR-000-06 · each card carries its provenance: producing tool, run id and the 7-hex commit", async () => {
    await render(warp, [toolArtefact("w-a1", "warp", { cases: ["A1"], run_id: "20261011T083000Z-a1" })]);
    const card = within(block()).getByText("w-a1").closest("article") as HTMLElement;
    expect(card.textContent).toContain("warp");
    expect(card.textContent).toContain("20261011T083000Z-a1");
    expect(card.textContent).toContain(GIT_SHA.slice(0, 7));
  });

  it("FR-019-12 · a manifest with thousands of artefacts of other tools lists none of them", async () => {
    const many = Array.from({ length: 3000 }, (_, i) =>
      toolArtefact(`o-${i}`, i % 2 ? "newton" : "pytorch", { cases: ["A1"] }),
    );
    await render(warp, [...many, toolArtefact("w-1", "warp", { cases: ["A1"] })]);
    expect(cards()).toEqual(["w-1"]);
  });
});

describe("a tool that has not run (FR-019-13, FR-000-07)", () => {
  const idle = makeTool("openusd", { status: "not-yet-run" });

  it("FR-019-13 · without an artefact the block says 'Not yet run' and shows no card, image, video or chart", async () => {
    await render(idle, []);
    expect(block().querySelector('[data-testid="not-yet-run"]')?.textContent).toContain("Not yet run");
    expect(cards()).toEqual([]);
    expect(block().querySelectorAll("img, video, canvas, svg, table, [data-kpi]")).toHaveLength(0);
  });

  it("FR-019-13 · artefacts of other tools do not count: the tool still says 'Not yet run'", async () => {
    await render(idle, [toolArtefact("w-1", "warp", { cases: ["A1"] })]);
    expect(block().textContent).toContain("Not yet run");
    expect(cards()).toEqual([]);
  });

  it("FR-019-13 · a tool with an artefact does not say 'Not yet run'", async () => {
    await render(idle, [toolArtefact("o-1", "openusd", { cases: ["B1"] })]);
    expect(block().textContent).not.toContain("Not yet run");
    expect(cards()).toEqual(["o-1"]);
  });

  it("FR-000-07 · a tool marked done with no artefact is still shown as 'Not yet run' (it is not marked done)", async () => {
    await render(makeTool("warp", { status: "done" }), []);
    expect(block().textContent).toContain("Not yet run");
  });
});

describe("an evaluated-not-adopted tool (FR-019-14)", () => {
  const cuopt = makeTool("cuopt", {
    reason: "Dispatch decisions are per-truck and event-driven; a batch routing solver adds no value.",
    docs_page: "docs/frameworks/not-adopted-cuopt.md",
  });

  it("FR-019-14 · shows 'Evaluated, not adopted' with the recorded reason and a link to the evidence page", async () => {
    await render(cuopt, []);
    const box = block().querySelector<HTMLElement>('[data-testid="not-adopted"]');
    expect(box?.textContent).toContain("Evaluated, not adopted");
    expect(box?.textContent).toContain(
      "Dispatch decisions are per-truck and event-driven; a batch routing solver adds no value.",
    );
    const link = box?.querySelector("a");
    expect(link?.getAttribute("href")).toContain("docs/frameworks/not-adopted-cuopt");
  });

  it("FR-019-14 · it does not say 'Not yet run' and shows no artefact grid, even if the manifest names the tool", async () => {
    await render(cuopt, [
      makeArtefact({ id: "stray", producer: { tool: "cuopt", stage: { id: "st50_physics" } } }),
    ]);
    expect(block().textContent).not.toContain("Not yet run");
    expect(cards()).toEqual([]);
    expect(block().querySelectorAll("img, video, canvas")).toHaveLength(0);
  });

  it("FR-019-14 · a reason with markup is text", async () => {
    await render(makeTool("cuopt", { reason: `<img src=x onerror=alert(1)>${"r".repeat(500)}` }), []);
    expect(document.querySelector("img[src='x']")).toBeNull();
  });
});
