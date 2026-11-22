// T-018-100 [red] · FR-018-77: the Reproduce block of a case with a published imported run states what reproduces that run (the
// import command and the run id) or why it cannot be reproduced yet, with the partial label of the run; a case with no published
// run keeps "Not yet run - recipe planned". Oracles: the run notes written by `studio import-run` (published run 20261012T061925Z-a3-dem-repose-20k,
// copied by hand), the FR text.
import { describe, expect, it } from "vitest";
import { renderApp } from "~/test-support/render";
import { importedRuns } from "./importedRuns";
import { type PublishedResult, readResult } from "./publishedResults";
import { ReproduceBlock } from "./ReproduceBlock";
import type { ArtefactRecord } from "./types";

const A3_RUN = "20261012T061925Z-a3-dem-repose-20k";
const GNS_RUN = "20261014T000302Z-a3-gns-v1-failed";
const NOTES = [
  "produced by the GPU queue, outside the runner",
  "job 21-dem-repose-n20k; script sha256 2ec8b6ecb22e67d0d198e65522e51b1c55f9616af78cfe5d66439ba18c96a6ae; log sha256 218ce14d",
  "calibrated synthetic, not validated against real data",
  "partial: recipe cases/a3.yaml is not written yet: its sha256 is recorded as zeros",
];
const art = (run: string) =>
  ({ id: "r", run_id: run, git_sha: "a".repeat(40), path: "p", lane: "static" }) as unknown as ArtefactRecord;

function result(
  run: string,
  notes: string[],
  over: Record<string, unknown> = {},
  profile = "imported",
): PublishedResult {
  const raw = {
    title: "T",
    label: "calibrated synthetic, not validated against real data",
    methods: [],
    verdict: "ok",
    headline: [],
    rows: [],
    ...over,
  };
  return readResult(raw, { stages: [], notes, profile }, run, art(run)) as PublishedResult;
}

describe("FR-018-77 the imported runs of a case", () => {
  it("FR-018-77 · reads the job, the label and the partial reasons of each imported run, newest first", () => {
    const runs = importedRuns([
      result(A3_RUN, NOTES),
      result(GNS_RUN, ["job 39-gns-train-v1-resume; x", "partial: GNS GPU-hours missing"], {
        verdict: "failed",
      }),
    ]);
    expect(runs.map((r) => r.runId)).toEqual([GNS_RUN, A3_RUN]);
    expect(runs[1]).toMatchObject({
      job: "21-dem-repose-n20k",
      label: "calibrated synthetic, not validated against real data",
      verdict: "ok",
      partialReasons: ["recipe cases/a3.yaml is not written yet: its sha256 is recorded as zeros"],
    });
    expect(runs[0]?.verdict).toBe("failed");
  });

  it("FR-018-77 · leaves out a run the runner made itself, and names no job it cannot read", () => {
    expect(importedRuns([result(A3_RUN, NOTES, {}, "laptop-rtx5000ada")])).toEqual([]);
    expect(importedRuns([result(A3_RUN, ["partial: x"])])[0]?.job).toBeNull();
  });
});

describe("FR-018-77 the Reproduce block", () => {
  it("FR-018-77 · without a recipe and with a published run: the run id, the import command, the publish command and the partial reason, never 'recipe planned'", async () => {
    const runs = importedRuns([result(A3_RUN, NOTES)]);
    const { container } = await renderApp(
      <ReproduceBlock caseId="A3" recipe={null} runId={A3_RUN} runs={runs} />,
    );
    const text = container.textContent ?? "";
    expect(text).not.toContain("Not yet run");
    expect(text).toContain(A3_RUN);
    expect(text).toContain("Partial provenance");
    expect(text).toContain("recipe cases/a3.yaml is not written yet");
    expect(text).toContain("calibrated synthetic, not validated against real data");
    const commands = [...container.querySelectorAll("[data-command]")].map((c) => c.textContent);
    expect(commands).toEqual([
      "uv run studio import-run 21-dem-repose-n20k --from <job output folder>",
      `uv run studio publish ${A3_RUN}`,
    ]);
    expect(container.querySelector(`a[href="/studio/runs/${A3_RUN}/"]`)).not.toBeNull();
    expect(container.textContent).toMatch(/no recipe/i);
  });

  it("FR-018-77 · states a failed evaluation as such, and a job that is not named as not reproducible yet", async () => {
    const runs = importedRuns([result(GNS_RUN, ["partial: GNS GPU-hours missing"], { verdict: "failed" })]);
    const { container } = await renderApp(
      <ReproduceBlock caseId="A3" recipe={null} runId={GNS_RUN} runs={runs} />,
    );
    expect(container.textContent).toContain("Failed evaluation");
    expect(container.textContent).toContain("cannot be reproduced yet");
    expect(container.querySelectorAll("[data-command]")).toHaveLength(0);
  });

  it("FR-018-77 · with a recipe and an imported run: the three recipe commands and the run list", async () => {
    const runs = importedRuns([result(A3_RUN, NOTES)]);
    const { container } = await renderApp(
      <ReproduceBlock
        caseId="C1"
        recipe={{ stages: [{ resources: { gpu: "exclusive" } }] }}
        runId={A3_RUN}
        runs={runs}
      />,
    );
    const commands = [...container.querySelectorAll("[data-command]")].map((c) => c.textContent);
    expect(commands.slice(0, 3)).toEqual([
      "uv run studio plan studio/recipes/cases/c1.yaml --profile laptop-rtx5000ada",
      "uv run studio run studio/recipes/cases/c1.yaml --profile laptop-rtx5000ada",
      `uv run studio publish ${A3_RUN}`,
    ]);
    expect(commands).toContain("uv run studio import-run 21-dem-repose-n20k --from <job output folder>");
  });

  it("FR-018-77 · a case with no published run keeps 'Not yet run' and no command", async () => {
    const { container } = await renderApp(
      <ReproduceBlock caseId="A1" recipe={null} runId={null} runs={[]} />,
    );
    expect(container.textContent).toContain("Not yet run — recipe planned");
    expect(container.querySelectorAll("[data-command]")).toHaveLength(0);
  });

  it("FR-018-77 · is written in Spanish", async () => {
    const runs = importedRuns([result(A3_RUN, NOTES)]);
    const { container } = await renderApp(
      <ReproduceBlock caseId="A3" recipe={null} runId={A3_RUN} runs={runs} />,
      { lang: "es" },
    );
    expect(container.textContent).toContain("Procedencia parcial");
    expect(container.textContent).not.toContain("Not yet run");
    expect(container.textContent).not.toContain("Partial provenance");
  });
});
