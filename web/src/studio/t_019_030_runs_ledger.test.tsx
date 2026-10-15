// T-019-030 [red] · FR-019-21 (the ledger lists only published runs, newest first, with run id, cases, producer tools, UTC date, determinism class and artefact count, filterable by `?case=` and `?tool=`,
// and says "No published runs yet" when there is none) and FR-019-41 (an unknown, malformed or over-long (> 2,000 characters) filter is ignored, all runs are shown with the note "unknown filter ignored").
// E2E half (published fixture runs, hostile filters, 404 for unpublished run ids): web/e2e/t_019_030_runs.spec.ts.
//
// Expected API: `~/studio/RunsLedger` (web/src/studio/RunsLedger.tsx): named export RunsLedger({ runs: RunCard[]; cases: string[]; tools: string[] }) where `runs` are the run cards (DC-001-01) found in the Pages artifact
// (a card with `published: false` is not a published run and is not listed) and `cases` / `tools` are the known case ids and tool ids of the registries; it reads `case` and `tool` from the URL query.
// Hooks: table[data-testid="runs-table"] with tr[data-run="<run id>"] and td[data-col="run|cases|tools|date|determinism|artefacts"]; the run cell holds a[href="/studio/runs/<run id>/"] with the run id;
// [data-testid="no-runs"] ("No published runs yet"); [data-testid="filter-note"] ("unknown filter ignored").
// Definitions (assumptions flagged in the report): the cases of a run are the union of the `cases` of its artefacts, the producer tools are the union of the `producer.tool` of its artefacts, the date is the UTC date of
// `created`, the determinism column names every class found among the run's stages, the artefact count is the length of the run card's `artefacts`.
// Oracles: hand-built run cards (the valid example of DC-001-01 as base), the EARS text, the date arithmetic of the UTC conversion.
import { screen, within } from "@testing-library/react";
import { createElement } from "react";
import { describe, expect, it } from "vitest";
import { RunsLedger } from "~/studio/RunsLedger";
import { makeArtefact } from "~/test-support/fixtures";
import { renderApp } from "~/test-support/render";
import { makeRunCard, makeStage, TOOL_IDS } from "~/test-support/studio-fixtures";

const CASES = ["A1", "A2", "A3", "B1", "B2", "C1", "C2", "C3", "D1", "D2", "E1", "E2"];
const art = (id: string, run: string, tool: string, cases: string[]) =>
  makeArtefact({ id, run_id: run, producer: { tool, stage: { id: "st50_physics" } }, cases } as never);
const stage = (id: string, tool: string, determinism: string) =>
  makeStage(id, tool, { determinism: { class: determinism, rerun_check: "pending" } });
const run = (id: string, created: string, over: Record<string, unknown> = {}) =>
  makeRunCard({
    run_id: id,
    created,
    published: true,
    stages: [stage("st50_physics", "warp", "bitwise")],
    artefacts: [art(`${id}-a`, id, "warp", ["C2"])],
    ...over,
  } as never);
const R1 = run("20261001T080000Z-c2", "2026-10-01T08:00:00Z");
const R2 = run("20261003T080000Z-a1", "2026-10-03T08:00:00Z", {
  stages: [stage("st56_encode", "nvenc-ffmpeg", "statistical"), stage("st53_sensors", "ovrtx", "none")],
  artefacts: [
    art("a1", "20261003T080000Z-a1", "nvenc-ffmpeg", ["A1"]),
    art("a2", "20261003T080000Z-a1", "nvenc-ffmpeg", ["A1", "B1"]),
    art("a3", "20261003T080000Z-a1", "pytorch", []),
  ],
});
const R3 = run("20261002T080000Z-d1", "2026-10-02T08:00:00Z", {
  artefacts: [
    art("d1", "20261002T080000Z-d1", "warp", ["D1"]),
    art("d2", "20261002T080000Z-d1", "openusd", ["D1", "E1"]),
  ],
});
const DRAFT = run("20261009T080000Z-draft", "2026-10-09T08:00:00Z", { published: false });

const render = (runs: unknown[], query = "") =>
  renderApp(createElement(RunsLedger, { runs: runs as never, cases: CASES, tools: TOOL_IDS }), {
    route: `/studio/runs/${query}`,
  });
const ids = () =>
  Array.from(document.querySelectorAll("tr[data-run]")).map((r) => r.getAttribute("data-run"));
const cell = (id: string, col: string) =>
  document.querySelector(`tr[data-run="${id}"] td[data-col="${col}"]`)?.textContent ?? "";

describe("the ledger (FR-019-21)", () => {
  it("FR-019-21 · lists the published runs newest first and not an unpublished one", async () => {
    await render([R1, DRAFT, R2, R3]);
    expect(ids()).toEqual(["20261003T080000Z-a1", "20261002T080000Z-d1", "20261001T080000Z-c2"]);
  });

  it("FR-019-21 · each row shows the run id (a link to its page), cases, producer tools, UTC date, determinism class and artefact count", async () => {
    await render([R2]);
    expect(document.querySelector('tr[data-run="20261003T080000Z-a1"] a')?.getAttribute("href")).toBe(
      "/studio/runs/20261003T080000Z-a1/",
    );
    expect(cell("20261003T080000Z-a1", "run")).toContain("20261003T080000Z-a1");
    const cases = cell("20261003T080000Z-a1", "cases");
    expect(cases).toContain("A1");
    expect(cases).toContain("B1");
    expect(cases).not.toContain("C2");
    const tools = cell("20261003T080000Z-a1", "tools");
    expect(tools).toContain("nvenc-ffmpeg");
    expect(tools).toContain("pytorch");
    expect(cell("20261003T080000Z-a1", "date")).toBe("2026-10-03");
    expect(cell("20261003T080000Z-a1", "determinism")).toContain("statistical");
    expect(cell("20261003T080000Z-a1", "determinism")).toContain("none");
    expect(cell("20261003T080000Z-a1", "artefacts")).toBe("3");
  });

  it("FR-019-21 · the table has a column header for each of the six columns", async () => {
    await render([R1]);
    const heads = Array.from(document.querySelectorAll('[data-testid="runs-table"] thead th')).map((h) =>
      h.textContent?.trim().toLowerCase(),
    );
    expect(heads).toHaveLength(6);
    for (const word of ["run", "case", "tool", "date", "determinism", "artefact"])
      expect(
        heads.some((h) => h?.includes(word)),
        word,
      ).toBe(true);
  });

  it("FR-019-21 · a run whose stages are all bitwise reads 'bitwise' and only that", async () => {
    await render([R1]);
    expect(cell("20261001T080000Z-c2", "determinism")).toContain("bitwise");
    expect(cell("20261001T080000Z-c2", "determinism")).not.toMatch(/statistical|none/);
  });

  it("FR-019-21 · the date is the UTC date: 23:59:59 at UTC-3 is already the next day", async () => {
    await render([run("20261007T235959Z-tz", "2026-10-07T23:59:59-03:00")]);
    expect(cell("20261007T235959Z-tz", "date")).toBe("2026-10-08");
  });

  it("FR-019-21 · two runs of the same instant are ordered by run id, descending, so that the order is stable", async () => {
    await render([
      run("20261005T000000Z-aaa", "2026-10-05T00:00:00Z"),
      run("20261005T000000Z-zzz", "2026-10-05T00:00:00Z"),
    ]);
    expect(ids()).toEqual(["20261005T000000Z-zzz", "20261005T000000Z-aaa"]);
  });

  it("FR-019-21 · with no run card the ledger says 'No published runs yet' and has no row", async () => {
    await render([]);
    expect(screen.getByTestId("no-runs").textContent).toContain("No published runs yet");
    expect(ids()).toEqual([]);
  });

  it("FR-019-21 · with only unpublished cards it says the same", async () => {
    await render([DRAFT]);
    expect(screen.getByTestId("no-runs").textContent).toContain("No published runs yet");
  });

  it("FR-019-21 · a run id with unusual characters is shown as text and linked with an encoded address", async () => {
    const odd = run("20261007T120000Z-<b>x</b> y", "2026-10-07T12:00:00Z");
    const { container } = await render([odd]);
    expect(container.querySelector("b")).toBeNull();
    expect(container.querySelector("tr[data-run] a")?.getAttribute("href")).toBe(
      `/studio/runs/${encodeURIComponent("20261007T120000Z-<b>x</b> y")}/`,
    );
  });
});

describe("filters (FR-019-21)", () => {
  const all = [R1, R2, R3];

  it("FR-019-21 · ?case=A1 lists the runs with an artefact of case A1", async () => {
    await render(all, "?case=A1");
    expect(ids()).toEqual(["20261003T080000Z-a1"]);
    expect(screen.queryByTestId("filter-note")).toBeNull();
  });

  it("FR-019-21 · ?case=D1 and ?case=E1 find the run that has an artefact of that case", async () => {
    await render(all, "?case=E1");
    expect(ids()).toEqual(["20261002T080000Z-d1"]);
  });

  it("FR-019-21 · ?tool=warp lists the runs with an artefact produced by warp", async () => {
    await render(all, "?tool=warp");
    expect(ids()).toEqual(["20261002T080000Z-d1", "20261001T080000Z-c2"]);
  });

  it("FR-019-21 · both filters together keep the runs that satisfy both", async () => {
    await render(all, "?case=D1&tool=openusd");
    expect(ids()).toEqual(["20261002T080000Z-d1"]);
    document.body.innerHTML = "";
    await render(all, "?case=A1&tool=openusd");
    expect(ids()).toEqual([]);
    expect(screen.queryByTestId("no-runs")).toBeNull();
  });

  it("FR-019-21 · a known filter that matches nothing leaves an empty table and not the 'No published runs yet' message", async () => {
    await render(all, "?case=C3");
    expect(ids()).toEqual([]);
    expect(screen.queryByTestId("no-runs")).toBeNull();
    expect(screen.queryByTestId("filter-note")).toBeNull();
  });
});

describe("hostile filters (FR-019-41)", () => {
  const all = [R1, R2, R3];
  const hostile: Array<[string, string]> = [
    ["an unknown case", "?case=zz"],
    ["a lower-case case id", "?case=a1"],
    ["markup as tool", `?tool=${encodeURIComponent("<script>alert(1)</script>")}`],
    ["an unknown tool", "?tool=no-such-tool"],
    ["an empty value", "?case="],
    ["a tool with a trailing space", "?tool=warp%20"],
    ["an encoded separator", "?case=A1%2F..%2FB1"],
    ["a null byte", "?case=A1%00"],
    ["20,000 characters", `?case=${"x".repeat(20_000)}`],
    ["a known id padded beyond 2,000 characters", `?tool=warp${"%20".repeat(1100)}`],
  ];
  for (const [what, query] of hostile) {
    it(`FR-019-41 · ${what}: ignored, every run is listed, the note 'unknown filter ignored' is shown`, async () => {
      await render(all, query);
      expect(ids()).toHaveLength(3);
      expect(screen.getByTestId("filter-note").textContent).toContain("unknown filter ignored");
      expect(document.querySelector("script")).toBeNull();
    });
  }

  it("FR-019-41 · a valid filter beside an unknown one is applied, the unknown one is ignored and noted", async () => {
    await render(all, "?case=A1&tool=no-such-tool");
    expect(ids()).toEqual(["20261003T080000Z-a1"]);
    expect(screen.getByTestId("filter-note").textContent).toContain("unknown filter ignored");
  });

  it("FR-019-41 · the note does not echo the hostile value", async () => {
    await render(all, `?tool=${encodeURIComponent("<img src=x onerror=alert(1)>")}`);
    expect(within(screen.getByTestId("filter-note")).queryByText(/img src/)).toBeNull();
    expect(document.querySelector("img[src='x']")).toBeNull();
  });
});
