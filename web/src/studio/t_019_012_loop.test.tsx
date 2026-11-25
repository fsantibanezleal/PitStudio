// T-019-012 [red] · FR-019-07: below the map, /studio shows the physical-AI loop (scene, sensors and synthetic data, labels, training, validation, acceleration, encoding, web), each step
// linking to the published runs whose stages realise it (spec section 7.2) or showing "Not yet run". E2E half: web/e2e/t_019_012_loop.spec.ts.
//
// Expected API: `~/studio/Loop` (web/src/studio/Loop.tsx): named export Loop({ runs: RunCard[] }) where `RunCard` is the published run manifest (DC-001-01: run_id, created, published,
// stages[{ key: { id }, status, ... }]). Hooks: `ol[data-testid="loop"]` with eight `li[data-step="<step id>"]` in this order and with these ids: scene, sensors, labels, training,
// validation, acceleration, encoding, web; each holds its title and either links `a[href="/studio/runs/<run id>/"]` (text: the run id), newest run first, or the text "Not yet run".
// Oracle: the table of spec section 7.2 (step -> stage ids), hand-built run cards. Assumptions flagged in the report: a stage realises a step only when its status is `succeeded`
// (a `not_run` or failed stage did not make anything), and unpublished run cards are never linked (FR-019-21).
import { screen, within } from "@testing-library/react";
import { createElement } from "react";
import { describe, expect, it } from "vitest";
import { Loop } from "~/studio/Loop";
import { renderApp } from "~/test-support/render";
import { makeRunCard, makeStage } from "~/test-support/studio-fixtures";

const STEPS = [
  "scene",
  "sensors",
  "labels",
  "training",
  "validation",
  "acceleration",
  "encoding",
  "web",
] as const;
const TITLES = [
  "Scene",
  "Sensors and synthetic data",
  "Labels",
  "Training",
  "Validation",
  "Acceleration",
  "Encoding",
  "Web",
];
/** Spec section 7.2: step -> stage ids that realise it. */
const REALISED_BY: Record<(typeof STEPS)[number], string[]> = {
  scene: ["st40_compose"],
  sensors: ["st53_sensors", "st55_sdg"],
  labels: ["st55_sdg"],
  training: ["s30_train", "st60_il_train"],
  validation: ["s50_evaluate"],
  acceleration: ["s62_accel"],
  encoding: ["st56_encode"],
  web: ["s60_export"],
};

const run = (id: string, stages: string[], over: Record<string, unknown> = {}) =>
  makeRunCard({
    run_id: id,
    created: `2026-10-${id.slice(-2)}T08:00:00Z`,
    stages: stages.map((s) => makeStage(s, "pytorch", { status: "succeeded" })),
    ...over,
  } as never);
const step = (id: string) => document.querySelector<HTMLElement>(`li[data-step="${id}"]`) as HTMLElement;
const links = (id: string) => Array.from(step(id).querySelectorAll("a")).map((a) => a.getAttribute("href"));

describe("the loop (FR-019-07)", () => {
  it("FR-019-07 · eight steps in the order of the loop, each with its title", async () => {
    await renderApp(createElement(Loop, { runs: [] }));
    const items = Array.from(document.querySelectorAll('[data-testid="loop"] > li'));
    expect(items.map((i) => i.getAttribute("data-step"))).toEqual([...STEPS]);
    for (const [i, title] of TITLES.entries()) expect(items[i]?.textContent).toContain(title);
  });

  it("FR-019-07 · with no published run every step shows 'Not yet run' and no link", async () => {
    await renderApp(createElement(Loop, { runs: [] }));
    for (const id of STEPS) {
      expect(step(id).textContent, id).toContain("Not yet run");
      expect(links(id), id).toEqual([]);
    }
  });

  for (const id of STEPS) {
    for (const stage of REALISED_BY[id]) {
      it(`FR-019-07 · a published run with stage ${stage} links from the step '${id}'`, async () => {
        await renderApp(createElement(Loop, { runs: [run("20261011T080000Z-x11", [stage])] }));
        expect(links(id)).toEqual(["/studio/runs/20261011T080000Z-x11/"]);
        expect(step(id).textContent).not.toContain("Not yet run");
        // every other step that this stage does not realise stays 'Not yet run'
        for (const other of STEPS) {
          if (!REALISED_BY[other].includes(stage))
            expect(step(other).textContent, `${other} after ${stage}`).toContain("Not yet run");
        }
      });
    }
  }

  it("FR-019-07 · the stage st55_sdg realises both the sensors and the labels steps", async () => {
    await renderApp(createElement(Loop, { runs: [run("20261012T080000Z-x12", ["st55_sdg"])] }));
    expect(links("sensors")).toEqual(["/studio/runs/20261012T080000Z-x12/"]);
    expect(links("labels")).toEqual(["/studio/runs/20261012T080000Z-x12/"]);
  });

  it("FR-019-07 · several runs are all linked, newest first; a run is linked once per step even when it has two realising stages", async () => {
    const runs = [
      run("20261001T080000Z-x01", ["s30_train"]),
      run("20261003T080000Z-x03", ["s30_train", "st60_il_train"]),
      run("20261002T080000Z-x02", ["st60_il_train"]),
    ];
    await renderApp(createElement(Loop, { runs }));
    expect(links("training")).toEqual([
      "/studio/runs/20261003T080000Z-x03/",
      "/studio/runs/20261002T080000Z-x02/",
      "/studio/runs/20261001T080000Z-x01/",
    ]);
    expect(within(step("training")).getAllByRole("link")).toHaveLength(3);
  });

  it("FR-019-07 · a stage that did not run, or failed, does not realise its step", async () => {
    const stages = [
      makeStage("s50_evaluate", "pytorch", { status: "not_run" }),
      makeStage("s62_accel", "tensorrt", { status: "failed" }),
    ];
    await renderApp(createElement(Loop, { runs: [run("20261011T080000Z-x11", [], { stages })] }));
    expect(step("validation").textContent).toContain("Not yet run");
    expect(step("acceleration").textContent).toContain("Not yet run");
  });

  it("FR-019-07 · an unpublished run card is not linked", async () => {
    await renderApp(
      createElement(Loop, { runs: [run("20261011T080000Z-x11", ["st56_encode"], { published: false })] }),
    );
    expect(step("encoding").textContent).toContain("Not yet run");
  });

  it("FR-019-07 · a run id with unusual characters is a text link with an encoded address, never markup", async () => {
    const id = "20261011T080000Z-<b>x</b>&y z";
    await renderApp(createElement(Loop, { runs: [run(id, ["s60_export"])] }));
    expect(document.querySelector("b")).toBeNull();
    expect(links("web")).toEqual([`/studio/runs/${encodeURIComponent(id)}/`]);
    expect(step("web").textContent).toContain(id);
  });

  it("FR-019-07 · the full loop of one run: every step links to it and none says 'Not yet run'", async () => {
    const all = Object.values(REALISED_BY).flat();
    await renderApp(createElement(Loop, { runs: [run("20261011T080000Z-x11", all)] }));
    for (const id of STEPS) {
      expect(links(id), id).toEqual(["/studio/runs/20261011T080000Z-x11/"]);
      expect(step(id).textContent, id).not.toContain("Not yet run");
    }
  });

  it("FR-019-07 · the section is labelled for assistive technology and the titles follow the language", async () => {
    await renderApp(createElement(Loop, { runs: [] }), { lang: "es" });
    expect(screen.getByTestId("loop").getAttribute("aria-label") ?? "").not.toBe("");
    expect(step("scene").textContent).not.toContain("Scene");
  });
});
