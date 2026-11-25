// T-018-034 [red] · FR-018-18, FR-000-01, FR-000-06: the anatomy of an artefact card.
//
// Expected component API:
//   module  ~/cards/ArtefactCard    export  function ArtefactCard(props: {
//                                      artefact: ArtefactRecord;          // web-manifest record, data-model 001 section 2.5
//                                      run?: RunSummary | null;           // { run_id, gpu: { name } | null, created: <UTC timestamp> } of artefact.run_id
//                                    })
//   DOM contract (rendered inside a router; no basename):
//     - a badge whose text is exactly LIVE, REPLAY or STATIC (from `artefact.lane`), and only that one;
//     - a producer chip: link with href `/studio/tools/<producer.tool>/` whose text contains the tool id;
//     - a run chip: link with href `/studio/runs/<run_id>/` whose text contains the run id;
//     - the first 7 hex digits of `git_sha`;
//     - the licence class (text containing the class, with a hyphen or a space: "public-domain" / "public domain");
//     - every input of kind "source" by its id (FR-000-01: data source);
//     - for REPLAY cards with a run: the sentence "Precomputed on <GPU name> on <YYYY-MM-DD>" (date = UTC date of `run.created`); LIVE and
//       STATIC cards never show it; a REPLAY card without a run or GPU shows no "Precomputed on" text and never prints undefined/null.
// Oracles: FR-018-18 / FR-000-06 text and the hand-written records of ~/test-support/fixtures.
import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ArtefactCard } from "~/cards/ArtefactCard";
import { GIT_SHA, makeArtefact, makeRun, RUN_ID } from "~/test-support/fixtures";
import { props, renderApp } from "~/test-support/render";

const GPU = "NVIDIA RTX 5000 Ada Generation Laptop GPU";

/** `card(artefact)` uses a default run; `card(artefact, undefined)` really passes no run. */
async function card(artefact = makeArtefact(), ...rest: [run?: unknown]) {
  const run = rest.length > 0 ? rest[0] : makeRun();
  return renderApp(<ArtefactCard artefact={props(artefact)} run={props(run)} />);
}

function badges(container: HTMLElement): string[] {
  return ["LIVE", "REPLAY", "STATIC"].filter((b) =>
    [...container.querySelectorAll("*")].some(
      (el) => el.children.length === 0 && el.textContent?.trim() === b,
    ),
  );
}

describe("badge (FR-018-18, FR-000-06)", () => {
  it("FR-018-18 · shows the REPLAY badge for a replay artefact and no other badge", async () => {
    const { container } = await card(makeArtefact({ lane: "replay" }));
    expect(badges(container)).toEqual(["REPLAY"]);
  });

  it("FR-018-18 · shows the LIVE badge for a live artefact and no other badge", async () => {
    const { container } = await card(makeArtefact({ lane: "live" }));
    expect(badges(container)).toEqual(["LIVE"]);
  });

  it("FR-018-18 · shows the STATIC badge for a static artefact and no other badge", async () => {
    const { container } = await card(
      makeArtefact({ lane: "static", kind: "table", budget_class: "own-code" }),
    );
    expect(badges(container)).toEqual(["STATIC"]);
  });
});

describe("provenance chips (FR-018-18, FR-000-06)", () => {
  it("FR-000-06 · links the producing tool to /studio/tools/<tool>/ and the run to /studio/runs/<run id>/", async () => {
    await card(makeArtefact({ producer: { tool: "isaac-lab", stage: { id: "st60_il_train" } } }));
    const tool = screen.getByRole("link", { name: /isaac-lab/ });
    expect(tool.getAttribute("href")).toBe("/studio/tools/isaac-lab/");
    const run = screen.getByRole("link", { name: new RegExp(RUN_ID) });
    expect(run.getAttribute("href")).toBe(`/studio/runs/${RUN_ID}/`);
  });

  it("FR-000-06 · shows the 7-hex commit", async () => {
    const { container } = await card();
    expect(container.textContent).toContain(GIT_SHA.slice(0, 7));
    expect(container.textContent).not.toContain(GIT_SHA.slice(0, 8));
  });

  it("FR-018-18 · shows the licence class", async () => {
    const pd = await card(makeArtefact({ licence_class: "public-domain" }));
    expect(pd.container.textContent).toMatch(/public[- ]domain/i);
    pd.unmount();
    const sa = await card(
      makeArtefact({ licence_class: "share-alike", spdx: "CC-BY-SA-4.0", attribution: "MineLib" }),
    );
    expect(sa.container.textContent).toMatch(/share[- ]alike/i);
  });

  it("FR-000-01 · shows the data source ids of the inputs of kind source, and not the other inputs", async () => {
    const { container } = await card(
      makeArtefact({
        inputs: [
          { id: "usgs-3dep-bingham", sha256: "b".repeat(64), kind: "source" },
          { id: "era5", sha256: "c".repeat(64), kind: "source" },
          { id: "upstream-model", sha256: "d".repeat(64), kind: "artefact" },
        ],
      }),
    );
    expect(container.textContent).toContain("usgs-3dep-bingham");
    expect(container.textContent).toContain("era5");
    expect(container.textContent).not.toContain("upstream-model");
  });
});

describe("REPLAY precompute sentence (FR-018-18, FR-000-06)", () => {
  it("FR-018-18 · a REPLAY card reads 'Precomputed on <GPU name> on <date>'", async () => {
    const { container } = await card(
      makeArtefact({ lane: "replay" }),
      makeRun({ created: "2026-10-11T08:30:00Z" }),
    );
    expect(container.textContent).toContain(`Precomputed on ${GPU} on 2026-10-11`);
  });

  it("FR-018-18 · the date is the UTC date of the run, also near midnight", async () => {
    const late = await card(makeArtefact({ lane: "replay" }), makeRun({ created: "2026-10-11T23:59:59Z" }));
    expect(late.container.textContent).toContain("on 2026-10-11");
    late.unmount();
    const early = await card(makeArtefact({ lane: "replay" }), makeRun({ created: "2026-10-12T00:00:01Z" }));
    expect(early.container.textContent).toContain("on 2026-10-12");
  });

  it("FR-018-18 · LIVE and STATIC cards do not show the precompute sentence", async () => {
    const live = await card(makeArtefact({ lane: "live" }));
    expect(badges(live.container)).toEqual(["LIVE"]);
    expect(live.container.textContent).not.toContain("Precomputed on");
    live.unmount();
    const stat = await card(makeArtefact({ lane: "static", kind: "table", budget_class: "own-code" }));
    expect(badges(stat.container)).toEqual(["STATIC"]);
    expect(stat.container.textContent).not.toContain("Precomputed on");
  });

  it("FR-018-18 · a REPLAY card whose run is unknown or CPU-only invents no GPU: no sentence, no undefined or null", async () => {
    for (const run of [undefined, null, makeRun({ gpu: null })]) {
      const { container, unmount } = await card(makeArtefact({ lane: "replay" }), run);
      expect(container.textContent).not.toContain("Precomputed on");
      expect(container.textContent).not.toMatch(/undefined|null|NaN/);
      expect(badges(container)).toEqual(["REPLAY"]);
      unmount();
    }
  });
});

describe("hostile records (FR-018-18)", () => {
  it("FR-018-18 · renders markup in the GPU name or the attribution as text", async () => {
    const evil = '<img src=x onerror="alert(1)">';
    const { container } = await card(
      makeArtefact({ lane: "replay", licence_class: "attribution", attribution: evil }),
      makeRun({ gpu: { backend: "nvml", name: evil, driver: "595.95" } }),
    );
    expect(container.querySelector("img")).toBeNull();
    expect(within(container).getAllByText(/alert\(1\)/).length).toBeGreaterThan(0);
  });

  it("FR-018-18 · an unparsable run date shows no date instead of Invalid Date", async () => {
    const { container } = await card(makeArtefact({ lane: "replay" }), makeRun({ created: "not-a-date" }));
    expect(badges(container)).toEqual(["REPLAY"]);
    expect(container.textContent).toContain(RUN_ID);
    expect(container.textContent).not.toMatch(/Invalid|NaN|undefined/);
    expect(container.textContent).not.toContain("on not-a-date");
  });
});
