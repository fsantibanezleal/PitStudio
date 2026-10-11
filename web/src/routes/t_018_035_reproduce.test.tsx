// T-018-035 [red] · FR-018-19, FR-018-20: the "Reproduce this" block at the end of every case page.
//
// Expected component API:
//   module  ~/cases/ReproduceBlock   export  function ReproduceBlock(props: {
//                                       caseId: string;                    // canonical id, e.g. "A1"
//                                       recipe: RecipeSummary | null;      // null = the recipe file does not exist in the repository at build time
//                                       runId: string | null;              // run id of the case's published artefacts; null when none is published
//                                    })
//     RecipeSummary = { stages: Array<{ resources: { gpu: "exclusive" | "nvenc" | "none" } }> }   (data-model 001 section 3.2)
//   DOM contract:
//     - a heading "Reproduce this";
//     - with a recipe: the recipe path `studio/recipes/cases/<id lower case>.yaml` as text and three `[data-command]` elements, in this order,
//         uv run studio plan <recipe> --profile laptop-rtx5000ada
//         uv run studio run <recipe> --profile laptop-rtx5000ada
//         uv run studio publish <run-id>          (the real run id when `runId` matches the run id pattern, else the literal <run-id>)
//       a requirement note: "needs an NVIDIA RTX GPU" when any stage has resources.gpu "exclusive", and no mention of NVIDIA when no stage
//       needs a GPU; a button named /copy/i whose click writes the three commands, one per line, to the clipboard;
//     - without a recipe (null): the text "Not yet run — recipe planned", no `[data-command]`, no copy button, no "uv run";
//     - never an absolute path, drive letter, UNC path, host name or user name.
//   run id pattern (data-model 001 section 1.3): ^[0-9]{8}T[0-9]{6}Z-[a-z0-9][a-z0-9-]{0,47}$ ; anything else is never put in a command.
// Oracles: the literal command strings of FR-018-19 and docs/cases/README.md; hand-written recipe summaries.
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ReproduceBlock } from "~/cases/ReproduceBlock";
import { CASE_IDS } from "~/test-support/fixtures";
import { props, renderApp } from "~/test-support/render";

const GPU_RECIPE = { stages: [{ resources: { gpu: "none" } }, { resources: { gpu: "exclusive" } }] };
const CPU_RECIPE = { stages: [{ resources: { gpu: "none" } }, { resources: { gpu: "none" } }] };
const RUN = "20261011T083000Z-a1";

async function block(caseId: string, recipe: unknown, runId: string | null) {
  return renderApp(<ReproduceBlock caseId={caseId} recipe={props(recipe)} runId={runId} />);
}

function commands(container: HTMLElement): string[] {
  return [...container.querySelectorAll("[data-command]")].map((e) => (e.textContent ?? "").trim());
}

describe("Reproduce this (FR-018-19)", () => {
  it("FR-018-19 · shows the heading, the recipe path and the three commands with the published run id", async () => {
    const { container } = await block("A1", GPU_RECIPE, RUN);
    expect(screen.getByRole("heading", { name: "Reproduce this" })).toBeTruthy();
    expect(container.textContent).toContain("studio/recipes/cases/a1.yaml");
    expect(commands(container)).toEqual([
      "uv run studio plan studio/recipes/cases/a1.yaml --profile laptop-rtx5000ada",
      "uv run studio run studio/recipes/cases/a1.yaml --profile laptop-rtx5000ada",
      `uv run studio publish ${RUN}`,
    ]);
  });

  it("FR-018-19 · the recipe path uses the lower-case id for every case", async () => {
    for (const id of CASE_IDS) {
      const { container, unmount } = await block(id, CPU_RECIPE, null);
      const path = `studio/recipes/cases/${id.toLowerCase()}.yaml`;
      expect(container.textContent, id).toContain(path);
      expect(commands(container)[0], id).toBe(`uv run studio plan ${path} --profile laptop-rtx5000ada`);
      unmount();
    }
  });

  it("FR-018-19 · without a published run the publish command keeps the literal <run-id>", async () => {
    const { container } = await block("C1", CPU_RECIPE, null);
    expect(commands(container)[2]).toBe("uv run studio publish <run-id>");
  });

  it("FR-018-19 · states 'needs an NVIDIA RTX GPU' when a stage needs an exclusive GPU", async () => {
    const { container } = await block("A1", GPU_RECIPE, null);
    expect(container.textContent).toContain("needs an NVIDIA RTX GPU");
  });

  it("FR-018-19 · does not claim a GPU requirement for a recipe whose stages need none", async () => {
    const { container } = await block("A1", CPU_RECIPE, null);
    expect(commands(container)).toHaveLength(3);
    expect(container.textContent).not.toContain("NVIDIA");
    expect(container.textContent).not.toContain("RTX");
  });

  it("FR-018-19 · the copy button writes the three commands, one per line, to the clipboard", async () => {
    const user = userEvent.setup();
    await block("A1", GPU_RECIPE, RUN);
    await user.click(screen.getByRole("button", { name: /copy/i }));
    expect(await navigator.clipboard.readText()).toBe(
      [
        "uv run studio plan studio/recipes/cases/a1.yaml --profile laptop-rtx5000ada",
        "uv run studio run studio/recipes/cases/a1.yaml --profile laptop-rtx5000ada",
        `uv run studio publish ${RUN}`,
      ].join("\n"),
    );
  });

  it("FR-018-19 · contains no absolute path, host name or user name", async () => {
    const { container } = await block("B2", GPU_RECIPE, RUN);
    expect(commands(container)).toHaveLength(3);
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/[A-Za-z]:[\\/]/);
    expect(text).not.toMatch(/\\\\[A-Za-z0-9._$-]+\\/);
    expect(text).not.toMatch(/(^|[\s"'=(,:])\/(home|Users|root|tmp|var|mnt|opt|srv)\//);
    expect(text).not.toContain("file:/");
  });

  it("FR-018-19 · a run id that is not a run id never reaches a command (shell metacharacters, paths, markup)", async () => {
    for (const hostile of [
      "x; rm -rf /",
      "C:\\Users\\someone\\run",
      "../../etc/passwd",
      "$(whoami)",
      "<img src=x onerror=alert(1)>",
      "",
      "A".repeat(500),
    ]) {
      const { container, unmount } = await block("A1", CPU_RECIPE, hostile);
      expect(commands(container)[2], JSON.stringify(hostile)).toBe("uv run studio publish <run-id>");
      expect(container.querySelector("img")).toBeNull();
      unmount();
    }
  });
});

describe("recipe not yet written (FR-018-20)", () => {
  it("FR-018-20 · states 'Not yet run — recipe planned' and shows no command", async () => {
    const { container } = await block("A1", null, null);
    expect(container.textContent).toContain("Not yet run — recipe planned");
    expect(commands(container)).toEqual([]);
    expect(container.textContent).not.toContain("uv run");
    expect(screen.queryByRole("button", { name: /copy/i })).toBeNull();
  });

  it("FR-018-20 · still ends with the Reproduce this heading, and a published run id changes nothing", async () => {
    await block("E1", null, RUN);
    expect(screen.getByRole("heading", { name: "Reproduce this" })).toBeTruthy();
    expect(document.body.textContent).toContain("Not yet run — recipe planned");
    expect(document.body.textContent).not.toContain(RUN);
  });
});
