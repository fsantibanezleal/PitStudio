// T-019-032 [red] · FR-019-24 (stage DAG: one node per stage with the cache result as text and icon, exit status, retries and wall time, the wall time omitted for `performance: local-only` stages, edges from each stage's
// inputs) and FR-019-25 (determinism block: the class and the re-run check; bitwise: both SHA-256 digests and "equal" or "different"; statistical: each observable with its tolerance and both values; a missing check: "pending").
//
// Expected API:
//   `~/studio/StageDag` (web/src/studio/StageDag.tsx): named export StageDag({ run: RunCard }) rendering `[data-testid="stage-dag"]` with one `[data-testid="stage-node"][data-stage="<id>"][data-variant?][data-cache="hit|miss"][data-status]`
//     per stage of the run card, in card order, each with an `svg` icon (a different icon for hit and for miss), the text "cache hit" or "cache miss", the status text (succeeded, failed, not run, ...) with "exit <code>" when
//     there is an exit code, `[data-field="retries"]` (attempts minus one) and, for a public stage with a wall time, `[data-field="wall"]` ("<seconds> s"); a local-only stage has no wall field and none of its numbers in the DAG.
//     Edges `[data-testid="dag-edge"][data-from][data-to]` (one per pair): from the stage that produced an artefact of the run card to each stage that lists that artefact among its inputs (`kind: artefact`).
//   `~/studio/DeterminismBlock` (web/src/studio/DeterminismBlock.tsx): named export DeterminismBlock({ run: RunCard }) rendering `[data-testid="determinism"]` with one `[data-testid="determinism-stage"][data-stage]` per stage:
//     the class (`bitwise`, `statistical`, `none`) and the re-run check; the data of the check is `stage.determinism.rerun` (an extension of DC-001-01 that the schema does not hold yet: flagged in the report):
//     bitwise: `{ digests: [first, second] }` shown in full, with "equal" or "different" computed from the two strings (never copied from `rerun_check`); statistical: `{ observables: [{ name, rtol, atol, first, second }] }`
//     shown one per row `[data-testid="observable"]` with name, tolerance and both values; no `rerun` (or `rerun_check: "pending"`): "pending"; `not-applicable`: "not applicable".
// Oracles: hand-built run cards (valid example of DC-001-01 as base): the DAG of the c2 fixture (compose -> physics, compose -> sdg), the EARS strings, digest equality by hand.
import { within } from "@testing-library/react";
import { createElement } from "react";
import { describe, expect, it } from "vitest";
import { DeterminismBlock } from "~/studio/DeterminismBlock";
import { StageDag } from "~/studio/StageDag";
import { renderApp } from "~/test-support/render";
import { makeRunCard, makeStage } from "~/test-support/studio-fixtures";

const SC = { id: "c2-scene", sha256: "3".repeat(64), kind: "artefact" };
const scene = { id: "c2-scene", producer: { tool: "openusd", stage: { id: "st40_compose" } }, kind: "table" };
const compose = makeStage("st40_compose", "openusd", {
  cache: "hit",
  wall_s: 3.25,
  attempts: [{ n: 1, error_class: null, duration_s: 3.25 }],
  inputs: [],
});
const physics = makeStage("st50_physics", "warp", {
  cache: "miss",
  wall_s: 120.5,
  attempts: [
    { n: 1, error_class: "oom", duration_s: 9 },
    { n: 2, error_class: null, duration_s: 111.5 },
  ],
  inputs: [SC],
});
const sdg = makeStage("st55_sdg", "isaac-sim-replicator", {
  cache: "miss",
  performance: "local-only",
  wall_s: 913.75,
  telemetry: "measured locally, not published (licence)",
  inputs: [SC],
});
const rejected = makeStage("s62_accel", "tensorrt", {
  key: { id: "s62_accel", variant: "fp8" },
  cache: "miss",
  status: "failed",
  error_class: "invalid-result",
  exit_code: 3,
  wall_s: 41.5,
  attempts: [{ n: 1, error_class: "invalid-result" }],
  inputs: [],
});
const notRun = makeStage("st45b_kit_validate", "kit-usd-composer-explorer", {
  cache: "miss",
  status: "not_run",
  reason: "Kit not installed",
  error_class: null,
  exit_code: 0,
  attempts: [{ n: 1, error_class: null }],
  inputs: [],
});
const run = (stages: unknown[], artefacts: unknown[] = [scene]) =>
  makeRunCard({ stages, artefacts } as never);

const node = (id: string, variant?: string) =>
  document.querySelector<HTMLElement>(
    `[data-testid="stage-node"][data-stage="${id}"]${variant ? `[data-variant="${variant}"]` : ""}`,
  ) as HTMLElement;
const icon = (n: HTMLElement) =>
  (n.querySelector("svg")?.getAttribute("class") ?? "")
    .split(/\s+/)
    .find((c) => c.startsWith("lucide-") && c !== "lucide") ?? "";
const dag = (stages: unknown[], artefacts?: unknown[]) =>
  renderApp(createElement(StageDag, { run: run(stages, artefacts) as never }));

describe("stage DAG (FR-019-24)", () => {
  it("FR-019-24 · one node per stage, in the order of the run card, with the variant of a variant stage", async () => {
    await dag([compose, physics, sdg, rejected, notRun]);
    const nodes = Array.from(document.querySelectorAll('[data-testid="stage-node"]')).map((n) =>
      n.getAttribute("data-stage"),
    );
    expect(nodes).toEqual(["st40_compose", "st50_physics", "st55_sdg", "s62_accel", "st45b_kit_validate"]);
    expect(node("s62_accel").getAttribute("data-variant")).toBe("fp8");
    expect(node("st40_compose").hasAttribute("data-variant")).toBe(false);
  });

  it("FR-019-24 · the cache result is written as text ('cache hit' / 'cache miss') and shown by an icon, with a different icon for each", async () => {
    await dag([compose, physics, sdg]);
    expect(node("st40_compose").textContent?.toLowerCase()).toContain("cache hit");
    expect(node("st40_compose").getAttribute("data-cache")).toBe("hit");
    expect(node("st50_physics").textContent?.toLowerCase()).toContain("cache miss");
    expect(node("st55_sdg").textContent?.toLowerCase()).toContain("cache miss");
    const hit = icon(node("st40_compose"));
    const miss = icon(node("st50_physics"));
    expect(hit.length).toBeGreaterThan(0);
    expect(miss.length).toBeGreaterThan(0);
    expect(hit).not.toBe(miss);
    expect(icon(node("st55_sdg"))).toBe(miss);
  });

  it("FR-019-24 · exit status: succeeded, failed with its exit code, not run", async () => {
    await dag([compose, rejected, notRun]);
    expect(node("st40_compose").textContent).toMatch(/succeeded/i);
    expect(node("s62_accel").textContent).toMatch(/failed/i);
    expect(node("s62_accel").textContent).toMatch(/exit\s*3\b/i);
    expect(node("st45b_kit_validate").textContent).toMatch(/not run/i);
  });

  it("FR-019-24 · retries are the attempts after the first: 0 for one attempt, 1 for two", async () => {
    await dag([compose, physics]);
    expect(node("st40_compose").querySelector('[data-field="retries"]')?.textContent).toMatch(/\b0\b/);
    expect(node("st50_physics").querySelector('[data-field="retries"]')?.textContent).toMatch(/\b1\b/);
  });

  it("FR-019-24 · the wall time of a public stage is shown in seconds", async () => {
    await dag([compose, physics, rejected]);
    expect(node("st50_physics").querySelector('[data-field="wall"]')?.textContent).toContain("120.5");
    expect(node("st40_compose").querySelector('[data-field="wall"]')?.textContent).toContain("3.25");
    expect(node("s62_accel").querySelector('[data-field="wall"]')?.textContent).toContain("41.5");
  });

  it("FR-019-24 · the wall time is omitted for a local-only stage, and none of its numbers appears in the DAG", async () => {
    await dag([compose, sdg]);
    expect(node("st55_sdg").querySelector('[data-field="wall"]')).toBeNull();
    expect(document.querySelector('[data-testid="stage-dag"]')?.textContent).not.toContain("913.75");
  });

  it("FR-019-24 · edges go from the stage that produced an input artefact to the stage that lists it", async () => {
    await dag([compose, physics, sdg, rejected]);
    const edges = Array.from(document.querySelectorAll('[data-testid="dag-edge"]')).map(
      (e) => `${e.getAttribute("data-from")}>${e.getAttribute("data-to")}`,
    );
    expect(edges.sort()).toEqual(["st40_compose>st50_physics", "st40_compose>st55_sdg"]);
  });

  it("FR-019-24 · an input that is a source, or an artefact that no stage of the card produced, draws no edge; a stage's own output is no edge", async () => {
    const own = makeStage("st40_compose", "openusd", {
      inputs: [
        { id: "c2-scene", sha256: "3".repeat(64), kind: "artefact" },
        { id: "usgs-3dep", sha256: "a".repeat(64), kind: "source" },
        { id: "ghost", sha256: "a".repeat(64), kind: "artefact" },
      ],
    });
    await dag([own, physics]);
    const edges = Array.from(document.querySelectorAll('[data-testid="dag-edge"]')).map(
      (e) => `${e.getAttribute("data-from")}>${e.getAttribute("data-to")}`,
    );
    expect(edges).toEqual(["st40_compose>st50_physics"]);
  });

  it("FR-019-24 · a card with no stage shows no node and no edge, without error", async () => {
    await dag([], []);
    expect(document.querySelectorAll('[data-testid="stage-node"], [data-testid="dag-edge"]')).toHaveLength(0);
    expect(document.querySelector('[data-testid="stage-dag"]')).not.toBeNull();
  });

  it("FR-019-24 · a hostile stage id is text", async () => {
    const evil = makeStage("<img src=x onerror=alert(1)>", "warp", {
      key: { id: "<img src=x onerror=alert(1)>" },
    });
    const { container } = await dag([evil]);
    expect(container.querySelector("img[src='x']")).toBeNull();
    expect(container.textContent).toContain("<img src=x onerror=alert(1)>");
  });
});

describe("determinism block (FR-019-25)", () => {
  const D1 = "1".repeat(64);
  const D2 = "2".repeat(64);
  const det = (id: string, determinism: unknown) => makeStage(id, "pytorch", { determinism });
  const block = (stages: unknown[]) =>
    renderApp(createElement(DeterminismBlock, { run: run(stages) as never }));
  const row = (id: string) =>
    document.querySelector<HTMLElement>(
      `[data-testid="determinism-stage"][data-stage="${id}"]`,
    ) as HTMLElement;

  it("FR-019-25 · bitwise with two equal digests: the class, both digests in full, and 'equal'", async () => {
    await block([det("s30_train", { class: "bitwise", rerun_check: "pass", rerun: { digests: [D1, D1] } })]);
    const t = row("s30_train").textContent ?? "";
    expect(t).toContain("bitwise");
    expect(t.split(D1).length - 1).toBe(2);
    expect(t).toMatch(/\bequal\b/);
    expect(t).not.toMatch(/different/);
  });

  it("FR-019-25 · bitwise with two different digests reads 'different', whatever rerun_check claims", async () => {
    await block([det("s30_train", { class: "bitwise", rerun_check: "pass", rerun: { digests: [D1, D2] } })]);
    const t = row("s30_train").textContent ?? "";
    expect(t).toContain(D1);
    expect(t).toContain(D2);
    expect(t).toMatch(/different/);
    expect(t).not.toMatch(/\bequal\b/);
  });

  it("FR-019-25 · digests that differ in one character, or only in case, are different", async () => {
    await block([
      det("s30_train", {
        class: "bitwise",
        rerun_check: "pass",
        rerun: { digests: [`${"a".repeat(63)}0`, `${"a".repeat(63)}1`] },
      }),
    ]);
    expect(row("s30_train").textContent).toMatch(/different/);
  });

  it("FR-019-25 · statistical: each observable with its tolerance and both values", async () => {
    await block([
      det("st50_physics", {
        class: "statistical",
        rerun_check: "pass",
        rerun: {
          observables: [
            { name: "angle_of_repose_deg", rtol: 0.02, atol: 0.5, first: 34.25, second: 34.75 },
            { name: "mass_flow_kg_s", rtol: 0.05, atol: 0, first: 12.5, second: 12.25 },
          ],
        },
      }),
    ]);
    const rows = Array.from(row("st50_physics").querySelectorAll('[data-testid="observable"]'));
    expect(rows).toHaveLength(2);
    for (const needle of ["angle_of_repose_deg", "0.02", "0.5", "34.25", "34.75"])
      expect(rows[0]?.textContent, needle).toContain(needle);
    for (const needle of ["mass_flow_kg_s", "0.05", "12.5", "12.25"])
      expect(rows[1]?.textContent, needle).toContain(needle);
    expect(row("st50_physics").textContent).toContain("statistical");
  });

  it("FR-019-25 · a missing check reads 'pending': no rerun data, or rerun_check pending", async () => {
    await block([
      det("a", { class: "bitwise", rerun_check: "pending" }),
      det("b", { class: "statistical", rerun_check: "pending", rerun: undefined }),
    ]);
    for (const id of ["a", "b"]) {
      expect(row(id).textContent, id).toMatch(/pending/i);
      expect(row(id).textContent, id).not.toMatch(/\bequal\b|different/);
    }
  });

  it("FR-019-25 · class none with 'not-applicable' is shown as such, not as pending", async () => {
    await block([det("s10_preprocess", { class: "none", rerun_check: "not-applicable" })]);
    expect(row("s10_preprocess").textContent).toContain("none");
    expect(row("s10_preprocess").textContent).toMatch(/not applicable/i);
    expect(row("s10_preprocess").textContent).not.toMatch(/pending/i);
  });

  it("FR-019-25 · one row per stage in card order, each with its class", async () => {
    await block([
      det("s1", { class: "bitwise", rerun_check: "pending" }),
      det("s2", { class: "statistical", rerun_check: "pending" }),
      det("s3", { class: "none", rerun_check: "not-applicable" }),
    ]);
    const rows = Array.from(document.querySelectorAll('[data-testid="determinism-stage"]'));
    expect(rows.map((r) => r.getAttribute("data-stage"))).toEqual(["s1", "s2", "s3"]);
    expect(within(rows[2] as HTMLElement).getByText(/none/)).toBeTruthy();
  });

  it("FR-019-25 · malformed rerun data (one digest, no observables, non-numeric values) shows 'pending' and does not throw", async () => {
    await block([
      det("a", { class: "bitwise", rerun_check: "pass", rerun: { digests: [D1] } }),
      det("b", { class: "statistical", rerun_check: "pass", rerun: { observables: [] } }),
      det("c", {
        class: "statistical",
        rerun_check: "pass",
        rerun: { observables: [{ name: "x", rtol: "a", atol: null, first: "b", second: {} }] },
      }),
    ]);
    for (const id of ["a", "b"]) expect(row(id).textContent, id).toMatch(/pending/i);
    expect(row("c").textContent).not.toMatch(/NaN|undefined|\[object/);
  });

  it("FR-019-25 · the observable name is text, never markup", async () => {
    await block([
      det("a", {
        class: "statistical",
        rerun_check: "pass",
        rerun: {
          observables: [{ name: "<img src=x onerror=alert(1)>", rtol: 0.1, atol: 0, first: 1, second: 1 }],
        },
      }),
    ]);
    expect(document.querySelector("img[src='x']")).toBeNull();
  });
});
